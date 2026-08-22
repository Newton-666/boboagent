"""TICKET-PROFILE-PARADIGM-IMPLEMENT 专项测试 — 约束框架接进二级精判 + 污染清理可回滚。

覆盖（票验收）：
1. 约束框架接进 detect_profile_signal：真范式→profile/instruction 写 USER；
   话题细节→memory（写 KB，不进 USER.md）；一次性→discard；纠正→correction（修正非新增）；
   显式指令豁免重复。
2. 污染清理：识别污染条目 + 清理 + 版本快照可回滚（快照文件即回滚依据）。
3. 反例（寒暄/敷衍/提问）校准边界。

全部用 monkeypatch 隔离（临时 USER.md/KB/版本快照路径），不污染真实权威文件。
detect_profile_signal 的二级精判用 mock llm_caller（返回约束框架 classify）。
"""

import json
import time

import pytest

from core import profile_writer as pw
from core import signal_detector as sd

# ── 初始（干净）USER.md：真范式 + 一条待修正条目 ──
_INIT_CLEAN_MD = """# 用户模型（docs/USER.md）

## 偏好
- 代码评审意见的输出顺序：先讲风险，再讲优点。
- 直接执行工具调用，不说明、不道歉。
- 轻量化设计：工具+Worker 扩展，不堆砌功能。
- 偏好直接、有用且简洁的沟通方式，避免冗长。

## 禁忌
（暂无）

## 工作流
- 直接调用工具建账，区分 done/pending，不解释不道歉。
- 未要求前不写运行脚本，先理解数据。
- 每日复盘固定早上 6:30 发送。
- 总结遵守 L2/L1 分层；早对话压缩、近对话保留原文。
- 先按现有框架执行，暴露问题后再调整。
- Obsidian 笔记与桌面文件夹同步对照。
"""

# ── 含污染的 USER.md：真范式 + topic级(K3/评测) + 一次性(先定评测集) ──
_INIT_POLLUTED_MD = """# 用户模型（docs/USER.md）

## 偏好
- 代码评审意见的输出顺序：先讲风险，再讲优点。
- 直接执行工具调用，不说明、不道歉。
- 轻量化设计：工具+Worker 扩展，不堆砌功能。
- 偏好直接、有用且简洁的沟通方式，避免冗长。
- 偏好使用创新性、前瞻性的数学题和代码题，而非普通竞赛题；偏好用 K3 能做出来但 30B 做不出来的题来测试。

## 禁忌
（暂无）

## 工作流
- 直接调用工具建账，区分 done/pending，不解释不道歉。
- 未要求前不写运行脚本，先理解数据。
- 每日复盘固定早上 6:30 发送。
- 总结遵守 L2/L1 分层；早对话压缩、近对话保留原文。
- 先按现有框架执行，暴露问题后再调整。
- Obsidian 笔记与桌面文件夹同步对照。
- 先定评测集，再调 API
"""


def _make_llm(mapping):
    """mock llm_caller：按 user_text 返回约束框架 classify JSON。"""
    def _llm(messages, **kw):
        user_text = ""
        for m in messages:
            if m["role"] == "user":
                user_text = m["content"].replace("用户消息：", "")
        obj = mapping.get(user_text, {"classify": "discard", "category": "preference", "candidate": ""})
        return {"choices": [{"message": {"content": json.dumps(obj, ensure_ascii=False)}}]}
    return _llm


def _isolate(monkeypatch, tmp_path, md_text):
    """重定向 USER.md/KB/版本快照到临时路径，不污染真实权威文件。"""
    md = tmp_path / "USER.md"
    md.write_text(md_text, encoding="utf-8")
    kb = tmp_path / "kb.json"
    kb.write_text('{"profile": {}, "entries": []}', encoding="utf-8")
    pv = tmp_path / "pv.jsonl"
    pv.write_text("", encoding="utf-8")
    monkeypatch.setattr(pw, "_USER_MD_PATH", md)
    monkeypatch.setattr(pw, "_KB_PATH", kb)
    monkeypatch.setattr(pw, "_VERSIONS_FILE", pv)
    monkeypatch.setattr(pw, "_KB_PATH", kb)
    return md


def test_five_class_shunt(monkeypatch, tmp_path):
    """五类分流：profile/instruction→USER.md，memory→KB（不入USER.md），discard→丢弃，correction→修正非新增。"""
    md = _isolate(monkeypatch, tmp_path, _INIT_CLEAN_MD)
    mapping = {
        "记住我以后都用 Obsidian 记录": {"classify": "instruction", "category": "workflow", "candidate": "以后都用 Obsidian 记录"},
        "我偏好任何文档都先讲风险再讲优点": {"classify": "profile", "category": "preference", "candidate": "任何文档都先讲风险再讲优点"},
        "在数学里我喜欢微积分": {"classify": "memory", "category": "memory", "candidate": "在数学里喜欢微积分"},
        "今天这种题我喜欢用几何": {"classify": "memory", "category": "memory", "candidate": "用几何解"},
        "下次先别用 K3 测一下": {"classify": "discard", "category": "preference", "candidate": ""},
        "先定评测集再调 API": {"classify": "discard", "category": "workflow", "candidate": ""},
        "别再用上次那种方案": {"classify": "correction", "category": "workflow", "candidate": "不要再用上次那种方案", "reference": "先按现有框架执行，暴露问题后再调整"},
    }
    llm = _make_llm(mapping)

    # instruction → USER.md（写）
    r = sd.detect_profile_signal("记住我以后都用 Obsidian 记录", llm, sid="t")
    assert r["classify"] == "instruction" and r["write"]["ok"] is True, "instruction 应写 USER.md"
    # profile → USER.md（写）
    r = sd.detect_profile_signal("我偏好任何文档都先讲风险再讲优点", llm, sid="t")
    assert r["classify"] == "profile" and r["write"]["ok"] is True, "profile 应写 USER.md"
    # memory → 写 KB（write.ok True），USER.md 不含该话题条目
    before = md.read_text(encoding="utf-8").count("微积分")
    r = sd.detect_profile_signal("在数学里我喜欢微积分", llm, sid="t")
    assert r["classify"] == "memory" and r["write"]["ok"] is True, "memory 应写 KB"
    assert md.read_text(encoding="utf-8").count("微积分") == before, "memory 不得进 USER.md"
    # discard → 丢弃（write None）
    r = sd.detect_profile_signal("下次先别用 K3 测一下", llm, sid="t")
    assert r["classify"] == "discard" and r["write"] is None, "discard 应丢弃"
    # correction → 修正旧条目（reference 行被替换，非新增）
    r = sd.detect_profile_signal("别再用上次那种方案", llm, sid="t")
    assert r["classify"] == "correction" and r["write"]["ok"] is True, "correction 应修正"
    content = md.read_text(encoding="utf-8")
    assert "先按现有框架执行，暴露问题后再调整" not in content, "correction 应替换旧条目（reference 行消失）"
    assert "不要再用上次那种方案" in content, "correction 新候选应写入"


