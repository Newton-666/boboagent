"""core/observer.py — 学习环观察总线（阶段 C1：观察 → 分类 → 累积 → 触发）。

挂现有 event_bus（Pi 评审：别新建机制），读 events.jsonl。
信号 schema（决策点×结果）：{decision, input, output, result, error_type}
累积阈值：同 (decision, output, result) ≥3 次 → 触发 learning.trigger 事件（供落笔）。

护栏（技术层）：
- 信号可测（分类/累积是确定性代码，可单测）；
- 观察只喂"落笔"，不进前馈路径（前馈仍 description+规则驱动）；
- BOBO_LEARN=1 启用，默认关（行为不变，基线 diff=0）。

范式条款落点：学习 = 后端背景监督（本模块是观察者，LLM 是被监督的演员）。
"""
import json
import os
from collections import Counter, defaultdict

THRESHOLD = 3  # 累积阈值（技术层护栏二：一次不算三次才算）


class Signal:
    """一条可学习信号（决策点 × 结果）。"""

    def __init__(self, decision: str, output: str, result: str,
                 error_type: str = "", input_text: str = ""):
        self.decision = decision      # 决策类型：tool_exec / route / ...
        self.output = output          # 输出选了谁（工具名/技能名/记忆类型）
        self.result = result          # ok / fail
        self.error_type = error_type  # 失败分类（正则/路径/权限/网络...）
        self.input_text = input_text[:100]

    def key(self) -> tuple:
        return (self.decision, self.output, self.result, self.error_type)


def observer_enabled() -> bool:
    """BOBO_LEARN=1 启用观察（默认关：行为不变）。"""
    return os.environ.get("BOBO_LEARN", "0") == "1"


def _classify_error(error_text: str) -> str:
    """错误分类（确定性规则）：正则/路径/权限/网络/其他。"""
    e = str(error_text or "")
    if any(k in e for k in ("正则", "regex", "pattern", "invalid regex", "SyntaxError")):
        return "regex"
    if any(k in e for k in ("No such file", "找不到", "路径", "FileNotFoundError", "不存在")):
        return "path"
    if any(k in e for k in ("权限", "denied", "PermissionError", "未授权")):
        return "permission"
    if any(k in e for k in ("网络", "连接", "timeout", "timed out", "connection", "unreachable")):
        return "network"
    return "other"


def parse_events(events_path: str) -> list:
    """解析 events.jsonl → 信号列表。

    当前提取规则（可扩展）：
    - tool.exec 失败 → {decision: tool_exec, output: 工具名, result: fail, error_type}
    - tool.exec 成功 → {decision: tool_exec, output: 工具名, result: ok}
    """
    signals = []
    if not os.path.exists(events_path):
        return signals
    try:
        with open(events_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                t = ev.get("type", "")
                if t == "tool.exec":
                    _extract_tool_signal(ev, signals)
    except OSError:
        pass
    return signals


def _extract_tool_signal(ev: dict, signals: list):
    """从 tool.exec 事件提取信号（成功/失败）。"""
    tool = ev.get("tool", "") or ev.get("name", "")
    if not tool:
        return
    status = ev.get("status", "")
    error = ev.get("error") or ev.get("result_summary", "") or ev.get("error_detail", "") or ""
    if status == "error" or ("error" in str(ev.get("error_detail", "")).lower()):
        signals.append(Signal("tool_exec", tool, "fail",
                              _classify_error(error), ev.get("args_summary", "")))
    elif status in ("ok", "success", "done"):
        signals.append(Signal("tool_exec", tool, "ok"))


def accumulate(signals: list) -> dict:
    """按 (decision, output, result, error_type) 累积计数。"""
    counts = Counter(s.key() for s in signals)
    return counts


def find_triggers(counts: dict) -> list:
    """过阈值（≥THRESHOLD）的 (key, count) 列表——触发落笔候选。"""
    return [(k, c) for k, c in counts.items() if c >= THRESHOLD]


def observe(events_path: str) -> list:
    """一次观察：解析 → 累积 → 返回过阈值的触发候选。

    只观察不落笔（观察与落笔分轨，护栏三）。落笔由上层（BOBO_LEARN 触发）执行。
    """
    signals = parse_events(events_path)
    counts = accumulate(signals)
    return find_triggers(counts)
