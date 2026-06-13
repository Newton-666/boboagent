"""Engine — 核心对话调度器（集成教学模式）"""

import sys
import os
import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from tools import TOOLS_SCHEMA
from core.tool_executor import execute_tool
from core.skill_manager import get_skill_manager
from core.skill_executor import get_skill_executor
from core.context import ContextMixin
from core.tool_runner import ToolRunnerMixin


class Engine(ContextMixin, ToolRunnerMixin):
    STATE_IDLE = "idle"
    STATE_THINKING = "thinking"
    STATE_EXECUTING = "executing"
    STATE_RESPONDING = "responding"
    STATE_DONE = "done"
    STATE_ERROR = "error"

    MAX_STEPS = 30

    def __init__(self, llm_caller, tool_executor=None, callback: Callable = None,
                 confirm_callback: Callable = None, test_mode: bool = False):
        self.llm_caller = llm_caller
        self.tool_executor = tool_executor or execute_tool
        self.callback = callback
        self.confirm_callback = confirm_callback
        self.test_mode = test_mode or ('pytest' in sys.modules)
        self.history = []
        self.skills_dir = Path(__file__).parent.parent / "skills"
        self.system_prompt = self._build_system_prompt()

        self.teaching_mode = False
        self.recorded_messages = []
        self.current_skill_name = None

        self.skill_manager = get_skill_manager()
        self.skill_executor = get_skill_executor()

        self.state = self.STATE_IDLE
        self.current_user_input = None
        self.current_depth = 0
        self.current_tool_round = 0
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0
        self._all_confirmed = False
        self._compressing = False
        self._tool_failures: dict[str, int] = {}
        self._last_usage: dict = {}
        self._pending_diff: str = ""

    def _notify(self, event_type: str, data: dict):
        if self.callback:
            self.callback(event_type, data)

    def _confirm(self, tool_name: str, tool_args: dict, reason: str) -> bool:
        if self.test_mode:
            return True
        if self._all_confirmed:
            return True
        if self.confirm_callback:
            result = self.confirm_callback(tool_name, tool_args, reason)
            if result == "all":
                self._all_confirmed = True
                return True
            return result
        return False

    def _build_system_prompt(self) -> str:
        return """你是Bobo,一个专业的智能助手.

核心规则:
- 用户问时间,距离,时长等问题 -> 直接回答,不要执行命令
- 用户要求搜索信息时 -> 使用 web_search 工具
- 用户要求写代码时 -> 使用 coding_master skill
- 用户要求文件操作时 -> 使用对应的工具
- 普通聊天 -> 直接回答

输出格式:
- 代码必须用 markdown 代码块包裹，标明语言，如 ```python```javascript
- 展示代码变更时使用 ```diff 并标注 +/- 行（绿色=新增，红色=删除）
- 表格用 markdown 表格格式

禁止使用 emoji,回答简洁专业."""

    def _handle_teaching_mode(self, user_input: str) -> Optional[str]:
        if user_input == "开始教学":
            self.teaching_mode = True
            self.recorded_messages = []
            return "📝 进入教学模式，我会记录接下来的对话。完成后说'保存为 skill <名称>'"
        if user_input.startswith("保存为 skill"):
            parts = user_input.replace("保存为 skill", "").strip().split()
            if not parts:
                return "请指定 skill 名称，例如: 保存为 skill 我的技能"
            skill_name = parts[0]
            desc = " ".join(parts[1:]) if len(parts) > 1 else ""
            result = self.skill_executor.save_from_recording(skill_name, self.recorded_messages, desc)
            self.teaching_mode = False
            self.recorded_messages = []
            return result
        if user_input == "取消教学":
            self.teaching_mode = False
            self.recorded_messages = []
            return "教学模式已取消"
        return None

    def _record_message(self, role: str, content: str = None, tool_name: str = None, args: dict = None, result: str = None):
        if not self.teaching_mode:
            return
        msg = {"role": role, "timestamp": time.time()}
        if content:
            msg["content"] = content
        if tool_name:
            msg["name"] = tool_name
            msg["args"] = args
        if result:
            msg["result"] = result
        self.recorded_messages.append(msg)

    def _check_skill_match(self, user_input: str) -> Optional[str]:
        user_lower = user_input.lower()
        ask_keywords = ['right', '是吗', '对吗', '真的吗', '?', '？', '是不是', '能否', '可以吗', 'how', 'what', 'why', 'when', 'where']
        for kw in ask_keywords:
            if kw in user_lower:
                return None
        execute_keywords = ['帮我', '请', '执行', '运行', '使用skill', '用skill', 'create', 'make', 'write', 'build']
        has_execute = any(kw in user_lower for kw in execute_keywords)
        if not has_execute:
            return None
        for skill_name in self.skill_manager.list_skills():
            if skill_name.lower() in user_lower:
                return skill_name
        return None

    def _handle_pre_input(self, user_input: str) -> Optional[str]:
        if not user_input:
            return None
        teaching_result = self._handle_teaching_mode(user_input)
        if teaching_result is not None:
            return teaching_result
        if self.teaching_mode:
            return None
        skill_name = self._check_skill_match(user_input)
        if skill_name is not None:
            skill = self.skill_executor.load_skill(skill_name)
            if skill is not None:
                self._notify("thinking", {"phase": "using_skill", "message": f"执行 Skill: {skill_name}"})
                result = self.skill_executor.execute_skill(skill)
                return result
            return None
        return None

    def _check_guards(self) -> bool:
        if self.current_tool_round > 5:
            self._notify("error", {"content": "工具调用次数过多，请简化问题"})
            return True
        if self.current_depth > 30:
            self._notify("error", {"content": "已达最大循环深度"})
            return True
        return False

    def _call_llm(self) -> Tuple[str, list]:
        # 硬限制：超过上限的消息数，丢弃最早的消息
        if len(self.history) > self.MAX_HISTORY_MESSAGES:
            user_indices = [i for i, m in enumerate(self.history) if m.get("role") == "user"]
            target_first = len(self.history) - self.MAX_HISTORY_MESSAGES
            split = target_first
            for idx in user_indices:
                if idx >= target_first:
                    split = idx
                    break
            self.history = self.history[split:]

        # 字符预算检查
        if not self._compressing:
            total_chars = sum(len(str(m)) for m in self.history)
            if total_chars > self.MAX_HISTORY_CHARS:
                self._notify("thinking", {"phase": "compressing", "message": "正在压缩历史上下文..."})
                self._compress_history()

        messages = [{"role": "system", "content": self.system_prompt}] + self.history

        if self._pending_diff:
            messages.insert(1, {
                "role": "system",
                "content": f"[自上次调用以来的文件变更:]\n{self._pending_diff[:2000]}"
            })
            self._pending_diff = ""

        self._notify("thinking", {"phase": "calling_llm", "message": "正在思考..."})

        def _on_token(token: str):
            self._notify("thinking.delta", {"text": token})

        def _on_retry(message: str, delay: float):
            self._notify("status.update", {
                "kind": "rate_limit",
                "text": f"API {message}，{int(delay)} 秒后重试...",
            })

        filtered_tools = self._get_filtered_tools()
        if filtered_tools is not None:
            names = [t.get("function", {}).get("name", "") for t in filtered_tools]
            self._notify("thinking", {"phase": "tool_filter", "message": f"加载 {len(filtered_tools)} 个工具 ({', '.join(names)})"})

        response = self.llm_caller(
            messages,
            stream_callback=_on_token,
            retry_callback=_on_retry,
            tools_override=filtered_tools,
        )
        if isinstance(response, dict) and "error" in response:
            error_msg = f"错误: {response['error']}"
            error_type = response.get("error_type", "unknown")
            retryable = response.get("retryable", False)
            if retryable:
                error_msg = f"{error_msg}（已自动重试，仍失败）"
            self._notify("error", {"content": error_msg, "error_type": error_type})
            return error_msg, []
        self._last_usage = response.get("usage", {})
        content, tool_calls = self._extract_response(response)
        content = self._remove_emojis(content)
        return content, tool_calls

    def _append_to_history(self, role: str, content: str = None,
                           tool_calls: list = None, tool_results: list = None):
        if role == "user":
            self.history.append({"role": "user", "content": content})
            self._notify("user_input", {"content": content})
            self._record_message("user", content=content)
        elif role == "assistant":
            msg = {"role": "assistant", "content": content or ""}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            self.history.append(msg)
            self._record_message("assistant", content=content)
        elif role == "tool" and tool_results:
            self.history.extend(tool_results)

    def _is_high_risk_tool(self, tool_name: str, tool_args: dict) -> Tuple[bool, str]:
        if tool_name == "execute_terminal":
            command = tool_args.get("command", "")
            dangerous_patterns = [r'rm\s+(-rf?|--recursive)\s+', r'sudo\s+', r'chmod\s+777\s+']
            for pattern in dangerous_patterns:
                if re.search(pattern, command):
                    return True, f"危险命令: {command[:50]}"
            return True, f"执行终端命令"
        if tool_name in ["delete_note", "move_note", "rename_note", "delete_folder"]:
            return True, f"文件操作: {tool_name}"
        return False, ""

    def _remove_emojis(self, text: str) -> str:
        emojis = ['😊', '🎉', '✅', '❌', '👍', '👋', '🙏', '💡', '📝', '🔍', '📂', '🏷️', '⚙️', '🔧', '📧', '📅', '⏰', '💾', '🔄', '✨', '🔥', '💪', '🤔', '🧠', '💭']
        for em in emojis:
            text = text.replace(em, '')
        return text

    def _extract_response(self, response) -> tuple:
        try:
            if isinstance(response, dict):
                choice = response.get("choices", [{}])[0]
                message = choice.get("message", {})
                content = message.get("content", "")
                tool_calls = message.get("tool_calls", [])
                return content, tool_calls
            if hasattr(response, 'choices') and response.choices:
                message = response.choices[0].message
                content = message.content or ""
                tool_calls = message.tool_calls or []
                return content, tool_calls
            return str(response), []
        except Exception as e:
            return f"解析失败: {str(e)}", []

    def _step(self):
        if self.state == self.STATE_IDLE:
            result = self._handle_pre_input(self.current_user_input)
            if result is not None:
                self._notify("complete", {"content": result})
                self.state = self.STATE_DONE
                return
            if self._check_guards():
                self.state = self.STATE_ERROR
                return
            if self.current_user_input:
                self._append_to_history("user", self.current_user_input)
            self.state = self.STATE_THINKING
        elif self.state == self.STATE_THINKING:
            content, tool_calls = self._call_llm()
            self._pending_content = content
            self._pending_tool_calls = tool_calls
            if tool_calls:
                self.state = self.STATE_EXECUTING
            else:
                self.state = self.STATE_RESPONDING
        elif self.state == self.STATE_EXECUTING:
            tool_results = self._execute_tool_loop(self._pending_tool_calls)
            self._append_to_history("assistant", self._pending_content,
                                    tool_calls=self._pending_tool_calls)
            self._append_to_history("tool", tool_results=tool_results)
            self._notify("thinking", {"phase": "continuing", "message": "工具执行完成"})
            self._pending_content = None
            self._pending_tool_calls = None
            self.current_depth += 1
            self.current_tool_round += 1
            self.state = self.STATE_THINKING
        elif self.state == self.STATE_RESPONDING:
            if self._pending_content:
                self._append_to_history("assistant", self._pending_content)
                content = self._format_final_output(self._pending_content)
                self._notify("complete", {"content": content, "usage": self._last_usage})
            else:
                self._notify("complete", {"content": "（没有生成回复内容）"})
            self._pending_content = None
            self.state = self.STATE_DONE

    def run(self, user_input: str = None, stream: bool = True, depth: int = 0, tool_round: int = 0):
        self.state = self.STATE_IDLE
        self.current_user_input = user_input
        self.current_depth = depth
        self.current_tool_round = tool_round
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0
        self._all_confirmed = False

        if self.history and not self._compressing:
            total_chars = sum(len(str(m)) for m in self.history)
            if total_chars > self.MAX_HISTORY_CHARS:
                self._compress_history()

        while self.state not in (self.STATE_DONE, self.STATE_ERROR):
            self._step_count += 1
            if self._step_count > self.MAX_STEPS:
                self._notify("error", {"content": f"执行步骤超过上限（{self.MAX_STEPS}步），已自动终止"})
                self.state = self.STATE_ERROR
                break
            self._step()

    def reset(self):
        self.history = []
        from tools.file_operation import clear_cache
        clear_cache()
        self.teaching_mode = False
        self.recorded_messages = []
        self.state = self.STATE_IDLE
        self.current_user_input = None
        self.current_depth = 0
        self.current_tool_round = 0
        self._tool_failures = {}
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0
        self._all_confirmed = False
        self._notify("reset", {})
