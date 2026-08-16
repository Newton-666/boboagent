"""TICKET-COST-1B 专项测试 — Token 消耗度量层（纯观测，只落盘）。

覆盖（票验收，全部实跑）：
- C1  JSONL 落盘字段齐全（usage/budget/tools/repeat_reads/duration_ms/branch/ticket）
- C2  追加写不覆盖（三轮回合 → 三行，逐行保留）
- C3  cache 字段缺时落 null 不编造（空 usage 也落行）
- C4  repeat_reads 侦测（同 path 读 3 次 → count=3；count≥2 才列）
- C5  budget 映射（临时 events.jsonl 含 prompt.budget → system/discipline/memory/pointers 归并正确）
- C6  消耗页签渲染（node 桩：页签按钮 + 拆解条 + 缓存未透传警示 + 重复劳动警示，全 Markdown 零 raw）
- C7  报告脚本聚合正确（--rounds 临时文件 → 总 tokens/调度层/缓存/repeat Top5 + 图落盘 PNG）
- C8  引擎行为零改动守卫（core/ 零 diff，铁律）

node 实跑：真实函数（从 index.html 提取）+ F13 同款桩 DOM。
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUI_FILE = ROOT / "apps" / "desktop" / "dist" / "index.html"


# ── 通用工具 ──

def _gui() -> str:
    return GUI_FILE.read_text(encoding="utf-8")


def _extract_func(src: str, fname: str) -> str:
    m = re.search(r"(?:async\s+)?function\s+" + fname + r"\s*\(", src)
    assert m, f"未找到 function {fname}"
    open_i = src.index("{", m.start())
    depth = 0
    for i in range(open_i, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():i + 1]
    raise AssertionError(f"function {fname} 括号不闭合")


def _run_node(js: str) -> str:
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败: {r.stderr}")
    return r.stdout


# ── C1-C5：gateway 度量层落盘 ──

def _sink(tmp: Path, events: dict | None = None):
    """构造隔离 MetricsSink（临时 rounds.jsonl + 可选临时 events.jsonl）。"""
    from bobo_tui_gateway.metrics import MetricsSink
    ev_path = tmp / "events.jsonl"
    if events:
        ev_path.write_text(json.dumps(events, ensure_ascii=False) + "\n", encoding="utf-8")
    return MetricsSink(metrics_path=tmp / "rounds.jsonl", events_path=ev_path)


def _drive_round(sink, sid, tools=None, usage=None, user_text="", budget_events=None):
    """驱动一轮事件流（start → tool* → complete），返回落盘行。"""
    sink.record_user_prompt(sid, user_text)
    sink.on_event("message.start", sid, {"session_id": sid})
    for t in (tools or []):
        sink.on_event("tool.start", sid, {**t, "session_id": sid})
        sink.on_event("tool.complete", sid, {**t, "session_id": sid})
    sink.on_event("message.complete", sid, {"usage": usage or {}, "session_id": sid})


def _read_rows(tmp: Path) -> list[dict]:
    p = tmp / "rounds.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").strip().splitlines() if l.strip()]


def test_c1_jsonl_fields_complete(tmp_path):
    """C1：落盘行字段齐全（usage 七键 + budget 四键 + tools + repeat_reads + duration_ms + branch/ticket）。"""
    sink = _sink(tmp_path)
    _drive_round(sink, "s1", tools=[{
        "name": "read_local_file", "arguments": {"file_path": "core/engine.py"},
        "duration": 0.12,  # tool.complete 的 duration（秒）
    }], usage={"input": 1234, "output": 567}, user_text="查结构")
    rows = _read_rows(tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert {"ts", "session_id", "round", "branch", "ticket", "usage",
            "budget", "tools", "repeat_reads", "duration_ms"} <= set(r)
    assert r["session_id"] == "s1" and r["round"] == 1
    assert r["branch"] and r["ticket"]  # 分支推断：feat/ticket-cost-1b → TICKET-COST-1B
    u = r["usage"]
    assert {"prompt_tokens", "completion_tokens", "cache_hit_tokens",
            "cache_miss_tokens", "user_prompt_chars"} <= set(u)
    assert u["prompt_tokens"] == 1234 and u["completion_tokens"] == 567
    assert u["user_prompt_chars"] == 3  # "查结构" = 3 字符
    assert r["tools"][0]["name"] == "read_local_file"
    assert r["tools"][0]["target"] == "core/engine.py"
    assert isinstance(r["tools"][0]["duration_ms"], int)
    assert isinstance(r["duration_ms"], int) and r["duration_ms"] >= 0


def test_c2_append_never_overwrite(tmp_path):
    """C2：三轮回合 → 三行，追加写绝不覆盖。"""
    sink = _sink(tmp_path)
    for i in range(3):
        _drive_round(sink, "s1", usage={"input": 100 + i, "output": 10}, user_text=f"第{i}轮")
    rows = _read_rows(tmp_path)
    assert len(rows) == 3
    assert [r["round"] for r in rows] == [1, 2, 3]
    assert [r["usage"]["prompt_tokens"] for r in rows] == [100, 101, 102]


def test_c3_cache_missing_null_not_fabricated(tmp_path):
    """C3：链路未透传 cache 字段 → 落 null，绝不编数；空 usage 也落行。"""
    sink = _sink(tmp_path)
    _drive_round(sink, "s1", usage={}, user_text="x")
    rows = _read_rows(tmp_path)
    assert len(rows) == 1
    u = rows[0]["usage"]
    assert u["cache_hit_tokens"] is None and u["cache_miss_tokens"] is None
    assert u["prompt_tokens"] is None and u["completion_tokens"] is None


def test_c4_repeat_reads_detection(tmp_path):
    """C4：同 path read 3 次 → count=3；count≥2 才列；grep 按 path+pattern 计。"""
    sink = _sink(tmp_path)
    tools = []
    for _ in range(3):
        tools.append({"name": "read_local_file", "arguments": {"file_path": "core/engine.py"}})
    tools.append({"name": "read_obsidian", "arguments": {"filename": "a.md"}})  # 1 次，不列
    tools.append({"name": "grep_code", "arguments": {"pattern": "def ", "path": "core/"}})
    tools.append({"name": "grep_code", "arguments": {"pattern": "def ", "path": "core/"}})
    _drive_round(sink, "s1", tools=tools, usage={"input": 1, "output": 1})
    rows = _read_rows(tmp_path)
    rr = rows[0]["repeat_reads"]
    assert {"target": "core/engine.py", "count": 3} in rr
    # COST-1c ③：grep 类 target 格式改为 pattern@path（票面口径）
    assert {"target": "def @core/", "count": 2} in rr
    assert all(x["target"] != "a.md" for x in rr)  # 单次读取不列


def test_c5_budget_mapping(tmp_path):
    """C5：events.jsonl 最近同 sid prompt.budget → 四段归并（system 含除 memory/note_pointers 外各段）。"""
    budget_event = {
        "ts": 1000.0, "type": "prompt.budget", "sid": "s1",
        "sections": {
            "selfmap": {"chars": 300},
            "now": {"chars": 50},
            "guidance": {"chars": 40},
            "office": {"chars": 10},
            "memory": {"chars": 200},
            "note_pointers": {"chars": 80},
        },
        "discipline": {"chars": 25},
    }
    sink = _sink(tmp_path, events=budget_event)
    _drive_round(sink, "s1", usage={"input": 1, "output": 1})
    b = _read_rows(tmp_path)[0]["budget"]
    assert b == {"system": 400, "discipline": 25, "memory": 200, "pointers": 80}


def test_c5b_budget_missing_all_null(tmp_path):
    """C5b：events.jsonl 无匹配 → 四段全 null（禁止编造）。"""
    sink = _sink(tmp_path)
    _drive_round(sink, "s1", usage={"input": 1, "output": 1})
    b = _read_rows(tmp_path)[0]["budget"]
    assert b == {"system": None, "discipline": None, "memory": None, "pointers": None}


def test_metrics_read_rpc(tmp_path, monkeypatch):
    """C6b：metrics.read 聚合查询（最近 N 条，新→旧，会话过滤）。"""
    from bobo_tui_gateway.metrics import MetricsSink
    sink = MetricsSink(metrics_path=tmp_path / "rounds.jsonl", events_path=tmp_path / "events.jsonl")
    for i in range(3):
        _drive_round(sink, "s1", usage={"input": i, "output": i}, user_text="u")
    _drive_round(sink, "s2", usage={"input": 9, "output": 9}, user_text="v")
    rows = sink.read_recent(limit=10)
    assert len(rows) == 4 and rows[0]["session_id"] == "s2"  # 新→旧
    rows_s1 = sink.read_recent(limit=10, session_id="s1")
    assert len(rows_s1) == 3 and all(r["session_id"] == "s1" for r in rows_s1)


# ── C7：报告脚本聚合 ──

def test_c7_cost_report_aggregation(tmp_path):
    """C7：cost_report.py 聚合正确 + 图落盘 PNG。"""
    import scripts.cost_report as cr
    rounds = tmp_path / "rounds.jsonl"
    data = []
    for i in range(3):
        data.append({
            "ts": 1700000000 + i, "session_id": "s1", "round": i + 1,
            "branch": "feat/ticket-cost-1b", "ticket": "TICKET-COST-1B",
            "usage": {
                "prompt_tokens": 1000 + i, "completion_tokens": 100 + i,
                "cache_hit_tokens": None, "cache_miss_tokens": None,
                "user_prompt_chars": 50,
            },
            "budget": {"system": 200, "discipline": 10, "memory": 30, "pointers": 20},
            "tools": [
                {"name": "read_local_file", "target": "core/engine.py", "duration_ms": 10, "error": False},
            ] * 2,
            "repeat_reads": [{"target": "core/engine.py", "count": 2}],
            "duration_ms": 100,
        })
    rounds.write_text("\n".join(json.dumps(x) for x in data), encoding="utf-8")
    out_png = tmp_path / "cost_feat_ticket-cost-1b.png"

    rows = cr.load_rounds(rounds)
    assert len(rows) == 3
    rows = cr.filter_rows(rows, branch="feat/ticket-cost-1b")
    assert len(rows) == 3
    agg = cr.aggregate(rows)
    assert agg["rounds"] == 3
    assert agg["prompt_tokens"] == 1000 + 1001 + 1002
    assert agg["completion_tokens"] == 100 + 101 + 102
    assert agg["user_chars"] == 150
    assert agg["tool_counter"]["read_local_file"] == 6
    assert agg["repeat_counter"]["core/engine.py"] == 6

    rc = cr.main(["--rounds", str(rounds), "--out", str(out_png), "--branch", "feat/ticket-cost-1b"])
    assert rc == 0
    md = cr.render_markdown(agg, rows, "feat/ticket-cost-1b", "")
    assert "调度层消耗" in md and "链路未透传" in md  # cache 缺 → 如实标注
    assert out_png.exists() and out_png.stat().st_size > 5000


# ── C6：消耗页签渲染（node 桩） ──

def _node_prelude() -> str:
    src = _gui()
    funcs = [_extract_func(src, fn) for fn in (
        # COST-1b 页签函数
        "_telHtmlEsc", "_telRenderCost", "_telCostHtml", "_telCostBar",
        "_telCacheRate", "_telRepeatWarn", "_telOnClick",
    )]
    return r"""
