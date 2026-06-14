"""Engine — 核心对话调度器（集成教学模式）"""

import sys
import os
import json
import re
import time
import threading
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
        self._interrupt_event: threading.Event | None = None

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
        return """你是 Bobo，一个专业的个人智能助手。

## 核心原则

- 用户让你做某事时，直接执行，不要只给计划或描述。完成后再报告结果。
- 如果工具调用失败，尝试替代方案，不要编造结果。诚实报告阻塞比伪造输出好。
- 在完成任务之前，继续调用工具。不要提前停止。

## 对话规则

- 跟踪用户的原始目标。用户中途问别的问题时，回答完后回到原任务。
- 每次工具返回结果后，检查是否回答了用户的问题。如果没有，继续。
- 如果你需要更多信息才能继续，直接问用户。

## 记住指令

- 当用户说"记住"、"以后都这样"、"按此执行"等时，使用 save_memory 保存。
- 记忆会在每次对话时自动注入，让指令贯穿整个会话。

## 用户资料

- 当用户提供个人信息（名字、偏好、语言、风格）时，使用 bobo_profile 保存。
- 用户资料会在每次对话时自动注入，立即可用。

## 可信度

- 工具失败时，尝试至少一种替代方法（web_search 超时就改 web_extract，grep 失败就改 os.walk）。
- 所有方法都失败时，直接告诉用户"我做不到"以及原因。不要假装成功。
- 每次声称完成时，提供具体证据（文件路径、返回值）。

## 技能

- [可参考的技能工作流] 是预设的工作路线参考，帮助你理解如何分解复杂任务。
- 技能不是硬编码步骤。根据用户实际环境和可用工具调整每个步骤的方法。
- 如果某个技能步骤不适合当前情况，用其他工具替代来实现相同目标。

## 工具使用

- 搜索信息 → web_search / search_obsidian / cross_search
- 写代码 → file_writer + auto-run（写完自动运行）
- 文件操作 → read_local_file / 对应工具
- 普通聊天 → 直接回答

## 输出格式

- 代码用 markdown 代码块包裹，标明语言
- 代码变更用 ```diff 标注 +/- 行
- 表格用 markdown 格式
- 不要使用 emoji，回答简洁专业"""



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
        """Skills are now tools (run_skill:xxx). No keyword matching needed."""
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

        # 验证提示：如果最近一次回复声称完成但没有工具调用证据，提醒 LLM
        if messages and messages[-1].get("role") == "tool":
            # 前一条是工具结果，LLM 即将生成回复 — 让它意识到需要基于真实结果回答
            pass  # 工具结果本身已经提供了足够的上下文

        # 注入技能作为参考工作流（指导而非自动化）
        try:
            from tools import _skill_mgr
            skill_refs = _skill_mgr.get_skill_tools()
            if skill_refs:
                lines = ["[可参考的技能工作流]:"]
                for s in skill_refs:
                    name = s["function"]["name"]
                    desc = s["function"]["description"]
                    lines.append(f"  {name.replace('skill_', '')}: {desc[:100]}")
                messages.insert(1, {
                    "role": "system",
                    "content": "\n".join(lines)
                })
        except Exception:
            pass

        # 注入已注册的自定义 API 列表
        apis_dir = os.path.expanduser("~/.bobo/apis")
        if os.path.isdir(apis_dir):
            apis = []
            for fname in sorted(os.listdir(apis_dir)):
                if fname.endswith(".json"):
                    try:
                        with open(os.path.join(apis_dir, fname)) as f:
                            cfg = json.load(f)
                        eps = [ep.get("name", "?") for ep in cfg.get("endpoints", [])]
                        apis.append(f"{cfg.get('name', fname)} ({', '.join(eps)})")
                    except Exception:
                        pass
            if apis:
                messages.insert(1, {
                    "role": "system",
                    "content": "[已注册的自定义 API]:\n" + "\n".join(apis)
                })
 
        # 注入相关记忆（本地 JSON 搜索，~5ms）
        user_query = self.current_user_input or ""
        if user_query and not self._compressing:
            try:
                from tools.v5_memory import search_knowledge_base, format_user_profile
                # User profile (injected every call)
                user_profile = format_user_profile()
                if user_profile:
                    messages.insert(1, {
                        "role": "system",
                        "content": user_profile
                    })
                # Memory search
                mem_result = search_knowledge_base(user_query)
                if mem_result and "未找到" not in mem_result:
                    messages.insert(1, {
                        "role": "system",
                        "content": f"[相关记忆]:\n{mem_result[:1000]}"
                    })
            except Exception:
                pass

        # 注入 AGENTS.md（来自 Obsidian vault 的项目规则）
        try:
            import os as _os
            vault = _os.environ.get("OBSIDIAN_VAULT", "")
            if vault:
                agents_path = _os.path.join(vault, "AGENTS.md")
                if _os.path.isfile(agents_path):
                    with open(agents_path, encoding="utf-8") as _f:
                        agents_content = _f.read(4000)
                    if agents_content.strip():
                        messages.insert(1, {
                            "role": "system",
                            "content": f"[项目规则 (AGENTS.md)]:\n{agents_content}"
                        })
        except Exception:
            pass

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
            # 检查中断信号
            if getattr(self, '_interrupt_event', None) and self._interrupt_event.is_set():
                self._notify("error", {"content": "用户中断了操作"})
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
        self._file_checkpoints.clear()
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0
        self._all_confirmed = False
        self._notify("reset", {})
