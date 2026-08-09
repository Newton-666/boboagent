"""票 LN-2S：笔记原料换血 — takeaways → 完整回复全文。

覆盖 8 项验收（全部 tmpdir 物理检查 + 密度断言）：
  1. 钩子传全文：2000 字 full_reply → 重写 prompt 收到完整未截断全文
  2. 密度金标准：3 公式 + 2 参数决策 + 1 推理链的长回复 →
     重写后笔记正文 ≥ 回复 60%，公式/决策逐字可寻
  3. 花絮过滤："Bobo承认表述混淆" 不进 ## 关键结论（可在时间线或不存在）
  4. 新主题成文：概述是多句完整表述，不是单行要点
  5. 32000 截断：超长回复 → 截断 + notes.error truncated=true + 流程不炸
  6. BOBO_LIVING_NOTES=off → 零动作
  7. library 只读 → 降级不炸 + notes.error
  8. 全量测试零回归（由 run_tests 单独验证）

边界：_extract_takeaways 不动、memory_mirror 不动、LN-3/LN-4 不碰。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.living_notes as ln


@pytest.fixture
def ln_env(tmp_path, monkeypatch):
    """隔离的 library 环境。"""
    library = tmp_path / "library"
    monkeypatch.setattr(ln, "LIBRARY_DIR", library)
    return library


@pytest.fixture
def event_capture(monkeypatch):
    """捕获事件总线写入（假 bus，非 mock 蒙混）。"""
    import core.event_bus as eb
    fired = []

    class _Bus:
        def write(self, t, d):
            fired.append((t, d))

    monkeypatch.setattr(eb, "event_bus", _Bus())
    return fired


def _old_note(ln_env, topic="矩阵B构造", domain="技术研究") -> object:
    """手工构造 v1 旧笔记（骨架格式）。"""
    fm = (
        "---\n"
        f"topic: {topic}\ndomain: {domain}\ncreated: 2026-01-01\n"
        "last_touched: 2026-01-01\nversion: 1\nsource_sessions: [sid-1]\n"
        "---\n\n"
    )
    body = (
        "## 概述\n\n- 旧概述（源自会话 sid-1）\n\n"
        "## 关键结论\n\n- 旧结论（源自会话 sid-1）\n\n"
        "## 决策与原因\n\n- 旧决策（源自会话 sid-1）\n\n"
        "## 待办与未决\n\n- 旧待办（源自会话 sid-1）\n\n"
        "## 时间线\n\n- 10:00 旧时间线（源自会话 sid-1）\n"
    )
    d = ln_env / domain
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{topic}.md"
    p.write_text(fm + body, encoding="utf-8")
    return p


def _dense_reply() -> str:
    """构造含 3 公式 + 2 参数决策 + 1 条推理链的长回复。"""
    return (
        "本轮结论有三条。\n"
        "第一条：能量与质量的关系由公式 E=mc^2 描述，其中 c 是光速。\n"
        "第二条：牛顿第二定律 F=ma 说明力等于质量乘加速度，这是动力学基础。\n"
        "第三条：理想气体状态方程 PV=nRT 连接了压强、体积、物质的量与温度。\n"
        "参数决策：学习率 lr=1e-4，batch_size=64，这两个值经过三轮实验确定。\n"
        "推理链：因为 E=mc^2 成立，且 F=ma 定义了力的作用，所以 PV=nRT "
        "在等温条件下可以简化为 P1V1=P2V2，这构成了本轮的完整推理路径。\n"
        "以上内容需要完整记入笔记，一个公式都不能丢。"
    )


def _dense_rewrite(reply: str, old_tl="- 10:00 旧时间线（源自会话 sid-1）") -> str:
    """重写输出：保留旧时间线 + 完整组织回复（公式/决策逐字保留，正文足够长）。"""
    return (
        "---\ntopic: 矩阵B构造\ndomain: 技术研究\ncreated: 2026-01-01\n---\n\n"
        "## 概述\n\n"
        "本轮围绕三个核心公式展开完整推导。能量与质量的关系由公式 E=mc^2 描述，"
        "其中 c 是光速；牛顿第二定律 F=ma 说明力等于质量乘加速度，这是动力学基础；"
        "理想气体状态方程 PV=nRT 连接了压强、体积、物质的量与温度。\n\n"
        "## 关键结论\n\n"
        "- 公式 E=mc^2 确立能量质量等价关系（源自会话 sid-2）\n"
        "- 公式 F=ma 是动力学基础定律（源自会话 sid-2）\n"
        "- 公式 PV=nRT 描述理想气体状态（源自会话 sid-2）\n\n"
        "## 决策与原因\n\n"
        "- 学习率 lr=1e-4：经三轮实验确认收敛稳定（源自会话 sid-2）\n"
        "- batch_size=64：在显存与收敛速度间取平衡（源自会话 sid-2）\n\n"
        "## 待办与未决\n\n"
        "- 等温简化条件 P1V1=P2V2 需实测验证（源自会话 sid-2）\n\n"
        "## 时间线\n\n" + old_tl + "\n- 10:30 三个公式与两个参数决策定稿（源自会话 sid-2）\n"
    )


def _seq_llm(judge: dict, writer, seen=None):
    """两阶段假 LLM：判定调用 → judge；成文/重写调用 → writer(prompt)。

    writer 返回 (content) 或直接 dict；seen 用于捕获 prompt 供断言。
    """
    seen = seen if seen is not None else {}

    def call(prompt, use_tools=False):
        user = prompt[-1]["content"] if isinstance(prompt, list) else str(prompt)
        if "本轮完整回复" in user or "旧笔记全文" in user:
            seen["write_prompt"] = user
            return writer(user)
        seen["judge_prompt"] = user
        return {"choices": [{"message": {"content": json.dumps(judge, ensure_ascii=False)}}]}

    return call


# ── 验收 1：钩子传全文（2000 字不截断）──────────────

def test_full_reply_not_truncated(ln_env):
    path = _old_note(ln_env)
    reply = "本轮回复内容。" * 400  # 约 2800 字 > 300 字截断线
    assert len(reply) > 300
    seen = {}

    def writer(user):
        # 重写输出：保留旧时间线行
        old = path.read_text(encoding="utf-8")
        tl = old.split("## 时间线")[1].strip()
        return {"choices": [{"message": {"content": (
            "---\ntopic: 矩阵B构造\ndomain: 技术研究\ncreated: 2026-01-01\n---\n\n"
            "## 概述\n\n- 完整内容（源自会话 sid-2）\n\n"
            "## 时间线\n\n" + tl + "\n- 10:30 本轮（源自会话 sid-2）\n"
        )}}]}

    llm = _seq_llm(
        {"topic": "矩阵B构造", "domain": "技术研究",
         "section": "- 本轮要点", "match": "矩阵B构造"},
        writer, seen)
    result = ln.write_living_notes(["要点"], "消息", "sid-2", llm, full_reply=reply)
    assert result["written"] is True
    # 重写 prompt 收到完整回复全文（未被截断）
    assert "本轮完整回复" in seen["write_prompt"]
    assert reply in seen["write_prompt"]


# ── 验收 2：密度金标准（≥60% + 公式/决策逐字可寻）───

def test_density_gold_standard(ln_env):
    path = _old_note(ln_env)
    reply = _dense_reply()
    seen = {}

    def writer(user):
        old = path.read_text(encoding="utf-8")
        tl = old.split("## 时间线")[1].strip()
        return {"choices": [{"message": {"content": _dense_rewrite(reply, tl)}}]}

    llm = _seq_llm(
        {"topic": "矩阵B构造", "domain": "技术研究",
         "section": "- 本轮要点", "match": "矩阵B构造"},
        writer, seen)
    result = ln.write_living_notes(["要点"], "消息", "sid-2", llm, full_reply=reply)
    assert result["written"] is True

    text = path.read_text(encoding="utf-8")
    body = text[text.find("---", 3) + 4:]  # frontmatter 之后的正文
    # 笔记正文字符数 ≥ 回复正文 60%
    assert len(body) >= len(reply) * 0.6, (
        f"笔记 {len(body)} 字 < 回复 {len(reply)} 字的 60%"
    )
    # 3 个公式逐字可寻
    for formula in ["E=mc^2", "F=ma", "PV=nRT"]:
        assert formula in body, f"公式 {formula} 在笔记中找不到"
    # 2 个参数决策逐字可寻
    for decision in ["lr=1e-4", "batch_size=64"]:
        assert decision in body, f"决策 {decision} 在笔记中找不到"


# ── 验收 3：花絮过滤 ───────────────────────────────

def test_gossip_filtered_from_conclusions(ln_env):
    path = _old_note(ln_env)
    reply = ("核心结论：B 矩阵需要显式构造。\n"
             "Bobo承认此前表述混淆，现已澄清 K_A 与 K_B 的关系。\n"
             "下一步验证泛化。")
    seen = {}

    def writer(user):
        old = path.read_text(encoding="utf-8")
        tl = old.split("## 时间线")[1].strip()
        # 花絮进时间线，不进关键结论
        return {"choices": [{"message": {"content": (
            "---\ntopic: 矩阵B构造\ndomain: 技术研究\ncreated: 2026-01-01\n---\n\n"
            "## 概述\n\n- B 矩阵需显式构造（源自会话 sid-2）\n\n"
            "## 关键结论\n\n- B 矩阵需显式构造（源自会话 sid-2）\n\n"
            "## 时间线\n\n" + tl
            + "\n- 10:30 澄清 K_A 与 K_B 关系（源自会话 sid-2）\n"
        )}}]}

    llm = _seq_llm(
        {"topic": "矩阵B构造", "domain": "技术研究",
         "section": "- 本轮要点", "match": "矩阵B构造"},
        writer, seen)
    result = ln.write_living_notes(["要点"], "消息", "sid-2", llm, full_reply=reply)
    assert result["written"] is True
    text = path.read_text(encoding="utf-8")
    # "Bobo承认" 不在 ## 关键结论 章节内（花絮进时间线）
    conclusion_sec = text.split("## 关键结论")[1].split("## ")[0]
    assert "Bobo承认" not in conclusion_sec


# ── 验收 4：新主题成文（概述多句完整表述）───────────

def test_new_topic_full_prose(ln_env):
    reply = ("这是关于上下文预算管理的第一轮讨论。\n"
             "我们决定采用分层策略：先按 token 估算，再按消息条数兜底。\n"
             "阈值设为 12000，超出后优先压缩历史工具结果。")
    seen = {}

    def writer(user):
        return {"choices": [{"message": {"content": (
            "---\ntopic: 上下文预算\ndomain: agent开发\ncreated: 2026-07-31\n---\n\n"
            "## 概述\n\n"
            "本轮确立了上下文预算管理的分层策略。首先按 token 数量进行估算，"
            "当 token 估算不可靠时，再按消息条数作为兜底判断依据。"
            "阈值统一设为 12000，一旦超出预算，优先压缩历史工具结果以释放空间。\n\n"
            "## 关键结论\n\n- 分层策略：token 估算优先，条数兜底（源自会话 sid-1）\n\n"
            "## 时间线\n\n- 10:30 确立上下文预算分层策略（源自会话 sid-1）\n"
        )}}]}

    llm = _seq_llm(
        {"topic": "上下文预算", "domain": "agent开发",
         "section": "- 本轮要点", "match": None},
        writer, seen)
    result = ln.write_living_notes(["要点"], "消息", "sid-1", llm, full_reply=reply)
    assert result["written"] is True and result["is_new"] is True
    path = ln_env / "agent开发" / "上下文预算.md"
    text = path.read_text(encoding="utf-8")
    overview = text.split("## 概述")[1].split("## ")[0]
    # 概述是多句完整表述：长度超过单行要点 + 含多个句号
    assert len(overview.strip()) > 100
    assert overview.count("。") >= 3
    # 关键结论含完整决策细节
    assert "12000" in text
    assert "token" in text


# ── 验收 5：32000 截断 + notes.error truncated=true ──

def test_32000_truncation(ln_env, event_capture):
    path = _old_note(ln_env)
    reply = "超长回复片段。" * 5000  # > 32000 字符（7×5000=35000）
    assert len(reply) > 32000
    seen = {}

    def writer(user):
        old = path.read_text(encoding="utf-8")
        tl = old.split("## 时间线")[1].strip()
        return {"choices": [{"message": {"content": (
            "---\ntopic: 矩阵B构造\ndomain: 技术研究\ncreated: 2026-01-01\n---\n\n"
            "## 概述\n\n- 截断后仍成文（源自会话 sid-2）\n\n"
            "## 时间线\n\n" + tl + "\n- 10:30 本轮（源自会话 sid-2）\n"
        )}}]}

    llm = _seq_llm(
        {"topic": "矩阵B构造", "domain": "技术研究",
         "section": "- 本轮要点", "match": "矩阵B构造"},
        writer, seen)
    result = ln.write_living_notes(["要点"], "消息", "sid-2", llm, full_reply=reply)
    # 流程不炸、正常写成
    assert result["written"] is True
    # 传给 LLM 的回复部分被截断到 32000 内
    assert "本轮完整回复" in seen["write_prompt"]
    material_part = seen["write_prompt"].split("本轮完整回复：")[1]
    if material_part.startswith("\n"):
        material_part = material_part[1:]
    assert len(material_part) <= 32000
    # notes.error truncated=true 事件
    assert any(t == "notes.error" and d.get("truncated") is True
               for t, d in event_capture)


# ── 验收 6：总开关 off → 零动作 ─────────────────────

def test_env_off_noop(ln_env, monkeypatch):
    monkeypatch.setenv("BOBO_LIVING_NOTES", "off")
    calls = []

    def spy(prompt, use_tools=False):
        calls.append(prompt)
        return {"choices": [{"message": {"content": "{}"}}]}

    result = ln.write_living_notes(["要点"], "消息", "sid-1", spy, full_reply="全文")
    assert result["written"] is False
    assert result["error"] == "disabled"
    if ln_env.exists():
        assert list(ln_env.rglob("*.md")) == []
    assert calls == []


# ── 验收 7：library 只读 → 降级不炸 + notes.error ──

def test_readonly_library_notes_error(ln_env, event_capture):
    path = _old_note(ln_env)
    os.chmod(ln_env, 0o555)
    try:
        result = ln.write_living_notes(
            ["要点"], "消息", "sid-2",
            _seq_llm(
                {"topic": "矩阵B构造", "domain": "技术研究",
                 "section": "- 本轮要点", "match": "矩阵B构造"},
                lambda u: {"choices": [{"message": {"content": "---\n---\n\n## 概述\n\n- x\n"}}]}),
            full_reply="全文")
        assert result["written"] is False
        assert result["error"] is not None
        assert any(t == "notes.error" for t, _ in event_capture)
    finally:
        os.chmod(ln_env, 0o755)
