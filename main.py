#!/usr/bin/env python3
"""
Bobo Agent - 主入口（带会话总结）
"""

import sys
import os
import json
import time
import re
import termios
import tty
import threading
from datetime import datetime
from pathlib import Path

try:
    import gnureadline as readline
except ImportError:
    import readline

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.engine import Engine
from core.tool_executor import execute_tool
from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA
from display import (
    print_separator, print_logo, print_assistant, print_step, print_tool,
    print_step_done, print_tree_end, print_session_box, print_help, print_tools_list
)

# 颜色常量
BRIGHT_YELLOW = '\033[93m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_BLACK = '\033[90m'
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_CYAN = '\033[96m'
BRIGHT_WHITE = '\033[97m'
RESET = '\033[0m'
BOLD = '\033[1m'


def get_key():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                if ch3 == 'A':
                    return 'UP'
                elif ch3 == 'B':
                    return 'DOWN'
                elif ch3 == 'C':
                    return 'RIGHT'
                elif ch3 == 'D':
                    return 'LEFT'
        return ch
    except:
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def clear_line():
    sys.stdout.write('\r\033[K')
    sys.stdout.flush()


def clear_screen():
    os.system('clear')


def get_terminal_width():
    try:
        return os.get_terminal_size().columns
    except:
        return 80


class LiveTimer:
    """计时器：只计时不打印，由 ThinkingUI 统一管理显示"""
    def __init__(self):
        self.seconds = 0
        self.running = False
        self.thread = None
    
    def start(self):
        self.seconds = 0
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
    
    def _run(self):
        while self.running:
            time.sleep(1)
            if self.running:
                self.seconds += 1
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
    
    @property
    def elapsed(self):
        return self.seconds


class SessionManager:
    def __init__(self):
        self.session_dir = Path.home() / ".bobo_v2" / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)
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
            "summary": None  # 缓存摘要
        }
        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
        self.current_session_id = session_id
        self.current_session = session
        return session_id
    
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
        """添加消息，不再按内容去重"""
        if self.current_session:
            self.current_session["messages"].append({
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat()
            })
            # 用第一条用户消息作为标题
            user_msgs = [m for m in self.current_session["messages"] if m["role"] == "user"]
            if len(user_msgs) == 1:
                preview = user_msgs[0]["content"][:30]
                self.current_session["title"] = preview + ("..." if len(preview) >= 30 else "")
            self._save()
    
    def _save(self):
        if self.current_session and self.current_session_id:
            with open(self.session_dir / f"{self.current_session_id}.json", 'w', encoding='utf-8') as f:
                json.dump(self.current_session, f, ensure_ascii=False, indent=2)


def show_session_selector(session_mgr):
    sessions = session_mgr.list_sessions(limit=10)
    display_sessions = [{"id": s["id"], "title": s["title"], "time": s["created_at"][5:10]} for s in sessions]
    
    if not display_sessions:
        return "new"
    
    selected = 0
    while True:
        clear_screen()
        print()
        print_logo()
        print_session_box(display_sessions, selected)
        print()
        key = get_key()
        if key == 'UP' and selected > 0:
            selected -= 1
        elif key == 'DOWN' and selected < len(display_sessions) - 1:
            selected += 1
        elif key == '\r' or key == '\n':
            return display_sessions[selected]["id"]
        elif key == 'n' or key == 'N':
            return "new"
        elif key == 'q' or key == 'Q':
            return None


def show_session_summary(session_mgr):
    """显示会话总结（带缓存）"""
    if not session_mgr.current_session:
        return
    
    messages = session_mgr.current_session.get("messages", [])
    if len(messages) < 2:
        return
    
    width = min(68, get_terminal_width() - 6)
    border = f"  {BRIGHT_BLACK}┌{'─' * width}┐{RESET}"
    bottom = f"  {BRIGHT_BLACK}└{'─' * width}┘{RESET}"
    
    print(border)
    print(f"  {BRIGHT_BLACK}│{RESET} {BRIGHT_YELLOW}📋 上次会话总结{RESET}{' ' * (width - 14)}{BRIGHT_BLACK}│{RESET}")
    
    # 检查是否有缓存的摘要
    cached_summary = session_mgr.current_session.get("summary")
    if cached_summary:
        lines = cached_summary
    else:
        # 进度条动画
        for i in range(8):
            bar = '█' * (i + 1) + '░' * (7 - i)
            print(f"  {BRIGHT_BLACK}│{RESET}   {BRIGHT_BLACK}{bar} 正在分析...{RESET}{' ' * (width - 24)}{BRIGHT_BLACK}│{RESET}")
            sys.stdout.write('\033[1A')
            time.sleep(0.06)
        
        # 清除进度行
        sys.stdout.write('\033[K')
        
        # 生成摘要
        llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, tools_schema=None)
        history_str = ""
        for msg in messages[-10:]:
            role = "用户" if msg['role'] == 'user' else "Bobo"
            content = msg['content'][:80].replace('\n', ' ')
            history_str += f"{role}: {content}\n"
        
        prompt = f"""根据对话用3-5个要点总结，每个要点用 - 开头，每条不超过25字。

{history_str}"""
        
        response = llm([{"role": "user", "content": prompt}], use_tools=False)
        summary = ""
        if isinstance(response, dict) and 'error' not in response:
            summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        lines = [line.strip() for line in summary.strip().split('\n') if line.strip() and line.startswith('-')]
        
        # 缓存摘要
        session_mgr.current_session["summary"] = lines
        session_mgr._save()
    
    # 显示摘要
    for line in lines:
        display = line[:width-6] if len(line) > width-6 else line
        print(f"  {BRIGHT_BLACK}│{RESET}   {display:<{width-4}}{BRIGHT_BLACK}│{RESET}")
        time.sleep(0.1)
    
    print(bottom)
    print()


