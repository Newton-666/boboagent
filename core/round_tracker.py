"""回合后处理追踪器 — 从 engine.py 抽离的 change_log / read_files / pattern tracker。

Usage:
    engine.tracker = RoundTracker(engine)
    engine.tracker.record_tool_round(pending_tool_calls, tool_results, tc_names)
    engine.tracker.maybe_propose_skill()
"""

import os
import json
import time
import logging

logger = logging.getLogger(__name__)


class RoundTracker:
    def __init__(self, engine):
        self._engine = engine
        self._change_log: list = []
        self._read_files: dict[str, str] = {}
        self._file_last_step: dict[str, int] = {}

    # ── change_log ──────────────────────────────────────────────────────

    def compress_changelog(self):
        if len(self._change_log) <= 20:
            return
        keep = self._change_log[-10:]
        old = self._change_log[:-10]
        descs = '; '.join(m['desc'] for m in old if m.get('desc'))
        if len(descs) > 300:
            descs = descs[:200] + f"...（共 {len(old)} 次）"
        self._change_log = [{"ts": 0, "desc": f"[历史改动]: {descs}"}] + keep
        if len(self._change_log) > 50:
            self._change_log = self._change_log[-20:]

    def log_change(self, desc: str):
        self._change_log.append({"ts": time.time(), "desc": desc})

    def recent_changes(self, limit: int = 5) -> list:
        return self._change_log[-limit:]

    # ── read_files ──────────────────────────────────────────────────────

    def record_read(self, fpath: str, content: str):
        if fpath and content and len(content) > 40:
            self._read_files[fpath] = content[:200]
            if len(self._read_files) > 10:
                self._read_files = dict(list(self._read_files.items())[-10:])
            self._file_last_step[fpath] = self._engine.current_depth

    def recent_reads(self, limit: int = 3) -> list[tuple[str, str]]:
        items = list(self._read_files.items())[-limit:]
        return [(fp, preview[:120].replace('\n', ' ').strip()) for fp, preview in items]

    # ── pattern tracker ────────────────────────────────────────────────

    def _pattern_tracker_path(self) -> str:
        try:
            from config import BOBO_DATA_DIR
            return str(BOBO_DATA_DIR / "pattern_tracker.json")
        except Exception:
            return ""

    def _load_patterns(self) -> dict:
        path = self._pattern_tracker_path()
        if not path or not os.path.exists(path):
            return {"patterns": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"patterns": {}}

    def _save_patterns(self, data: dict):
        path = self._pattern_tracker_path()
        if not path:
            return
        import tempfile, shutil as _sh
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp', prefix='.pt_')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            _sh.move(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    def record_tool_pattern(self, tool_names: list, user_input: str = ""):
        if not tool_names or len(tool_names) < 2:
            return
        seen = set()
        unique = []
        for t in tool_names:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        if len(unique) < 2:
            return
        sig = " → ".join(unique)
        data = self._load_patterns()
        entry = data.setdefault("patterns", {}).get(sig, {
            "count": 0, "first_seen": None, "last_seen": None,
            "example_topics": [], "proposed": False,
        })
        entry["count"] += 1
        today = time.strftime("%Y-%m-%d")
        entry["last_seen"] = today
        if not entry.get("first_seen"):
            entry["first_seen"] = today
        if user_input and len(entry.get("example_topics", [])) < 5:
            topic = user_input[:80]
            if topic not in entry["example_topics"]:
                entry.setdefault("example_topics", []).append(topic)
        data["patterns"][sig] = entry
        self._save_patterns(data)

    def maybe_propose_skill(self):
        data = self._load_patterns()
        for sig, entry in data.get("patterns", {}).items():
            if entry.get("count", 0) >= 3 and not entry.get("proposed"):
                count = entry["count"]
                examples = "、".join(entry.get("example_topics", [])[:3] or ["相关任务"])
                proposal = (
                    f"[Bobo 注意到] 我观察到你最近 {count} 次对话中"
                    + f"重复了相似的操作流程：\n"
                    + f"  {sig}\n"
                    + f"  例子：{examples}\n\n"
                    + f"这看起来像一个可复用的工作流。要不要我把它保存为一个 skill？"
                    + f"以后你说对应的触发词我就会自动按这个流程来执行。\n"
                    + f"回复“好”来创建，或“不用”来跳过。"
                )
                self._engine._append_to_history("system", proposal)
                entry["proposed"] = True
                data["patterns"][sig] = entry
                self._save_patterns(data)
                break

    # ── retroactive marking ─────────────────────────────────────────────

    def retroactive_mark(self):
        from core.tool_runner import _build_result_summary
        import hashlib, json as _mj
        history = self._engine.history
        workspace_dir = self._engine.WORKSPACE_DIR
        tool_positions = [i for i, m in enumerate(history) if m.get("role") == "tool"]
        if len(tool_positions) < 10:
            return
        cutoff = tool_positions[-10]
        for idx in range(cutoff):
            msg = history[idx]
            if msg.get("role") != "tool":
                continue
            content = msg.get("content", "")
            if not content or len(content) < 500 or content.startswith("[RESULT]"):
                continue
            marker_id = f"retro_{idx}_{hashlib.sha256(content.encode()).hexdigest()[:8]}"
            summary = _build_result_summary("tool", content)
            os.makedirs(workspace_dir, exist_ok=True)
            import tempfile
            fd, tmp = tempfile.mkstemp(dir=workspace_dir, suffix='.json', prefix='.rs_')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    _mj.dump({"tool": "tool", "args": "{}", "content": content}, f, ensure_ascii=False)
                import shutil
                shutil.move(tmp, os.path.join(workspace_dir, f"{marker_id}.json"))
                history[idx]["content"] = (
                    f"[RESULT] tool\n  → {summary}\n  → id: {marker_id}, {len(content)} chars"
                )
            except Exception:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