function makeEl(tag) {
  const el = {
    tagName: tag, _className: '', _innerHTML: '', textContent: '', style: {},
    _attrs: {}, _qs: {}, parentNode: null,
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return this._attrs[k]; },
    querySelector(sel) { if (!this._qs[sel]) { this._qs[sel] = makeEl(sel); this._qs[sel].parentNode = this; } return this._qs[sel]; },
    addEventListener() {},
  };
  Object.defineProperty(el, 'className', { get() { return el._className; }, set(v) { el._className = v || ''; } });
  Object.defineProperty(el, 'innerHTML', {
    get() { return this._innerHTML || ''; },
    set(v) { this._innerHTML = v || ''; },
  });
  return el;
}
""" + "\n".join(funcs)


def test_c6_cost_tab_render():
    """C6：消耗页签渲染（node 桩）——拆解条/缓存未透传警示/重复劳动警示，全 Markdown 零 raw。"""
    js = _node_prelude() + r"""
const FIXED_ROUNDS = [{
  round: 3, session_id: 's1', branch: 'feat/ticket-cost-1b', ticket: 'TICKET-COST-1B',
  usage: { prompt_tokens: 2000, completion_tokens: 300, cache_hit_tokens: null, cache_miss_tokens: null, user_prompt_chars: 120 },
  budget: { system: 400, discipline: 30, memory: 60, pointers: 20 },
  tools: [{ name: 'read_local_file', target: 'core/engine.py', duration_ms: 10, error: false }],
  repeat_reads: [{ target: 'core/engine.py', count: 3 }],
  duration_ms: 500,
}];
const html = _telCostHtml(FIXED_ROUNDS);
const out = [];
out.push('has_battle_tab_static=' + (html.indexOf('本轮拆解') >= 0));
out.push('has_user_seg=' + (html.indexOf('tel-bar-user') >= 0));
out.push('has_user_label=' + (html.indexOf('不计入优化口径') >= 0));
out.push('has_cache_warn=' + (html.indexOf('链路未透传') >= 0));
out.push('has_repeat_warn=' + (html.indexOf('重复读取') >= 0 && html.indexOf('× 3') >= 0 && html.indexOf('core/engine.py') >= 0));
out.push('has_sched_label=' + (html.indexOf('调度层') >= 0));
out.push('no_raw_json=' + (html.indexOf('{') < 0 || html.indexOf('"session_id"') < 0));
out.push('has_data_src=' + (html.indexOf('rounds.jsonl') >= 0));
// 页签切换：_telOnClick 处理 BUTTON[data-tab]
let switched = false;
const savedRender = globalThis._telRender;
const telEl = makeEl('div');
telEl._qs['[data-pane="cost"]'] = makeEl('div');
telEl._qs['[data-pane="cost"]']._innerHTML = '';
globalThis._telEl = telEl;
globalThis._telTab = 'battle';
globalThis._telRender = function() { switched = true; };
_telOnClick({ target: { tagName: 'BUTTON', getAttribute: function() { return 'cost'; } } });
out.push('tab_switch=' + switched + ':' + globalThis._telTab);
console.log(out.join('\n'));
"""
    out = _run_node(js)
    for line in out.strip().splitlines():
        key, val = line.split("=", 1)
        assert val == "true" or val.startswith("true"), f"{key} 断言失败: {line}"
    # 页签按钮存在（静态断言，桩 DOM 太弱；'tel-tab active' 是运行时拼接产物）
    src = _gui()
    assert 'data-tab="battle"' in src and 'data-tab="cost"' in src
    assert "tel-tabs" in src and 'class="tel-tab' in src


def test_c6b_cache_rate_with_values():
    """C6b：cache 字段有值 → 命中率渲染（本轮 + 均值）。"""
    js = _node_prelude() + r"""
