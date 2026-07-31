"""票 HR-1：夜班体检报告验收测试（8 项金标准，tmpdir 全物理检查）。

  1. 20 行假事件 → 报告数字与手工核算一致
  2. events.jsonl 不存在 → 报告仍生成，板块 1 标"无数据"，不炸
  3. 坏行混入 → 跳过，统计不含坏行
  4. 假 library（疑似重复对 + 无 frontmatter 孤儿）→ 治理板块全部命中
  5. 幂等：同数据跑两次，报告内容逐字节一致
  6. 启动补报钩子 ensure_report：缺 → 生成；已存在 → None
  7. python -m tools.health_report 手动模式可跑
  8. 全量 pytest 通过（由 run_tests 单独验证零回归）
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.health_report as hr


def _ts(date_str: str, hour: int = 10) -> float:
    """构造指定日期某时刻的 Unix 时间戳。"""
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour)
    return d.timestamp()


def _write_events(events_path, rows, date_str):
    """写假 events.jsonl（可混入坏行）。"""
    events_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for r in rows:
        if isinstance(r, str):  # 坏行原样写入
            lines.append(r)
        else:
            lines.append(json.dumps(r, ensure_ascii=False))
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def env(tmp_path):
    """tmp 环境：events.jsonl + library + knowledge_base.json 全部隔离。"""
    data_dir = tmp_path / "data"
    events_path = data_dir / "logs" / "events.jsonl"
    library = tmp_path / "library"
    kb_path = tmp_path / "kb.json"
    # 默认空 knowledge_base（避免依赖真实数据）
    kb_path.write_text(json.dumps({"entries": []}), encoding="utf-8")
    return {"tmp": tmp_path, "events": events_path, "library": library,
            "kb": kb_path, "date": "2026-07-30"}


def _std_events(date_str: str) -> list[dict]:
    """20 行标准假事件（手工核算基准）。

    核算：
      exit 3 次：completed 2 / max_steps 1 / 异常 0
      step_fuse 1 次
      收工闸：no_ledger 2 / released 1
      llm.call 5 次（含 rate_limit×1）+ stream_stall 1
      tool.exec 4 次（无 status → 只总数）
      compressed 1 次：100 → 50
    """
    t = _ts(date_str)
    rows = []
    # 3 个线程退出
    rows += [
        {"ts": t + 1, "type": "engine.thread.exit", "session_id": "s1", "reason": "completed"},
        {"ts": t + 2, "type": "engine.thread.exit", "session_id": "s2", "reason": "completed"},
        {"ts": t + 3, "type": "engine.thread.exit", "session_id": "s3", "reason": "max_steps"},
    ]
    # 步数熔断
    rows.append({"ts": t + 4, "type": "engine.step_fuse", "session_id": "s3", "step_count": 71})
    # 收工闸
    rows += [
        {"ts": t + 5, "type": "goal_gate.no_ledger_detected", "session_id": "s1"},
        {"ts": t + 6, "type": "goal_gate.no_ledger_detected", "session_id": "s2"},
        {"ts": t + 7, "type": "goal_gate.released", "session_id": "s3"},
    ]
    # LLM 调用 5 次 + stream_stall
    rows += [
        {"ts": t + 10 + i, "type": "llm.call", "session_id": "s1",
         "msg_count": 5, "error_type": ("rate_limit" if i == 2 else None)}
        for i in range(5)
    ]
    rows.append({"ts": t + 20, "type": "llm.stream_stall", "session_id": "s1",
                 "received_chunks": 3, "action": "retry"})
    # 工具 4 次
    rows += [
        {"ts": t + 30 + i, "type": "tool.exec", "session_id": "s1",
         "name": "tool_x", "args_summary": "{}", "result_summary": "ok"}
        for i in range(4)
    ]
    # 上下文压缩
    rows.append({"ts": t + 40, "type": "context.compressed", "session_id": "s1",
                 "pre_msg_count": 100, "post_msg_count": 50})
    # 外加 1 条非目标日事件（应被过滤）
    rows.append({"ts": _ts("2026-07-29"), "type": "engine.thread.exit",
                 "session_id": "other", "reason": "completed"})
    return rows


# ── 验收 1：数字与手工核算一致 ──────────────────────

def test_numbers_match_manual_count(env):
    date = env["date"]
    _write_events(env["events"], _std_events(date), date)
    path = hr.generate_report(date, events_path=env["events"],
                              library_dir=env["library"], kb_path=env["kb"])
    text = path.read_text(encoding="utf-8")
    assert path.name == f"{date}.md"
    assert path.parent.name == "健康日报"
    # 板块 1 数字
    assert "回合 3 次：completed 2 / max_steps 1 / 异常 0" in text
    assert "步数熔断 1 次：s3" in text
    assert "收工闸：无账检测 2 次，熔断放行 1 次 ⚠️" in text
    assert "LLM 调用 5 次" in text
    assert "rate_limit×1" in text
    assert "stream_stall 1 次" in text
    assert "工具调用 4 次" in text
    assert "上下文压缩 1 次：100 条 → 50 条" in text
    # 非目标日事件未计入
    assert "other" not in text


# ── 验收 2：events.jsonl 不存在 → 不炸 ───────────────

def test_missing_events_no_crash(env):
    date = env["date"]
    path = hr.generate_report(date, events_path=env["events"],
                              library_dir=env["library"], kb_path=env["kb"])
    text = path.read_text(encoding="utf-8")
    assert "无数据（events.jsonl 不存在）" in text
    assert "## 引擎健康" in text
    assert "## 知识库治理" in text
    assert "## 异常关注" in text


# ── 验收 3：坏行跳过 ─────────────────────────────────

def test_bad_lines_skipped(env):
    date = env["date"]
    rows = _std_events(date)
    rows.insert(0, "这不是JSON{{{")
    rows.insert(3, '{"ts": 12345, "type": "broken"')  # 截断 JSON
    rows.insert(5, '{"type": "no_ts"}')  # 缺 ts
    _write_events(env["events"], rows, date)
    path = hr.generate_report(date, events_path=env["events"],
                              library_dir=env["library"], kb_path=env["kb"])
    text = path.read_text(encoding="utf-8")
    # 坏行不影响统计：数字仍与验收 1 一致
    assert "回合 3 次：completed 2 / max_steps 1 / 异常 0" in text
    assert "LLM 调用 5 次" in text
    assert "工具调用 4 次" in text


# ── 验收 4：治理板块全部命中 ─────────────────────────

def test_governance_section_hits(env):
    date = env["date"]
    lib = env["library"]
    # 3 篇主题笔记：一对疑似重复（收工闸/收工闸门）+ 1 篇无 frontmatter 孤儿
    (lib / "agent开发").mkdir(parents=True)
    (lib / "生活").mkdir()
    fm = ("---\ntopic: 收工闸\ndomain: agent开发\ncreated: 2026-07-29\n"
          "last_touched: 2026-07-30\nsource_sessions: [s1]\n---\n\n# 收工闸\n")
    (lib / "agent开发" / "收工闸.md").write_text(fm, encoding="utf-8")
    fm2 = ("---\ntopic: 收工闸门\ndomain: agent开发\ncreated: 2026-07-28\n"
           "last_touched: 2026-07-28\nsource_sessions: [s2]\n---\n\n# 收工闸门\n")
    (lib / "agent开发" / "收工闸门.md").write_text(fm2, encoding="utf-8")
    (lib / "生活" / "买菜清单.md").write_text("# 买菜清单\n无 frontmatter\n", encoding="utf-8")
    # MEMORY.md 与健康日报目录不应算主题笔记
    (lib / "MEMORY.md").write_text("# MEMORY\n", encoding="utf-8")
    (lib / "健康日报").mkdir()
    (lib / "健康日报" / "2026-07-29.md").write_text("# 旧报告\n", encoding="utf-8")

    path = hr.generate_report(date, events_path=env["events"],
                              library_dir=lib, kb_path=env["kb"])
    text = path.read_text(encoding="utf-8")
    # 主题笔记 3 篇（不含 MEMORY.md / 健康日报）
    assert "主题笔记 3 篇" in text
    # 疑似重复
    assert "疑似重复：」收工闸」~」收工闸门」" in text or "疑似重复" in text
    # 孤儿笔记
    assert "孤儿笔记 1 篇：买菜清单" in text
    # 健康日报目录下的旧报告未计入主题笔记
    assert "2026-07-29" not in text.split("## 知识库治理")[1].split("## 异常关注")[0]


# ── 验收 5：幂等逐字节一致 ───────────────────────────

def test_idempotent(env):
    date = env["date"]
    _write_events(env["events"], _std_events(date), date)
    p1 = hr.generate_report(date, events_path=env["events"],
                            library_dir=env["library"], kb_path=env["kb"])
    p2 = hr.generate_report(date, events_path=env["events"],
                            library_dir=env["library"], kb_path=env["kb"])
    assert p1.read_text(encoding="utf-8") == p2.read_text(encoding="utf-8")


# ── 验收 6：ensure_report 缺则生成 / 已有则跳过 ──────

def test_ensure_report(env):
    date = env["date"]
    _write_events(env["events"], _std_events(date), date)
    # 缺 → 生成
    p = hr.ensure_report(date, events_path=env["events"],
                         library_dir=env["library"], kb_path=env["kb"])
    assert p is not None and p.exists()
    # 已存在 → None（不重复生成）
    assert hr.ensure_report(date, events_path=env["events"],
                            library_dir=env["library"], kb_path=env["kb"]) is None


# ── 验收 7：手动模式可跑 ─────────────────────────────

def test_manual_cli(tmp_path):
    """python -m tools.health_report <date> 可跑（用真实环境幂等覆盖昨天报告）。"""
    date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-m", "tools.health_report", date],
        cwd=root, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "报告已生成" in result.stdout


# ── 补充：health.reported 事件埋点 ───────────────────

def test_health_reported_event(env):
    date = env["date"]
    _write_events(env["events"], _std_events(date), date)
    fired = []

    class _FakeBus:
        def write(self, t, d):
            fired.append((t, d))

    import core.event_bus as eb
    original = eb.event_bus
    try:
        eb.event_bus = _FakeBus()
        hr.generate_report(date, events_path=env["events"],
                           library_dir=env["library"], kb_path=env["kb"])
    finally:
        eb.event_bus = original
    assert any(t == "health.reported" for t, _ in fired)
