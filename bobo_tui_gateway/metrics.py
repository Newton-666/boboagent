"""bobo_tui_gateway/metrics.py — COST-1b Token 消耗度量层（纯观测，只落盘）。

挂载点（全部在 gateway 转发层，core/ 零改动）：
  - server_utils.emit：message.start / tool.start / tool.complete / message.complete 事件
  - handlers/prompts.handle_prompt_submit：记录 user_prompt 长度（message.start 事件不带 prompt 内容）
每轮 message.complete 时合成一条结构化消耗日志，追加写 data/metrics/rounds.jsonl。

铁律（COST-1b 票面）：
  - 只观测、只落盘：零优化行为、零 prompt 改动、零调度改动
  - 字段全部来自真实事件流，取不到就落 null，禁止编造
  - 任何异常静默降级（event_bus 同款纪律），绝不影响主链路
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from config import BOBO_DATA_DIR

logger = logging.getLogger(__name__)

_METRICS_DIR = Path(BOBO_DATA_DIR) / "metrics"
_METRICS_PATH = _METRICS_DIR / "rounds.jsonl"
_EVENTS_PATH = Path(BOBO_DATA_DIR) / "logs" / "events.jsonl"

# 重复劳动侦测（本票最重要的一区）：read 类工具同 target 重复调用 count≥2 才列
_READ_TOOLS = {"read_local_file", "read_obsidian", "grep_code"}

# 单轮工具行上限：防止异常会话把单行 JSON 撑爆（观测数据，超限丢弃尾部）
_MAX_TOOLS_PER_ROUND = 200


def _tool_target(name: str, args: dict) -> str:
    """提取 read 类工具的 target（文件路径或 path+pattern），取不到返回 ''。"""
    args = args or {}
    if name == "read_local_file":
        return str(args.get("file_path") or args.get("filepath") or "")
    if name == "read_obsidian":
        return str(args.get("filename") or "")
    if name == "grep_code":
        p = str(args.get("path") or "")
        pat = str(args.get("pattern") or "")
        return (p + "::" + pat) if (p or pat) else ""
    return ""


class MetricsSink:
    """会话级轮次缓冲，message.complete 时合成 JSONL 行。

    线程安全；观测失败静默降级（绝不抛异常，绝不阻塞主链路）。
    """

    def __init__(self, metrics_path: str | Path | None = None, events_path: str | Path | None = None):
        self._metrics_path = Path(metrics_path) if metrics_path else _METRICS_PATH
        self._events_path = Path(events_path) if events_path else _EVENTS_PATH
        self._lock = threading.Lock()
        self._buf: dict[str, dict] = {}          # sid → 轮缓冲
        self._user_chars: dict[str, int] = {}    # sid → 最近一次用户输入长度
        self._branch_cache: str | None = None
        self._round_no: dict[str, int] = {}      # sid → 轮次号

    # ── 外部挂载点 ──

    def record_user_prompt(self, sid: str, text: str):
        """prompt.submit 时记录用户输入长度（转发层补字段，属兼容扩展）。"""
        try:
            with self._lock:
                self._user_chars[sid] = len(text or "")
        except Exception:
            pass

    def on_event(self, event_type: str, sid: str, payload: dict | None):
        """server_utils.emit 钩子：观测事件流，维护轮缓冲。"""
        try:
            payload = payload or {}
            if event_type == "message.start":
                self._begin_round(sid)
            elif event_type == "tool.start":
                self._tool_start(sid, payload)
            elif event_type == "tool.complete":
                self._tool_complete(sid, payload)
            elif event_type == "message.complete":
                self._finalize_round(sid, payload)
        except Exception:
            logger.debug("metrics sink error (silent)", exc_info=True)

    # ── 轮缓冲 ──

    def _begin_round(self, sid: str):
        with self._lock:
            n = self._round_no.get(sid, 0) + 1
            self._round_no[sid] = n
            self._buf[sid] = {
                "round": n,
                "t0": time.time(),
                "tools": [],          # {name, target, duration_ms, error}
                "read_counts": {},    # target → count（重复劳动侦测）
            }

    def _tool_start(self, sid: str, payload: dict):
        with self._lock:
            buf = self._buf.get(sid)
            if not buf:
                return
            name = str(payload.get("name") or "")
            args = payload.get("arguments") or {}
            buf["tools"].append({
                "name": name,
                "target": _tool_target(name, args),
                "duration_ms": None,
                "error": False,
            })
            tgt = _tool_target(name, args)
            if name in _READ_TOOLS and tgt:
                buf["read_counts"][tgt] = buf["read_counts"].get(tgt, 0) + 1

    def _tool_complete(self, sid: str, payload: dict):
        with self._lock:
            buf = self._buf.get(sid)
            if not buf or not buf["tools"]:
                return
            t = buf["tools"][-1]
            if str(payload.get("name") or "") == t["name"]:
                dur = payload.get("duration")
                t["duration_ms"] = int(float(dur) * 1000) if dur is not None else None
                t["error"] = bool(payload.get("error"))

    def _finalize_round(self, sid: str, payload: dict):
        with self._lock:
            buf = self._buf.get(sid)
            if not buf:
                return
            usage = payload.get("usage") or {}
            duration_ms = int((time.time() - buf["t0"]) * 1000)
            # usage 拆解：message.complete 的 usage 为 last_usage（input/output/total/context_*）；
            # DeepSeek 原名字段（prompt_tokens 等）若链路透传则优先取
            prompt_tokens = usage.get("prompt_tokens")
            if prompt_tokens is None:
                prompt_tokens = usage.get("input")
            completion_tokens = usage.get("completion_tokens")
            if completion_tokens is None:
                completion_tokens = usage.get("output")
            user_chars = self._user_chars.pop(sid, None)
            tools = buf["tools"][:_MAX_TOOLS_PER_ROUND]
            repeat_reads = [
                {"target": t, "count": c}
                for t, c in sorted(buf["read_counts"].items(), key=lambda kv: -kv[1])
                if c >= 2
            ]
            row = {
                "ts": time.time(),
                "session_id": sid,
                "round": buf["round"],
                "branch": self._branch(),
                "ticket": self._ticket(),
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
                    "cache_miss_tokens": usage.get("prompt_cache_miss_tokens"),
                    "user_prompt_chars": user_chars,
                },
                "budget": self._budget(sid),
                "tools": tools,
                "repeat_reads": repeat_reads,
                "duration_ms": duration_ms,
            }
            self._buf.pop(sid, None)
            self._append(row)

    # ── 元数据 ──

    def _branch(self) -> str | None:
        try:
            if self._branch_cache is None:
                r = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=3,
                )
                self._branch_cache = r.stdout.strip() or None
            return self._branch_cache
        except Exception:
            return None

    def _ticket(self) -> str | None:
        """TICKET-XXX 推断：优先 BOBO_TICKET 环境变量，其次分支名。推断不到落 null。"""
        try:
            env = os.environ.get("BOBO_TICKET", "")
            if env:
                return env
            br = self._branch()
            if br:
                m = re.search(r"(TICKET-[\w.-]+)", br, re.IGNORECASE)
                if m:
                    return m.group(1).upper()
            return None
        except Exception:
            return None

    # ── budget 映射（读 events.jsonl 最近同会话 prompt.budget）──

    def _budget(self, sid: str) -> dict:
        """四段口径映射（来源：prompt.budget 审计事件，禁止编造）：

        system     = sections 中除 memory/note_pointers 外各段 chars 之和（selfmap/now/guidance/office…）
        discipline = 顶层 discipline.chars（未注入为 0）
        memory     = sections.memory.chars
        pointers   = sections.note_pointers.chars
        取不到整条审计 → 全 null。
        """
        try:
            line = self._last_budget_line(sid)
            if line is None:
                return {"system": None, "discipline": None, "memory": None, "pointers": None}
            sections = line.get("sections") or {}
            sys_chars = 0
            for k, v in sections.items():
                if k in ("memory", "note_pointers"):
                    continue
                if isinstance(v, dict) and isinstance(v.get("chars"), int):
                    sys_chars += v["chars"]
            disc = line.get("discipline") or {}
            mem = sections.get("memory") or {}
            ptr = sections.get("note_pointers") or {}
            return {
                "system": sys_chars or None,
                "discipline": disc.get("chars") if isinstance(disc, dict) else None,
                "memory": mem.get("chars") if isinstance(mem, dict) else None,
                "pointers": ptr.get("chars") if isinstance(ptr, dict) else None,
            }
        except Exception:
            return {"system": None, "discipline": None, "memory": None, "pointers": None}

    def _last_budget_line(self, sid: str) -> dict | None:
        """从 events.jsonl 尾部倒找最近一条 type=prompt.budget 且 sid 匹配（只读尾部 512KB）。"""
        try:
            if not self._events_path.exists():
                return None
            size = self._events_path.stat().st_size
            read_size = min(size, 512 * 1024)
            with open(self._events_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(max(0, size - read_size))
                tail = f.read()
            for raw in reversed(tail.splitlines()):
                try:
                    ev = json.loads(raw)
                except Exception:
                    continue
                if ev.get("type") == "prompt.budget" and ev.get("sid") == sid:
                    return ev
            return None
        except Exception:
            return None

    # ── 落盘（JSONL 追加写，绝不覆盖）──

    def _append(self, row: dict):
        try:
            self._metrics_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(row, ensure_ascii=False, default=str, separators=(",", ":")) + "\n"
            with open(self._metrics_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            logger.debug("metrics append failed (silent)", exc_info=True)

    # ── 只读查询（metrics.read JSON-RPC 供 Telescope 消耗页签）──

    def read_recent(self, limit: int = 50, session_id: str = "") -> list[dict]:
        """读 rounds.jsonl 最近 N 条（新→旧）；损坏行跳过，失败返回 []。"""
        try:
            if not self._metrics_path.exists():
                return []
            rows = []
            with open(self._metrics_path, "r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rows.append(json.loads(raw))
                    except Exception:
                        continue
            if session_id:
                rows = [r for r in rows if r.get("session_id") == session_id]
            return rows[-limit:][::-1]
        except Exception:
            return []


metrics_sink = MetricsSink()