const ROUNDS = [
  { round: 2, usage: { cache_hit_tokens: 75, cache_miss_tokens: 25 } },
  { round: 1, usage: { cache_hit_tokens: 50, cache_miss_tokens: 50 } },
];
const html = _telCacheRate(ROUNDS);
const out = [];
out.push('cur_pct=' + (html.indexOf('本轮命中 75%') >= 0));
out.push('avg_pct=' + (html.indexOf('近 2 轮均值 63%') >= 0));
console.log(out.join('\n'));
"""
    out = _run_node(js)
    for line in out.strip().splitlines():
        key, val = line.split("=", 1)
        assert val == "true", f"{key} 断言失败: {line}"


def test_c6c_repeat_warn_escaping():
    """C6c：重复劳动警示 HTML 转义（target 含 < > 不注入）。"""
    js = _node_prelude() + r"""
const html = _telRepeatWarn({ repeat_reads: [{ target: '<script>alert(1)</script>', count: 5 }] });
const out = [];
out.push('escaped=' + (html.indexOf('<script>') < 0 && html.indexOf('&lt;script&gt;') >= 0));
out.push('count=' + (html.indexOf('× 5') >= 0));
console.log(out.join('\n'));
"""
    out = _run_node(js)
    for line in out.strip().splitlines():
        key, val = line.split("=", 1)
        assert val == "true", f"{key} 断言失败: {line}"


# ── C8：引擎行为零改动守卫（铁律）──

def test_c8_core_zero_diff_guard():
    """C8：core/ 零 diff（铁律：纯度量层不得触碰引擎逻辑）。

    COST-1c 例外：core/llm_caller.py 为票面 ① 特批文件（仅加 llm.usage 事件透传，
    零逻辑改动），其余 core/ 文件仍必须零 diff。
    """
    r = subprocess.run(
        ["git", "diff", "--name-only", "core/"], capture_output=True, text=True, cwd=ROOT)
    r2 = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "core/"], capture_output=True, text=True, cwd=ROOT)
    changed = [x for x in (r.stdout + r2.stdout).splitlines() if x.strip()]
    # 票 COST-1c ① 特批白名单：llm_caller.py 允许（仅加字段透传）
    # 票 COST-2 特批白名单：injector.py 允许（仅限两处：NOW 锚点后移 + 小时级精度）
    changed = [x for x in changed if x not in ("core/llm_caller.py", "core/injector.py")]
    assert changed == [], f"core/ 有改动，违反铁律: {changed}"


def test_c8b_gui_lessons_l14_no_fake_globals():
    """C8b：GUI-LESSONS L14 —— 测试桩禁止虚构全局（页签函数用真实函数名实跑）。"""
    src = _gui()
    # 页签渲染函数必须真实存在于 index.html，不允许测试内自造
    for fn in ("_telRenderCost", "_telCostHtml", "_telCacheRate", "_telRepeatWarn", "_telHtmlEsc"):
        assert re.search(r"function\s+" + fn + r"\s*\(", src), f"真实函数缺失: {fn}"
