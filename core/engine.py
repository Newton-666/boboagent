"""
core/engine.py - 主干调度器（集成教学模式）
"""

import sys
import os
import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple

# 将项目根目录加入 sys.path（基于当前文件位置推导）
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from tools import TOOLS_SCHEMA
from core.tool_executor import execute_tool
from core.skill_manager import get_skill_manager
from core.skill_executor import get_skill_executor


class Engine:
    # 状态常量
    STATE_IDLE = "idle"
    STATE_THINKING = "thinking"
    STATE_EXECUTING = "executing"
    STATE_RESPONDING = "responding"
    STATE_DONE = "done"
    STATE_ERROR = "error"

    # 最大步数限制（防止无限循环）
    MAX_STEPS = 30

    def __init__(self, llm_caller, tool_executor=None, callback: Callable = None, confirm_callback: Callable = None):
        self.llm_caller = llm_caller
        self.tool_executor = tool_executor or execute_tool
        self.callback = callback
        self.confirm_callback = confirm_callback
        self.history = []
        self.skills_dir = Path(__file__).parent.parent / "skills"
        self.system_prompt = self._build_system_prompt()
        
        # 教学模式
        self.teaching_mode = False
        self.recorded_messages = []
        self.current_skill_name = None
        
        self.skill_manager = get_skill_manager()
        self.skill_executor = get_skill_executor()

        # 状态机
        self.state = self.STATE_IDLE
        self.current_user_input = None
        self.current_depth = 0
        self.current_tool_round = 0
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0
    
    def _notify(self, event_type: str, data: dict):
        if self.callback:
            self.callback(event_type, data)
    
    def _confirm(self, tool_name: str, tool_args: dict, reason: str) -> bool:
        if self.confirm_callback:
            return self.confirm_callback(tool_name, tool_args, reason)
        return False
    
    def _build_system_prompt(self) -> str:
        return """你是Bobo,一个专业的智能助手.

核心规则:
- 用户问时间,距离,时长等问题 -> 直接回答,不要执行命令
- 用户要求搜索信息时 -> 使用 web_search 工具
- 用户要求写代码时 -> 使用 coding_master skill
- 用户要求文件操作时 -> 使用对应的工具
- 普通聊天 -> 直接回答

禁止使用 emoji,回答简洁专业."""
    
    def _handle_teaching_mode(self, user_input: str) -> Optional[str]:
        """处理教学模式命令"""
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
        """记录消息（教学模式）"""
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
        """检查是否匹配已保存的 Skill（需要执行意图）"""
        user_lower = user_input.lower()
        
        # 询问类关键词 - 不匹配 skill
        ask_keywords = ['right', '是吗', '对吗', '真的吗', '?', '？', '是不是', '能否', '可以吗', 'how', 'what', 'why', 'when', 'where']
        for kw in ask_keywords:
            if kw in user_lower:
                return None
        
        # 执行类关键词 - 匹配 skill
        execute_keywords = ['帮我', '请', '执行', '运行', '使用skill', '用skill', 'create', 'make', 'write', 'build']
        has_execute = any(kw in user_lower for kw in execute_keywords)
        
        if not has_execute:
            return None
        
        for skill_name in self.skill_manager.list_skills():
            if skill_name.lower() in user_lower:
                return skill_name
        return None

    # ──────────────────────────────────────────────
    # 新增：_handle_pre_input
    # ──────────────────────────────────────────────
    def _handle_pre_input(self, user_input: str) -> Optional[str]:
        """
        处理进入主循环前的特殊输入。
        
        按优先级依次检查：
        1. 教学模式命令（开始教学 / 保存为 skill / 取消教学）
        2. 是否匹配已保存的 Skill
        
        Args:
            user_input: 用户原始输入，可能为 None
            
        Returns:
            Optional[str]: 
                - 如果匹配特殊输入，返回响应内容（str），调用方应直接输出并终止本轮
                - 如果不匹配，返回 None，调用方应继续正常流程
        """
        if not user_input:
            return None

        # ── 优先级 1：教学模式命令 ──
        teaching_result = self._handle_teaching_mode(user_input)
        if teaching_result is not None:
            return teaching_result

        # ── 优先级 2：Skill 匹配（教学模式中不匹配 Skill） ──
        if self.teaching_mode:
            return None

        skill_name = self._check_skill_match(user_input)
        if skill_name is not None:
            skill = self.skill_executor.load_skill(skill_name)
            if skill is not None:
                self._notify("thinking", {
                    "phase": "using_skill",
                    "message": f"执行 Skill: {skill_name}"
                })
                result = self.skill_executor.execute_skill(skill)
                return result
            return None

        return None

    # ──────────────────────────────────────────────
    # 新增：_check_guards
    # ──────────────────────────────────────────────
    def _check_guards(self) -> bool:
        """
        检查递归深度和工具轮次是否超限。
        
        Returns:
            bool: True 表示超限，调用方应终止本轮处理
        """
        if self.current_tool_round > 5:
            self._notify("error", {
                "content": "工具调用次数过多，请简化问题"
            })
            return True

        if self.current_depth > 30:
            self._notify("error", {
                "content": "已达最大循环深度"
            })
            return True

        return False

    # ──────────────────────────────────────────────
    # 新增：_call_llm
    # ──────────────────────────────────────────────
    def _call_llm(self) -> Tuple[str, list]:
        """
        构造 messages、调用 LLM、解析响应、去 emoji。
        
        Returns:
            Tuple[str, list]: (content, tool_calls)
        """
        messages = [{"role": "system", "content": self.system_prompt}] + self.history

        self._notify("thinking", {
            "phase": "calling_llm",
            "message": "正在思考..."
        })

        response = self.llm_caller(messages)

        if isinstance(response, dict) and "error" in response:
            error_msg = f"错误: {response['error']}"
            error_type = response.get("error_type", "unknown")
            retryable = response.get("retryable", False)
            
            if retryable:
                error_msg = f"{error_msg}（已自动重试，仍失败）"
            
            self._notify("error", {
                "content": error_msg,
                "error_type": error_type
            })
            return error_msg, []

        content, tool_calls = self._extract_response(response)
        content = self._remove_emojis(content)

        return content, tool_calls

    # ──────────────────────────────────────────────
    # 新增：_append_to_history
    # ──────────────────────────────────────────────
    def _append_to_history(self, role: str, content: str = None,
                           tool_calls: list = None, tool_results: list = None):
        """
        统一管理 self.history 的追加操作，同时触发回调通知和教学模式记录。
        """
        if role == "user":
            msg = {"role": "user", "content": content}
            self.history.append(msg)
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

    # ──────────────────────────────────────────────
    # 新增：_execute_tool_loop
    # ──────────────────────────────────────────────
    def _execute_tool_loop(self, tool_calls: list) -> list:
        """
        遍历所有工具调用：高风险检查 → 用户确认 → 执行 → 记录结果。
        
        Returns:
            list[dict]: 工具执行结果列表
        """
        self._notify("thinking", {
            "phase": "executing_tools",
            "message": f"准备执行 {len(tool_calls)} 个工具"
        })

        tool_results = []
        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "")
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                tool_args = json.loads(args_str)
            except:
                tool_args = {}

            self._record_message("tool_call", tool_name=tool_name, args=tool_args)

            is_high_risk, reason = self._is_high_risk_tool(tool_name, tool_args)
            if is_high_risk:
                self._notify("confirm_request", {
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "reason": reason
                })
                confirmed = self._confirm(tool_name, tool_args, reason)
                if not confirmed:
                    self._notify("tool_cancelled", {
                        "name": tool_name,
                        "args": tool_args,
                        "reason": "用户取消"
                    })
                    tool_results.append({
                        "tool_call_id": tc.get("id", ""),
                        "role": "tool",
                        "content": f"操作已取消: {reason}"
                    })
                    continue

            self._notify("tool_call", {
                "name": tool_name,
                "args": tool_args,
                "status": "start"
            })
            start_time = time.time()
            result = self.tool_executor(tool_name, tool_args)
            duration = time.time() - start_time

            self._notify("tool_result", {
                "name": tool_name,
                "args": tool_args,
                "result": result[:200],
                "duration": duration,
                "success": not result.startswith("错误")
            })

            tool_results.append({
                "tool_call_id": tc.get("id", ""),
                "role": "tool",
                "content": result
            })

            self._record_message("tool_result", result=result[:200])

        return tool_results

    # ──────────────────────────────────────────────
    # 新增：_format_final_output
    # ──────────────────────────────────────────────
    def _format_final_output(self, content: str) -> str:
        """
        对最终输出做后处理：去表格、去重行。
        """
        if not content:
            return content

        lines = content.split('\n')
        cleaned = []
        in_table = False
        for line in lines:
            if line.strip().startswith('|'):
                in_table = True
                continue
            if in_table and line.strip() == '':
                in_table = False
                continue
            if not in_table:
                cleaned.append(line)
        content = '\n'.join(cleaned)

        lines = content.split('\n')
        seen = set()
        unique_lines = []
        for line in lines:
            line_stripped = line.strip()
            if line_stripped and line_stripped not in seen:
                seen.add(line_stripped)
                unique_lines.append(line)
            elif not line_stripped:
                unique_lines.append(line)
        content = '\n'.join(unique_lines)

        return content

    # ──────────────────────────────────────────────
    # 新增：_step — 单步执行
    # ──────────────────────────────────────────────
    def _step(self):
        """
        单步执行：根据当前状态执行一个步骤，然后更新状态。
        由 run() 循环调用，不递归。
        """
        if self.state == self.STATE_IDLE:
            # 处理特殊输入
            result = self._handle_pre_input(self.current_user_input)
            if result is not None:
                self._notify("complete", {"content": result})
                self.state = self.STATE_DONE
                return

            # 守卫检查
            if self._check_guards():
                self.state = self.STATE_ERROR
                return

            # 记录用户输入
            if self.current_user_input:
                self._append_to_history("user", self.current_user_input)

            self.state = self.STATE_THINKING

        elif self.state == self.STATE_THINKING:
            # 调用 LLM
            content, tool_calls = self._call_llm()
            self._pending_content = content
            self._pending_tool_calls = tool_calls

            if tool_calls:
                self.state = self.STATE_EXECUTING
            else:
                self.state = self.STATE_RESPONDING

        elif self.state == self.STATE_EXECUTING:
            # 执行工具
            tool_results = self._execute_tool_loop(self._pending_tool_calls)
            self._append_to_history("assistant", self._pending_content,
                                    tool_calls=self._pending_tool_calls)
            self._append_to_history("tool", tool_results=tool_results)

            self._notify("thinking", {
                "phase": "continuing",
                "message": "工具执行完成"
            })

            # 清空暂存
            self._pending_content = None
            self._pending_tool_calls = None

            # 继续下一轮
            self.current_depth += 1
            self.current_tool_round += 1
            self.state = self.STATE_THINKING

        elif self.state == self.STATE_RESPONDING:
            # 输出最终结果
            if self._pending_content:
                self._append_to_history("assistant", self._pending_content)
                content = self._format_final_output(self._pending_content)
                self._notify("complete", {"content": content})

            self._pending_content = None
            self.state = self.STATE_DONE

    # ──────────────────────────────────────────────
    # 新增：run — 循环入口
    # ──────────────────────────────────────────────
    def run(self, user_input: str = None, stream: bool = True, depth: int = 0, tool_round: int = 0):
        """
        主入口：循环调用 _step() 直到完成。
        
        与改造前的行为完全一致，但不再递归。
        内置步数限制，防止无限循环。
        """
        self.state = self.STATE_IDLE
        self.current_user_input = user_input
        self.current_depth = depth
        self.current_tool_round = tool_round
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0

        while self.state not in (self.STATE_DONE, self.STATE_ERROR):
            # 步数限制检查
            self._step_count += 1
            if self._step_count > self.MAX_STEPS:
                self._notify("error", {
                    "content": f"执行步骤超过上限（{self.MAX_STEPS}步），已自动终止"
                })
                self.state = self.STATE_ERROR
                break

            self._step()

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
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0
        self._notify("reset", {})
