"""事件总线 MVP（Phase 1 — 只读观测，零行为变更）

bobo 的第二双眼睛：engine 关键动作以结构化事件追加写入 JSONL 账本。
只做产生+落盘，禁止任何消费。

三类事件：
  - llm.call    LLM 调用前后
  - tool.exec   工具执行前后
  - state.change Engine 状态机转换
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

from config import BOBO_DATA_DIR

logger = logging.getLogger("bobo.event_bus")

# ── 轮转配置 ──
_MAX_SIZE_BYTES = 10 * 1024 * 1024   # 10 MB
_MAX_BACKUPS = 3                       # 保留 3 代
_SINGLE_EVENT_MAX_CHARS = 500          # 单条事件上限（摘要+指针原则）

# 审计类事件放宽上限：预算记账（prompt.budget*）是结构化审计数据，必须完整落盘，
# 不能被"摘要+指针"原则以 payload_too_large 丢弃（票 GOV-1 修复：TICKET-GOV-1 终审打回，
# discipline 段曾把 prompt.budget 推过 500 导致整条事件被丢，审计缺失=违背记账语义）。
_AUDIT_EVENTS = ("prompt.budget", "prompt.budget.decision")
_AUDIT_MAX_CHARS = 2000                 # 审计事件单条上限（结构化记账户，含嵌套 sections）


def _truncate(text: str, max_chars: int) -> str:
    """截断文本到 max_chars，末尾加 … 标记。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


class EventBus:
    """线程安全的事件写入器。写失败静默降级，绝不抛异常影响主流程。"""

    _instance: "EventBus | None" = None

    def __new__(cls, log_dir: str = ""):
        # 默认路径返回模块单例；指定 log_dir 则创建独立实例（测试用）
        if log_dir:
            return super().__new__(cls)
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, log_dir: str = ""):
        # __new__ 返回单例时 __init__ 仍会调用；用 _ready 标志跳过重复初始化
        if getattr(self, "_ready", False):
            return
        self._lock = threading.Lock()
        if log_dir:
            self._log_dir = Path(log_dir)
        else:
            self._log_dir = Path(BOBO_DATA_DIR) / "logs"
        self._log_path = self._log_dir / "events.jsonl"
        self._ensure_dir()
        # 公开只读属性，方便测试/监控读取
        self.filepath = str(self._log_path)
        self._ready = True

    # ── 对外 API ──

    def write(self, event_type: str, data: dict):
        """写入一条事件。

        捕所有异常，绝不影响主流程（静默降级铁律）。
        所有截断在序列化前完成，保证 JSON 行 100% 可解析。
        """
        try:
            event = self._build_event(event_type, data)
            # 序列化前截断长文本字段（修复票 I：第 114 行断 JSON）
            self._truncate_fields(event)
            payload = json.dumps(event, ensure_ascii=False, default=str, separators=(",", ":"))
            # 仍超长 → 删除 bulk 字段，而不是切 JSON 字符串
            # 审计类事件（prompt.budget*）用放宽上限，不走丢弃路径
            limit = _AUDIT_MAX_CHARS if event_type in _AUDIT_EVENTS else _SINGLE_EVENT_MAX_CHARS
            if len(payload) > limit:
                event["_truncated"] = True
                for drop_key in ["args_summary", "result_summary", "error_detail"]:
                    event.pop(drop_key, None)
                payload = json.dumps(event, ensure_ascii=False, default=str, separators=(",", ":"))
                # 丢字段后还超长？放弃本条（但写一条标记替代，不写坏行）
                if len(payload) > limit:
                    payload = json.dumps({
                        "ts": time.time(), "type": "event_bus.dropped",
                        "session_id": event.get("session_id", ""),
                        "reason": "payload_too_large",
                    }, ensure_ascii=False, separators=(",", ":"))
            line = payload + "\n"
            with self._lock:
                self._rotate_if_needed()
                self._log_dir.mkdir(parents=True, exist_ok=True)
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception:
            logger.debug("event_bus write failed (silent)", exc_info=True)

    def _truncate_fields(self, event: dict):
        """序列化前截断超长字符串字段到 120 字符。"""
        for k, v in list(event.items()):
            if isinstance(v, str) and len(v) > 120:
                event[k] = v[:120] + "…"

    @classmethod
    def reset(cls, log_dir: str = ""):
        """重置单例指向，用于测试隔离。传入 log_dir 重定向输出路径。"""
        inst = cls._instance
        if inst is None:
            inst = cls.__new__(cls, log_dir)
            cls._instance = inst
            inst.__init__(log_dir)
        else:
            if log_dir:
                inst._log_dir = Path(log_dir)
            else:
                inst._log_dir = Path(BOBO_DATA_DIR) / "logs"
            inst._log_path = inst._log_dir / "events.jsonl"
            inst.filepath = str(inst._log_path)
            inst._ensure_dir()
        return inst

    # ── 内部 ──

    def _build_event(self, event_type: str, data: dict) -> dict:
        _data = data if isinstance(data, dict) else {}
        return {
            "ts": time.time(),
            "type": event_type,
            **_data,
        }

    def _ensure_dir(self):
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _rotate_if_needed(self):
        """文件超 10MB 时轮转，保留 3 代。"""
        try:
            path = self._log_path
            if not path.exists():
                return
            if path.stat().st_size < _MAX_SIZE_BYTES:
                return
            # 轮转: events.jsonl → events.jsonl.1 → events.jsonl.2 → events.jsonl.3(丢弃)
            for i in range(_MAX_BACKUPS, 0, -1):
                src = self._log_dir / f"events.jsonl.{i}"
                dst = self._log_dir / f"events.jsonl.{i + 1}"
                if i == _MAX_BACKUPS and dst.exists():
                    dst.unlink()
                if src.exists():
                    src.rename(dst)
            # 当前文件改名
            path.rename(self._log_dir / "events.jsonl.1")
        except Exception:
            # 轮转失败也不影响主流程
            pass


# ── 模块级单例 ──
event_bus = EventBus()
