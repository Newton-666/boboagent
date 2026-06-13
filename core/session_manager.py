"""
core/session_manager.py - 会话管理（支持多人协作）
"""

import json
import os
import getpass
from datetime import datetime
from pathlib import Path


class SessionManager:
    def __init__(self, session_dir: str = None, author: str = None):
        if session_dir:
            self.session_dir = Path(session_dir)
        else:
            default_dir = os.environ.get("BOBO_SESSION_DIR",
                                         str(Path.home() / ".bobo_v2" / "sessions"))
            self.session_dir = Path(default_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.author = author or getpass.getuser()
        self.current_session_id = None
        self.current_session = None

    def new_session(self, title: str = None) -> str:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = self.session_dir / f"{session_id}.json"
        session = {
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "title": title or f"会话_{session_id}",
            "messages": [],
            "summary": None
        }
        self._write_atomic(session_path, session)
        self.current_session_id = session_id
        self.current_session = session
        self.add_system_message(f"{self.author} 加入了会话")
        return session_id

    def rename_session(self, title: str):
        """重命名当前会话"""
        if self.current_session:
            self.current_session["title"] = title[:50]
            self._save()

    def list_sessions(self, limit: int = 10) -> list:
        sessions = []
        for p in self.session_dir.glob("*.json"):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    created = data.get("created_at", "")[:16]
                    sessions.append({
                        "id": data["id"],
                        "title": data.get("title", data["id"])[:35],
                        "created_at": created,
                        "message_count": len(data.get("messages", []))
                    })
            except:
                continue
        return sorted(sessions, key=lambda x: x["created_at"], reverse=True)[:limit]

    def load_session(self, session_id: str):
        session_path = self.session_dir / f"{session_id}.json"
        if not session_path.exists():
            return None
        with open(session_path, 'r', encoding='utf-8') as f:
            session = json.load(f)
        self.current_session_id = session_id
        self.current_session = session
        return session

    def add_message(self, role: str, content: str):
        if self.current_session:
            msg = {
                "role": role,
                "content": content,
                "author": self.author,
                "timestamp": datetime.now().isoformat()
            }
            self.current_session["messages"].append(msg)
            user_msgs = [m for m in self.current_session["messages"] if m["role"] == "user"]
            if len(user_msgs) == 1:
                preview = user_msgs[0]["content"][:30]
                self.current_session["title"] = preview + ("..." if len(preview) >= 30 else "")
            self._save()

    def add_system_message(self, content: str):
        if self.current_session:
            self.current_session["messages"].append({
                "role": "system",
                "content": content,
                "author": "system",
                "timestamp": datetime.now().isoformat()
            })
            self._save()

    def get_message_count(self) -> int:
        if self.current_session:
            return len(self.current_session.get("messages", []))
        return 0

    def get_new_messages(self, since_index: int) -> list:
        if not self.current_session:
            return []
        messages = self.current_session.get("messages", [])
        if since_index >= len(messages):
            return []
        return messages[since_index:]

    def reload_session(self):
        if self.current_session_id:
            session_path = self.session_dir / f"{self.current_session_id}.json"
            if session_path.exists():
                with open(session_path, 'r', encoding='utf-8') as f:
                    self.current_session = json.load(f)

    def _write_atomic(self, path: Path, data: dict):
        """原子写入：先写 .tmp 文件，再 rename，避免写操作中断导致文件损坏"""
        tmp_path = path.with_suffix(".json.tmp")
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            # 写入 .tmp 失败，尝试直接写原文件
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return
        # 写入 .tmp 成功，原子替换原文件
        if path.exists():
            os.replace(path, path.with_suffix(".json.bak"))
        os.replace(tmp_path, path)

    def _save(self):
        if self.current_session and self.current_session_id:
            self._write_atomic(
                self.session_dir / f"{self.current_session_id}.json",
                self.current_session
            )