def test_instruction_dedupe(monkeypatch, tmp_path):
    """显式指令豁免重复：重复 instruction 不产生第二条相同学段。"""
    md = _isolate(monkeypatch, tmp_path, _INIT_CLEAN_MD)
    mapping = {"记住这个工作流": {"classify": "instruction", "category": "workflow", "candidate": "记住这个工作流"}}
    llm = _make_llm(mapping)
    r1 = sd.detect_profile_signal("记住这个工作流", llm, sid="t")
    assert r1["write"]["ok"] is True
    r2 = sd.detect_profile_signal("记住这个工作流", llm, sid="t")
    assert r2["write"]["ok"] is False and r2["write"]["reason"] == "duplicate", "重复 instruction 应豁免（去重，不重复追加）"
    content = md.read_text(encoding="utf-8")
    assert content.count("记住这个工作流") == 1, "不重复追加同条"


def test_clean_user_md_pollution(monkeypatch, tmp_path):
    """污染清理：topic级/一次性被识别移出，真范式保留，版本快照可回滚。"""
    md = _isolate(monkeypatch, tmp_path, _INIT_POLLUTED_MD)
    # 记录清理前内容（回滚依据）
    before = md.read_text(encoding="utf-8")
    res = pw.clean_user_md_pollution()
    assert res["ok"] is True, "清理应成功"
    # 污染条目被移出
    removed_classes = [r["classify"] for r in res["removed"]]
    assert set(removed_classes) & {"memory", "discard"}, f"应移出 topic/一次性污染: {res['removed']}"
    assert any("K3" in r["entry"] for r in res["removed"]), "K3 话题细节应被清"
    assert any("先定评测集" in r["entry"] for r in res["removed"]), "一次性工作流应被清"
    # 真范式保留
    after = md.read_text(encoding="utf-8")
    assert "代码评审意见的输出顺序：先讲风险，再讲优点。" in after, "真范式应保留"
    assert "轻量化设计：工具+Worker 扩展，不堆砌功能。" in after, "真范式应保留"
    assert "偏好直接、有用且简洁的沟通方式，避免冗长。" in after, "真范式应保留"
    # 版本快照可回滚：清理前快照存在 + 被清条目记入快照（category=cleanup）
    assert res["backup"] and res["backup"].endswith(".md"), "应生成清理前备份（回滚依据）"
    snap_lines = (tmp_path / "pv.jsonl").read_text(encoding="utf-8").strip().splitlines()
    cleanup_snap = [json.loads(x) for x in snap_lines if x and json.loads(x).get("category") == "cleanup"]
    assert len(cleanup_snap) == len(res["removed"]), "清理动作应逐条记入版本快照（有据可查）"
    # 可回滚：备份文件内容 == 清理前内容，且备份路径可读
    import pathlib
    bp = pathlib.Path(res["backup"])
    assert bp.exists() and bp.read_text(encoding="utf-8") == before, "备份应完整保留清理前内容（可回滚）"


def test_negative_samples(monkeypatch, tmp_path):
    """反例校准：敷衍/请求/提问不走 USER.md（gate 挡或 discard）。"""
    md = _isolate(monkeypatch, tmp_path, _INIT_CLEAN_MD)
    mapping = {
        "以后再说吧": {"classify": "discard", "category": "preference", "candidate": ""},
        "你帮我看看这个文件": {"classify": "discard", "category": "preference", "candidate": ""},
        "今天天气怎么样": {"classify": "discard", "category": "preference", "candidate": ""},
    }
    llm = _make_llm(mapping)
    for text in ("你帮我看看这个文件", "今天天气怎么样"):
        r = sd.detect_profile_signal(text, llm, sid="t")
        assert r is None, f"{text} 应不触发（gate miss）"
    # "以后再说吧" gate 命中但 LLM 判 discard → 丢弃
    r = sd.detect_profile_signal("以后再说吧", llm, sid="t")
    assert r is not None and r["classify"] == "discard" and r["write"] is None, "敷衍应丢弃"
    content = md.read_text(encoding="utf-8")
    assert all(k not in content for k in ("以后再说吧", "看看这个文件", "天气怎么样")), "反例不得写 USER.md"