def user_confirm(tool_name: str, tool_args: dict, reason: str) -> bool:
    """真正的交互式确认"""
    print(f"\n  {BRIGHT_YELLOW}⚠️ 高风险操作{RESET}")
    print(f"  {BRIGHT_BLACK}工具: {tool_name}{RESET}")
    print(f"  {BRIGHT_BLACK}原因: {reason}{RESET}")
    
    # 显示参数
    args_str = json.dumps(tool_args, ensure_ascii=False)[:100]
    print(f"  {BRIGHT_BLACK}参数: {args_str}{RESET}")
    
    while True:
        try:
            response = input(f"  {BRIGHT_YELLOW}是否允许？(y/n): {RESET}").strip().lower()
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                print(f"  {BRIGHT_BLACK}操作已取消{RESET}")
                return False
        except (KeyboardInterrupt, EOFError):
            print()
            return False


class ThinkingUI:
    def __init__(self):
        self.has_printed = False
        self.timer = LiveTimer()
    
    def on_engine_event(self, event_type, data):
        if event_type == "tool_call":
            name = data.get("name", "")
            args = data.get("args", {})
            query = args.get('query', args.get('command', str(args)))[:50]
            print(f"  {BRIGHT_BLACK}│{RESET}    {BRIGHT_CYAN}⚙ {name}{RESET} {BRIGHT_BLACK}({query}){RESET}")
        elif event_type == "tool_result":
            duration = data.get("duration", 0)
            success = data.get("success", False)
            result = data.get("result", "")
            print(f"  {BRIGHT_BLACK}│{RESET}      {BRIGHT_GREEN}✓{RESET} {BRIGHT_BLACK}done ({duration:.1f}s){RESET}")
            if result and len(result) < 100:
                print(f"  {BRIGHT_BLACK}│{RESET}        {result[:80]}")
        elif event_type == "complete":
            content = data.get("content", "")
            self.timer.stop()
            elapsed = self.timer.elapsed
            # 清除计时行
            clear_line()
            print(f"  {BRIGHT_YELLOW}├─ thinking ({elapsed}s){RESET}")
            print(f"  {BRIGHT_BLACK}│{RESET}")
            print(f"  {BRIGHT_BLACK}└─{RESET}")
            if not self.has_printed:
                print_assistant(content)
                self.has_printed = True
    
    def start_loop(self):
        self.has_printed = False
        self.timer.start()
        print(f"  {BRIGHT_YELLOW}├─ thinking (0s){RESET}")
        print(f"  {BRIGHT_BLACK}│{RESET}")
        print(f"  {BRIGHT_BLACK}│{RESET}  {BRIGHT_YELLOW}▶{RESET} 规划任务")


def main():
    session_mgr = SessionManager()
    choice = show_session_selector(session_mgr)
    
    if choice is None:
        clear_screen()
        print("\n  👋 再见！\n")
        return
    elif choice == "new":
        session_mgr.new_session()
        clear_screen()
        print_logo()
        print(f"  {BRIGHT_GREEN}✓{RESET} 新会话已创建")
        print()
    else:
        session_mgr.load_session(choice)
        clear_screen()
        print_logo()
        print(f"  {BRIGHT_GREEN}✓{RESET} 已恢复会话")
        print()
        show_session_summary(session_mgr)
    
    print_separator()
    print(f"  {BRIGHT_BLACK}命令: /help | /exit | Ctrl+T{RESET}")
    print_separator()
    print()
    
    thinking_ui = ThinkingUI()
    llm_caller = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    engine = Engine(llm_caller, execute_tool, callback=thinking_ui.on_engine_event, confirm_callback=user_confirm)
    
    if session_mgr.current_session:
        engine.history = session_mgr.current_session.get("messages", [])
    
    while True:
        try:
            user_input = input("  [YOU] 你 > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  👋 再见！")
            break
        
        if not user_input:
            continue
        
        cmd = user_input.lower().strip()
        if cmd in ["/exit", "/quit", "exit", "quit"]:
            print("\n  👋 再见！")
            break
        if cmd == "/clear":
            clear_screen()
            print_logo()
            print_separator()
            continue
        if cmd == "/help":
            print_help()
            continue
        if cmd == "/tools":
            print_tools_list()
            continue
        
        session_mgr.add_message("user", user_input)
        print()
        print_separator()
        thinking_ui.start_loop()
        engine.run(user_input)
        if engine.history and engine.history[-1]["role"] == "assistant":
            session_mgr.add_message("assistant", engine.history[-1]["content"])
        print_separator()
        print()


if __name__ == "__main__":
    main()
