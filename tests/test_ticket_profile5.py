"""TICKET-PROFILE-5 专项测试 — 行为信号两级检测流水线。

覆盖（票验收）：
- P5-1 一级门卫：指令词命中（以后/别/不要/记住/每次/我其实喜欢/我讨厌/
  不要再/请记得）→ True；日常文本不命中 → False（零成本）
- P5-2 二级精判：LLM 确认（is_signal:true）→ 提取候选 → 写 USER.md +
  profile_versions.jsonl（signal_source=auto_detect）
- P5-3 二级精判：LLM 拒绝（is_signal:false，如"以后再说吧"）→ 不写
- P5-4 二级精判：LLM 失败（异常 / error 返回 / 输出不可解析）→ 静默丢弃
- P5-5 模板兜底：候选不含模板词 → write_user_profile 拒写（not_behavioral）
- P5-6 静态：engine_adapter 注入点存在（message.complete 后异步触发）、
  signal_detector 模块结构（keyword_gate/检测入口）
- P5-7 异步入口：maybe_detect_profile_signal 起 daemon 线程不阻塞（返回即完）
"""

import json
import re
from pathlib import Path

from core.signal_detector import (
    _KEYWORDS,
    detect_profile_signal,
    keyword_gate,
    maybe_detect_profile_signal,
)

ROOT = Path(__file__).resolve().parent.parent
ENGINE_ADAPTER = ROOT / "core" / "engine_adapter.py"
SIGNAL_DETECTOR = ROOT / "core" / "signal_detector.py"

# 与真实 USER.md 同构
_USER_MD = (
    "# 用户模型（docs/USER.md）\n\n"
    "## 偏好\n"
    "- 代码评审意见的输出顺序：先讲风险，再讲优点。\n\n"
    "## 禁忌\n"
    "（暂无）\n\n"
    "## 工作流\n"
    "（暂无）\n"
)


def _fake_llm(content: str):
    """假 llm_caller：返回 OpenAI 格式响应（content 为精判输出）。"""

    def call_llm(messages, use_tools=True, **kwargs):
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}

    return call_llm


# ── P5-1：一级门卫（关键词命中/不命中）──────────────────────────────────

def test_p5_1_keyword_gate_hits():
    hits = [
        "以后别用 emoji",
        "以后回复简洁一点",
        "别用那么长的开头",
        "不要用这种语气",
        "记住我的咖啡偏好",
        "每次汇报先给结论",
        "我其实喜欢这样的格式",
        "我讨厌这种回答方式",
        "不要再加 emoji 了",
        "请记得先讲风险再讲优点",
    ]
    for text in hits:
        assert keyword_gate(text), f"应命中指令词: {text!r}"
    # 指令词清单与票面一致
    for k in ("以后", "别", "不要", "记住", "每次", "我其实喜欢", "我讨厌", "不要再", "请记得"):
        assert k in _KEYWORDS, f"指令词清单缺 {k!r}"


def test_p5_1_keyword_gate_misses():
    misses = [
        "",                       # 空
        None,                     # 非 str
        "今天天气不错",           # 日常闲聊
        "帮我把文件读一下",       # 一次性请求
        "运行测试",               # 指令但非画像信号（一级放行由二级拦）
    ]
    for text in misses:
        assert not keyword_gate(text), f"不应命中: {text!r}"


# ── P5-2：二级精判确认 → 写入（signal_source=auto_detect）───────────────

