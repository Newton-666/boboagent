"""ThinkingUI - 思考过程可视化"""

from ui.timer import LiveTimer
from ui.utils import (
    BRIGHT_YELLOW, BRIGHT_GREEN, BRIGHT_BLACK, BRIGHT_CYAN, RESET, clear_line
)
from display import print_assistant


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
