"""TICKET-R2-P1: relay 转发触发逻辑修复测试。

病历（2026-08-10 首跑）：23:05 轮转 1 条后停摆 / 23:30 bobo 8 连写
零转发 / 23:32 只通 bobo→hermes 单向。

根因：阶段 2 转发触发用 spoken（本次运行摘录计数）与 state（inbox 文件
序号，跨运行持久化）直接比较——两个不同语义。残留高位 state（封口
999 / 上次运行遗留）→ 触发永远不成立 = 零转发；inbox 非 1 起始序号 →
计数追不上序号 → 转 1 条即停 = 停摆。

修复（本票）：
1. 触发只看通道：read_new_inbox(name, state) 有文件才转，不依赖摘录计数
2. sanitize_state：state > 通道最大序号 → 自愈重置为 0
3. read_new_inbox 按数字序号排序（字符串排序 seq>=10 乱序）
4. 注入后重设目标基线：防注入内容被 diff 当发言回声转发
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import team_relay_v2 as tr  # noqa: E402


def _make_inbox(root: str, agent: str, seqs) -> None:
    d = os.path.join(root, agent)
    os.makedirs(d, exist_ok=True)
    for s in seqs:
        with open(os.path.join(d, f"{s:04d}.md"), "w", encoding="utf-8") as f:
            f.write(f"第{s}条发言内容")


class TicketR2P1Test(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self._old_inbox = tr.INBOX_ROOT
        self._old_state = tr.STATE_PATH
        tr.INBOX_ROOT = self.root
        tr.STATE_PATH = os.path.join(self._tmp.name, "relay.state")
        self.addCleanup(self._restore_paths)

    def _restore_paths(self):
        tr.INBOX_ROOT = self._old_inbox
        tr.STATE_PATH = self._old_state

    # ── 病历 1：23:30 零转发（封口 999 / 残留高位 state）──
    def test_sanitize_resets_capped_state(self):
        """state[bobo]=999（封口设置）且通道有 0001-0002 → 重置为 0。"""
        _make_inbox(self.root, "bobo", [1, 2])
        state = tr.sanitize_state({"bobo": 999, "hermes": 0, "claude": 0, "pi": 0})
        self.assertEqual(state["bobo"], 0)

    def test_sanitize_resets_leftover_after_cleanup(self):
        """上次运行遗留 state=4，通道清理后只有 0001-0003 → 重置为 0。"""
        _make_inbox(self.root, "bobo", [1, 2, 3])
        state = tr.sanitize_state({"bobo": 4, "hermes": 0, "claude": 0, "pi": 0})
        self.assertEqual(state["bobo"], 0)

    def test_sanitize_keeps_valid_state(self):
        """state=3 且通道最大 0005 → 保留（新文件 0004/0005 待转发）。"""
        _make_inbox(self.root, "bobo", [1, 2, 3, 4, 5])
        state = tr.sanitize_state({"bobo": 3, "hermes": 0, "claude": 0, "pi": 0})
        self.assertEqual(state["bobo"], 3)

    def test_sanitize_empty_channel_resets_high_state(self):
        """通道为空但 state 高 → 重置（无文件可转发，不留错误状态）。"""
        state = tr.sanitize_state({"bobo": 9, "hermes": 0, "claude": 0, "pi": 0})
        self.assertEqual(state["bobo"], 0)

    def test_sanitize_fills_missing_agents(self):
        state = tr.sanitize_state({"bobo": 1})
        self.assertEqual(state, {"bobo": 0, "hermes": 0, "claude": 0, "pi": 0})

    # ── 修复后的触发语义：只看通道，不依赖计数 ──
    def test_forward_trigger_channel_based(self):
        """旧逻辑 spoken<=state 会永久跳过；新逻辑 sanitize 后通道文件可读。"""
        _make_inbox(self.root, "bobo", [1, 2])
        state = tr.sanitize_state({"bobo": 999, "hermes": 0, "claude": 0, "pi": 0})
        msgs = tr.read_new_inbox("bobo", state["bobo"])
        self.assertEqual([seq for seq, _ in msgs], [1, 2])

    def test_no_duplicate_forward(self):
        """state=2 时只返回 0003/0004，不重复转发已转过的。"""
        _make_inbox(self.root, "bobo", [1, 2, 3, 4])
        msgs = tr.read_new_inbox("bobo", 2)
        self.assertEqual([seq for seq, _ in msgs], [3, 4])

    # ── read_new_inbox 数字排序（seq >= 10 不丢序）──
    def test_read_new_inbox_numeric_order(self):
        _make_inbox(self.root, "bobo", [1, 2, 10, 3, 11])
        msgs = tr.read_new_inbox("bobo", 0)
        self.assertEqual([seq for seq, _ in msgs], [1, 2, 3, 10, 11])

    # ── 通道读写往返 ──
    def test_write_read_roundtrip(self):
        seq1 = tr.write_inbox("hermes", "第一条发言")
        seq2 = tr.write_inbox("hermes", "第二条发言")
        self.assertEqual([seq1, seq2], [1, 2])
        msgs = tr.read_new_inbox("hermes", 0)
        self.assertEqual([m for _, m in msgs], ["第一条发言", "第二条发言"])

    def test_read_new_inbox_excludes_tmp(self):
        tr.write_inbox("pi", "正文")
        tmp = os.path.join(self.root, "pi", "9999.md.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("半截")
        msgs = tr.read_new_inbox("pi", 0)
        self.assertEqual([seq for seq, _ in msgs], [1])

    # ── clean_reply：注入段边界行/思考流不进通道 ──
    def test_clean_reply_filters_injection_markers_and_think(self):
        """clean_reply 过滤注入段边界行（【来自…的发言】/【硬约束】）与思考流。

        注：注入正文的防回声不在这里——正文任意文本无法用行前缀识别，
        由注入后重设基线在 diff 层拦截（见下方基线测试）。
        """
        raw = (
            "【来自 bobo 的发言】\n"
            "【硬约束·必须遵守】本讨论为纯讨论……\n"
            "💭 这是内部思考流\n"
            "【hermes】收到，同意。\n"
        )
        out = tr.clean_reply(raw)
        self.assertIn("【hermes】收到，同意。", out)
        self.assertNotIn("来自 bobo 的发言", out)
        self.assertNotIn("硬约束", out)
        self.assertNotIn("💭", out)

    # ── 注入后重设基线：防回声转发 ──
    def test_extract_reply_excludes_injection_after_baseline(self):
        """新基线含注入消息 → diff 只取新回复，注入内容不进通道。

        旧实现基站在注入前，注入内容出现在 after 中会被 diff 当成新发言
        提取 → 转发里带着别人发言的原文回声。
        """
        injection = "【来自 bobo 的发言】\n这是 bobo 的发言内容\n【硬约束·必须遵守】……"
        base = "⚕ ❯ msg=interrupt · /queue\n" + injection  # 注入后重设的基线
        reply = "【hermes】收到，同意你的观点。\n补充一点……"
        cur = base + "\n" + reply
        out = tr._capture_reply("hermes", base, cur)
        self.assertIn("收到，同意你的观点", out)
        self.assertNotIn("这是 bobo 的发言内容", out)


if __name__ == "__main__":
    unittest.main()