def test_p5_2_judge_confirm_writes(tmp_path, monkeypatch):
    import core.profile_writer as pw

    user_md = tmp_path / "USER.md"
    user_md.write_text(_USER_MD, encoding="utf-8")
    versions = tmp_path / "profile_versions.jsonl"
    kb = tmp_path / "knowledge_base.json"
    kb.write_text(json.dumps({"entries": [], "profile": {}}), encoding="utf-8")
    monkeypatch.setattr(pw, "_USER_MD_PATH", user_md)
    monkeypatch.setattr(pw, "_VERSIONS_FILE", versions)
    monkeypatch.setattr(pw, "_KB_PATH", kb)

    llm = _fake_llm(
        '{"is_signal": true, "category": "taboo", '
        '"candidate": "不要用 emoji"}'
    )
    result = detect_profile_signal("以后别用 emoji", llm)

    assert result is not None
    assert result["write"]["ok"] is True, f"写入应成功: {result}"
    assert result["write"]["version"]["signal_source"] == "auto_detect"

    # USER.md 禁忌分区（暂无）→ 候选行
    md = user_md.read_text(encoding="utf-8")
    assert "- 不要用 emoji" in md, "USER.md 禁忌分区应写入候选"

    # knowledge_base 影子
    kb_data = json.loads(kb.read_text(encoding="utf-8"))
    assert kb_data["profile"]["taboo"]["value"] == "不要用 emoji"

    # 版本快照 signal_source=auto_detect
    rows = [json.loads(l) for l in versions.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["signal_source"] == "auto_detect"
    assert rows[0]["reason"] == "behavioral"


def test_p5_2b_judge_confirm_preference(tmp_path, monkeypatch):
    """偏好类信号：我其实喜欢 → preference 写入。"""
    import core.profile_writer as pw

    user_md = tmp_path / "USER.md"
    user_md.write_text(_USER_MD, encoding="utf-8")
    versions = tmp_path / "profile_versions.jsonl"
    kb = tmp_path / "knowledge_base.json"
    kb.write_text(json.dumps({"entries": [], "profile": {}}), encoding="utf-8")
    monkeypatch.setattr(pw, "_USER_MD_PATH", user_md)
    monkeypatch.setattr(pw, "_VERSIONS_FILE", versions)
    monkeypatch.setattr(pw, "_KB_PATH", kb)

    llm = _fake_llm(
        '{"is_signal": true, "category": "preference", '
        '"candidate": "偏好回复先给结论再给细节"}'
    )
    result = detect_profile_signal("我其实喜欢先看到结论", llm)
    assert result["write"]["ok"] is True
    assert "- 偏好回复先给结论再给细节" in user_md.read_text(encoding="utf-8")


# ── P5-3：二级精判拒绝 → 丢弃 ─────────────────────────────────────────

def test_p5_3_judge_reject_no_write(tmp_path, monkeypatch):
    import core.profile_writer as pw

    user_md = tmp_path / "USER.md"
    user_md.write_text(_USER_MD, encoding="utf-8")
    versions = tmp_path / "profile_versions.jsonl"
    kb = tmp_path / "knowledge_base.json"
    kb.write_text(json.dumps({"entries": [], "profile": {}}), encoding="utf-8")
    monkeypatch.setattr(pw, "_USER_MD_PATH", user_md)
    monkeypatch.setattr(pw, "_VERSIONS_FILE", versions)
    monkeypatch.setattr(pw, "_KB_PATH", kb)

    # "以后再说吧" 命中"以后"但精判拒绝
    llm = _fake_llm('{"is_signal": false}')
    result = detect_profile_signal("以后再说吧", llm)

    assert result is not None
    assert result["write"] is None, "精判拒绝不应写入"
    assert result["judged"]["is_signal"] is False
    # USER.md 未被改动
    assert "不要用 emoji" not in user_md.read_text(encoding="utf-8")
    assert not versions.exists() or versions.read_text(encoding="utf-8").strip() == ""


# ── P5-4：精判失败 → 静默丢弃 ─────────────────────────────────────────

def test_p5_4_judge_failure_silent_drop(tmp_path, monkeypatch):
    import core.profile_writer as pw

    user_md = tmp_path / "USER.md"
    user_md.write_text(_USER_MD, encoding="utf-8")
    versions = tmp_path / "profile_versions.jsonl"
    kb = tmp_path / "knowledge_base.json"
    kb.write_text(json.dumps({"entries": [], "profile": {}}), encoding="utf-8")
    monkeypatch.setattr(pw, "_USER_MD_PATH", user_md)
    monkeypatch.setattr(pw, "_VERSIONS_FILE", versions)
    monkeypatch.setattr(pw, "_KB_PATH", kb)

    # 异常：llm_caller 直接抛
    def boom(messages, use_tools=True, **kwargs):
        raise RuntimeError("llm down")

    r1 = detect_profile_signal("以后别用 emoji", boom)
    assert r1 is None, "LLM 异常应返回 None"

    # error 返回
    def err_llm(messages, use_tools=True, **kwargs):
        return {"error": "timeout", "error_type": "http", "retryable": False}

    r2 = detect_profile_signal("以后别用 emoji", err_llm)
    assert r2 is None, "LLM error 返回应返回 None"

    # 输出不可解析 → 丢弃（None）
    r3 = detect_profile_signal("以后别用 emoji", _fake_llm("不是 JSON"))
    assert r3 is None, "不可解析应丢弃（None）"

    assert not versions.exists(), "全程不应写版本快照"


# ── P5-5：模板兜底（write_user_profile 拒写）──────────────────────────

def test_p5_5_template_fallback(tmp_path, monkeypatch):
    import core.profile_writer as pw

    user_md = tmp_path / "USER.md"
    user_md.write_text(_USER_MD, encoding="utf-8")
    versions = tmp_path / "profile_versions.jsonl"
    kb = tmp_path / "knowledge_base.json"
    kb.write_text(json.dumps({"entries": [], "profile": {}}), encoding="utf-8")
    monkeypatch.setattr(pw, "_USER_MD_PATH", user_md)
    monkeypatch.setattr(pw, "_VERSIONS_FILE", versions)
    monkeypatch.setattr(pw, "_KB_PATH", kb)

    # LLM 误判：候选是纯事实（不含模板词）→ write_user_profile 模板闸门拒写
    llm = _fake_llm(
        '{"is_signal": true, "category": "preference", "candidate": "喜欢冰美式"}'
    )
    result = detect_profile_signal("我其实喜欢冰美式", llm)
    assert result["write"]["ok"] is False
    assert result["write"]["reason"] == "not_behavioral"
    # USER.md 未写入
    assert "冰美式" not in user_md.read_text(encoding="utf-8")


# ── P5-6：静态断言（注入点 + 模块结构）────────────────────────────────

def test_p5_6_static_injection_point():
    src = ENGINE_ADAPTER.read_text(encoding="utf-8")
    # message.complete emit 之后注入异步检测
    assert "emit(\"message.complete\"" in src
    assert "maybe_detect_profile_signal" in src, "engine_adapter 应调异步检测入口"
    assert "TICKET-PROFILE-5" in src, "注入点应带票标记"

    det = SIGNAL_DETECTOR.read_text(encoding="utf-8")
    assert "def keyword_gate" in det
    assert "def detect_profile_signal" in det
    assert "def maybe_detect_profile_signal" in det
    # 写入走 write_user_profile（signal_source=auto_detect）
    assert "signal_source=\"auto_detect\"" in det


# ── P5-7：异步入口不阻塞 ──────────────────────────────────────────────

def test_p5_7_async_entry_nonblocking():
    """maybe_detect_profile_signal 返回即完（daemon 线程），不阻塞主流程。"""
    import time

    called = []

    def slow_llm(messages, use_tools=True, **kwargs):
        called.append(1)
        time.sleep(5)  # 模拟慢 LLM

    t0 = time.time()
    maybe_detect_profile_signal("sid-x", "以后别用 emoji", slow_llm, delay=0.01)
    elapsed = time.time() - t0
    # 入口应立即返回（不等待线程内的 5s）
    assert elapsed < 2.0, f"异步入口不应阻塞主流程: {elapsed:.2f}s"
    # 线程是 daemon 且会在延迟后执行（不 join，交给进程收尾）
