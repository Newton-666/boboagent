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

    MAX_STEPS = 70

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
        self._verification_attempted = False  # 防止验证死循环
        self._checkpoints: list[dict] = []   # 对话回退快照
        self._interrupt_event: threading.Event | None = None
        self._recent_tool_calls: list[tuple[str, str]] = []  # (tool_name, args_key) for loop detection
        self._used_categories: set[str] = set()  # 边执行边扩张的工具分类
        self._phase_pending_cleanup: bool = False
        self._phase_summary: str = ""
        self._plan_reminded: bool = False

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

- 用户让你做简单的事时直接执行。复杂任务先列计划再逐步执行。
- **可以一次发送多个不冲突的编辑操作（edit_file/file_operation）。不冲突的判断标准：同时改不同文件是安全的，同时改同一文件的不同部分是安全的。如果两个编辑操作要改同一段代码，先改一个，结果返回后再改另一个。**
- **重要规则：单独的纯文字回复 = 任务结束。如果你还有工作要做，回复必须同时包含工具调用。不要只做"进度汇报"而不调工具。**
- 如果工具调用失败，尝试替代方案，不要编造结果。诚实报告阻塞比伪造输出好。
- 在完成任务之前，继续调用工具。不要提前停止。

## ⚡ 项目任务拆分（重要）

面对涉及多个文件或步骤的较大任务，请先识别需要拆分。

**判断标准**：如果满足以下任一条件，应当拆分为独立子任务：
- 涉及 **2 个以上**文件
- 预估需要 **超过 10 步**完成
- 需要跨不同类型工具（如先读文件、再改代码、再测试）

**优先使用 spawn_worker 拆分子任务**：将每个独立子任务派给一个 Worker。
- 每个 Worker 只做一个明确的子任务（如"调研方案"、"改文件 A"、"跑测试"）
- 给 Worker 起有意义的 name（如 "researcher"、"bug-fixer"），方便后续获取完整结果
- Worker 成功后返回轻量标记，需要详细结果可通过 read_worker_result 获取
- 简单任务（1-2 步、1 个文件）直接调工具即可，不需要 spawn

**连续步骤用 [PLAN] 管理**：如果一个子任务内部有多个连续步骤（如调研完成后必须马上写代码），用 `[PLAN]` 组织。
- `[PLAN]` 适用于单个 Worker 内部或简单任务的步骤管理
- 每完成一个阶段，说"阶段X完成"同时带上下一步的工具调用
- **注意**：说"阶段X完成"时必须同时带上下一步的工具调用。单独的文字汇报会被视为任务结束。

**简单任务**（1 个文件、几步就能完成）：直接执行，不需要规划阶段。

## 防循环规则（重要）

- **不要重复调用同一个工具读取同一个文件**。read_local_file 读一次就够了，内容不会变。
- 如果文件被截断了（输出末尾有"... (内容已截断，共 XXX 字符)"），用 offset+limit 分页继续读下一段。读完就停。
- grep_code 搜索一次就够了。如果无结果，换关键词或换搜索路径，不要原样重试。
- **最多连续调用同一个工具 3 次**。3 次后必须换方法或报告给用户。

## 对话规则

- 跟踪用户的原始目标。用户中途问别的问题时，回答完后回到原任务。
- 每次工具返回结果后，检查是否回答了用户的问题。如果没有，继续。
- 如果你需要更多信息才能继续，直接问用户。

## 记住指令

- 当用户说"记住"、"以后都这样"、"按此执行"等时，使用 save_memory 保存。
- 记忆会在每次对话时自动注入，让指令贯穿整个会话。

## 用户资料

- 当用户提供个人信息（名字、语言偏好、风格等）时，使用 save_memory(target="profile", memory_type="key") 保存。
- 用户资料与记忆分开存储，同样会在每次对话时自动注入。

## 可信度

- 工具失败时，尝试至少一种替代方法（web_search 超时就改 web_extract，grep 失败就改 os.walk）。
- 所有方法都失败时，直接告诉用户"我做不到"以及原因。不要假装成功。
- 每次声称完成时，提供具体证据（文件路径、返回值）。
- 删除、移动、重命名的文件会自动备份到回收站（~/.bobo/trash/），可用 restore_checkpoint 撤销。

## 技能

- [可参考的技能工作流] 是预设的工作路线参考，帮助你理解如何分解复杂任务。
- 技能不是硬编码步骤。根据用户实际环境和可用工具调整每个步骤的方法。
- 如果某个技能步骤不适合当前情况，用其他工具替代来实现相同目标。

## 创建技能

- 用户可以说"开始教学"来录制当前对话为技能。
- 录制完成后说"保存为 skill <名称>"，Bobo 会保存到 skills/ 目录。
- 用户也可以直接在 skills/ 目录编写 .yaml 文件。
- 个人技能保存在本地，不会提交到 GitHub（skills/*.yaml 已被 gitignore）。

## 工具并行

- 独立的操作（如搜索多个关键词）可以同时发送，不需要逐个等待。
- LLM 可以一次性发出多个工具调用，引擎会并行执行。

## 会话记忆

- 用户说"继续昨天的工作"、"接着上次的文件"时，先检查 [相关记忆] 中是否有记录。
- 如果记忆中没有，再搜索笔记库。
- 每完成一项主要工作，自动保存当前文件路径到记忆：save_memory("工作文件: <path>")。
- 这样下次继续时可以直接定位到文件，无需重新搜索。

## 代码修改工作流（重要）

- 修改已有代码 → **先用 grep_code 定位**，再用 **edit_file 精确替换**
  - edit_file 只能替换文件中恰好出现一次的文本
  - 如果 old_string 不唯一，加上前后 1-2 行作为额外上下文
  - grep_code 支持正则表达式，按文件类型过滤
- 创建新文件 → file_operation（action="write"）+ auto-run（写完自动运行）
- **修改代码后 → run_tests 验证**，测试失败 → grep_code 定位 → edit_file 修复 → run_tests 再次验证
- 代码变更尽量用 ```diff 格式展示（+ 新增行，- 删除行）

## 工具使用

- 代码搜索 → grep_code（正则搜索代码内容）
- 项目结构 → index_project（首次接触项目时建立代码索引，后续无需重复搜索结构）
- 精确改代码 → edit_file（字符串替换，不改整体架构）
- 创建新文件 → file_operation（action="write"）+ auto-run（写完自动运行）
- 搜索信息 → web_search / search_obsidian / cross_search
- 文件操作 → read_local_file / 对应工具
- 短内容写入（约 40000 字符以内）→ 用 write_obsidian（安全、有自动备份）
- 长内容写入（超过 40000 字符）→ 用 execute_terminal 的 cat / echo 命令（无大小限制）
- 时间/日期 → get_current_time
- 文件列表 → list_directory
- 普通聊天 → 直接回答

## 命令安全

- execute_terminal 的白名单命令（git, python, npm, ls, cat 等）静默执行，不需要确认
- 灰名单命令会弹窗让用户确认
- 高危操作（rm -rf, sudo, chmod 777, dd, 管道执行远程脚本）会被自动拦截
- 不要绕过分级：如果命令被拦截，尝试用白名单内的命令组合实现相同目标

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
        # 对话回退：支持自然语言和 /undo 命令
        undo_keywords = ["回退", "撤销", "撤销刚才", "回到上一步", "回到之前", "恢复上一步",
                         "undo", "revert", "go back"]
        if any(kw in user_input.lower() for kw in undo_keywords) and self._checkpoints:
            return self._do_undo()
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

    def _compress_changelog(self):
        """超过 20 条时压缩最早的条目为摘要"""
        if not hasattr(self, '_change_log') or len(self._change_log) <= 20:
            return
        keep = self._change_log[-10:]
        old = self._change_log[:-10]
        descs = '; '.join(m['desc'] for m in old if m.get('desc'))
        if len(descs) > 300:
            descs = descs[:200] + f"...（共 {len(old)} 次）"
        self._change_log = [{"ts": 0, "desc": f"[历史改动]: {descs}"}] + keep
        if len(self._change_log) > 50:
            self._change_log = self._change_log[-20:]

    def _check_guards(self) -> bool:
        # 循环检测：同一搜索类工具调用超过3次，注入停止提示
        if len(self._recent_tool_calls) >= 3:
            name_count = {}
            for name, _ in self._recent_tool_calls[-8:]:
                name_count[name] = name_count.get(name, 0) + 1
            search_tools = {'web_search', 'web_fetch', 'web_extract', 'search_code',
                           'search_obsidian', 'grep_code'}
            search_count = sum(name_count.get(t, 0) for t in search_tools)
            if search_count >= 3:
                self._append_to_history("user",
                    "提示: 搜索次数过多，请基于已有信息直接整理答案返回，不要再调用搜索工具。")
                self.current_depth += 1
                self._recent_tool_calls.clear()
                return False
            # 按目标检测重复：提取工具调用的搜索目标（文件路径/搜索模式）
            # 不依赖工具名，LLM 换工具名也能检测到
            import json as _jl
            targets = []
            for name, arg in self._recent_tool_calls[-8:]:
                desc = arg[:40]
                if name in ("read_local_file", "edit_file", "file_operation"):
                    try:
                        a = _jl.loads(arg) if isinstance(arg, str) else arg
                        desc = a.get("file_path", "") or a.get("path", "") or desc[:30]
                    except Exception:
                        pass
                targets.append(desc)
            target_counts = {}
            for t in targets:
                target_counts[t] = target_counts.get(t, 0) + 1
            # 如果有 >=3 次指向同一个文件或搜索内容
            for t, c in target_counts.items():
                if t and c >= 3:
                    self._append_to_history("user",
                        f"注意: 你已多次 [{t}] 相关操作（{c} 次）。如果之前的结果不理想，"
                        f"请换一种策略或直接告知用户无法完成，不要重复尝试相同方向。")
                    self.current_depth += 1
                    self._recent_tool_calls.clear()
                    return False
        # 步骤预算渐进提醒
        if self.current_depth == 35:
            self._append_to_history("user", "提示: 你已执行 35 步，剩余步骤预算约一半。注意合理分配，不必着急收尾。")
            self.current_depth += 1
            return False
        if self.current_depth == 45:
            self._append_to_history("user", "提示: 还剩 5 步，请尽快完成当前操作并生成回复。")
            self.current_depth += 1
            return False

        if self.current_tool_round > 90:
            # 达上限时请求总结，而不是直接报错
            summary = (
                "你已达到最大工具调用轮次上限。请提供最终回复，"
                "总结你已完成的内容，不需要再调用工具。"
            )
            self._append_to_history("user", summary)
            self.current_depth += 1
            return False  # let LLM respond with summary
        if self.current_depth > 200:
            self._notify("error", {"content": "已达最大循环深度"})
            return True
        return False

    # ── 阶段管理与上下文交接 ──────────────────────────────────────────

    _PHASE_COMPLETE_PATTERNS = [
        r"阶段\s*[\w\d]+\s*完成",  # "阶段1完成" — LLM 实际完成一个阶段后输出
        r"进入阶段",
        r"开始阶段",
    ]

    def _is_phase_complete(self, text: str) -> bool:
        """检测 LLM 回复是否包含阶段完成信号"""
        import re
        for pattern in self._PHASE_COMPLETE_PATTERNS:
            if re.search(pattern, text, re.DOTALL):
                return True
        return False

    def _extract_phase_summary(self, text: str) -> str:
        """从 LLM 回复中提取阶段摘要（取最后一段自然段落）"""
        import re
        # 尝试取 [PLAN] 之间的内容作为下一阶段计划
        plan_m = re.search(r"\[PLAN\](.*?)\[/PLAN\]", text, re.DOTALL)
        next_plan = f"\n### 下一阶段计划\n{plan_m.group(1).strip()}" if plan_m else ""

        # 去掉 [PLAN] 标记后取原文最后 800 字作为摘要
        clean = re.sub(r"\[/?PLAN\].*?\[?/PLAN\]?", "", text, flags=re.DOTALL).strip()
        summary = clean[-800:] if len(clean) > 800 else clean
        return f"[阶段完成摘要]\n{summary}{next_plan}"

    def _handle_phase_transition(self):
        """在阶段边界清理上下文：删工具结果，注入摘要"""
        # 1. 提取最后一轮 assistant 回复中的摘要
        summary = ""
        for m in reversed(self.history):
            if m.get("role") == "assistant" and m.get("content"):
                summary = self._extract_phase_summary(m["content"])
                break

        if not summary:
            return

        # 2. 删掉所有 tool 消息和 assistant 消息中的 tool_calls
        new_history = []
        for m in self.history:
            if m.get("role") == "tool":
                continue  # 删掉工具结果
            if m.get("role") == "assistant":
                m = {k: v for k, v in m.items() if k != "tool_calls"}  # 保留文本，删调用记录
            new_history.append(m)
        self.history = new_history

        # 3. 清空缓存
        self._read_files = {}
        self._recent_tool_calls = []
        self._change_log = []

        # 4. 注入阶段摘要（放在 history 开头，紧接系统 prompt）
        self.history.insert(0, {"role": "system", "content": summary})

    # ── 对话回退 ──────────────────────────────────────────────────────

    MAX_CHECKPOINTS = 20

    def _save_checkpoint(self, label: str = ""):
        """保存当前对话状态快照，用于回退。"""
        import copy, os as _os
        files = {}
        for path, content in self._file_checkpoints.items():
            if _os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as _f:
                        files[path] = _f.read()
                except Exception:
                    files[path] = content
        self._checkpoints.append({
            "label": label or f"step_{self.current_depth}",
            "history": copy.deepcopy(self.history),
            "files": files,
            "depth": self.current_depth,
            "tool_round": self.current_tool_round,
        })
        # 只保留最近 N 个快照
        if len(self._checkpoints) > self.MAX_CHECKPOINTS:
            self._checkpoints = self._checkpoints[-self.MAX_CHECKPOINTS:]

    def _find_checkpoint(self, target: str = "") -> int | None:
        """查找快照索引。支持数字（回退 N 步）、关键词匹配 label、默认回退 1 步。"""
        if not self._checkpoints:
            return None
        if not target:
            return len(self._checkpoints) - 2  # 回退到倒数第二个（恢复一步）
        # 数字
        try:
            steps = int(target)
            idx = len(self._checkpoints) - 1 - steps
            return max(0, idx)
        except ValueError:
            pass
        # 关键词
        for i in range(len(self._checkpoints) - 1, -1, -1):
            if target.lower() in self._checkpoints[i]["label"].lower():
                return i
        return None

    def _do_undo(self, target: str = "") -> str:
        """执行回退，返回给用户的消息。"""
        if not self._checkpoints:
            return "没有可回退的操作。"
        idx = self._find_checkpoint(target)
        if idx is None:
            return f"未找到匹配的快照: {target}"

        cp = self._checkpoints[idx]
        # 恢复 history
        self.history = cp["history"]
        # 恢复文件
        restored = []
        import os as _os
        for path, content in cp.get("files", {}).items():
            try:
                _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding="utf-8") as _f:
                    _f.write(content)
                restored.append(_os.path.basename(path))
            except Exception:
                pass
        # 恢复状态
        self.current_depth = cp["depth"]
        self.current_tool_round = cp["tool_round"]
        self._pending_content = None
        self._pending_tool_calls = None
        # 截断后续快照
        self._checkpoints = self._checkpoints[:idx + 1]

        label = cp["label"]
        file_info = f"\n文件已恢复: {', '.join(restored)}" if restored else ""
        self._notify("status.update", {
            "kind": "undo",
            "text": f"已回退到: {label}{file_info}",
        })
        return f"已回退到: {label}{file_info}\n\n要继续对话吗？"

    def _call_llm(self) -> Tuple[str, list]:

        # 阶段交接清理：在当前 LLM 调用前清理上一阶段的上下文
        if self._phase_pending_cleanup:
            self._handle_phase_transition()
            self._phase_pending_cleanup = False

        # 首次工具调用后提醒 LLM 规划阶段（避免自指问题）
        if not self._plan_reminded and self._step_count >= 1:
            has_plan = any("[PLAN]" in str(m.get("content", "")) for m in self.history)
            if not has_plan:
                self.history.insert(0, {
                    "role": "system",
                    "content": "注意：如果这个任务还需要多个工具调用才能完成，请先输出带 [PLAN] 的阶段计划。每个阶段完成后说'阶段X完成'。如果只是简单任务，直接继续即可。"
                })
                self._plan_reminded = True

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
            diff_preview = self._pending_diff[:4000]
            messages.insert(1, {
                "role": "system",
                "content": (
                    f"[代码变更 — 请审查以下 diff 是否有 bug、安全风险或性能问题:]\n"
                    f"{diff_preview}\n\n"
                    f"审查要点:\n"
                    f"1. 逻辑错误（拼写错误、条件反转、off-by-one）\n"
                    f"2. 安全风险（注入、硬编码密钥、权限问题）\n"
                    f"3. 性能问题（不必要的循环、重复计算、N+1 查询）\n"
                    f"4. 代码风格（与项目其他部分不一致的命名/格式）\n\n"
                    f"发现问题后如实报告，使用 review_diff 工具可查看完整 diff。"
                )
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
                user_text = (self.current_user_input or "").lower()
                matched = []
                others = []
                for s in skill_refs:
                    name = s["function"]["name"].replace("run_skill:", "")
                    desc = s["function"]["description"]
                    triggers = s.get("triggers", [])
                    if triggers and any(t.lower() in user_text for t in triggers):
                        matched.append(f"  ▶ {name}: {desc}")
                        # 注入匹配 skill 的完整步骤 → LLM 直接可见，不需调工具
                        try:
                            skill_data = _skill_mgr.get_skill(name)
                            if skill_data and skill_data.get("steps"):
                                step_lines = []
                                for st in skill_data["steps"]:
                                    sn = st.get("name", "")
                                    sa = st.get("action", "")
                                    si = st.get("step", "")
                                    if sn or sa:
                                        step_lines.append(f"    {si}. {sn}: {sa[:200]}")
                                if step_lines:
                                    matched.append("\n".join(step_lines))
                        except Exception:
                            pass
                    else:
                        others.append(f"  {name}: {desc[:100]}")
                lines = []
                if matched:
                    lines.append("[推荐技能 — 当前场景可用]:")
                    lines.extend(matched)
                    if others:
                        lines.append("")
                        lines.append("[其他技能]:")
                        lines.extend(others)
                else:
                    lines.append("[可参考的技能工作流]:")
                    lines.extend(others)
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
 
        # 注入用户资料（始终注入）
        try:
            from tools.v5_memory import format_user_profile, format_all_memory
            user_profile = format_user_profile()
            if user_profile:
                messages.insert(1, {
                    "role": "system",
                    "content": user_profile
                })
            # 注入全部记忆（最新 5000 字符，类似 Hermes 的快照方式）
            if not self._compressing:
                all_mem = format_all_memory(max_chars=5000)
                if all_mem and "记忆 (0/0" not in all_mem:
                    messages.insert(1, {
                        "role": "system",
                        "content": all_mem
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

        # 注入改动日志和已读文件摘要
        if hasattr(self, '_change_log') and self._change_log:
            items = self._change_log[-5:]
            lines = ["[本会话的改动记录]:", ""]
            for it in items:
                lines.append(f"  {it['desc']}")
            if len(self._change_log) > 5:
                lines.append(f"  ...（共 {len(self._change_log)} 次改动）")
            messages.insert(1, {"role": "system", "content": "\n".join(lines)})
        if hasattr(self, '_read_files') and self._read_files:
            items = list(self._read_files.items())[-3:]
            lines = ["[最近读过的文件]:", ""]
            for fpath, preview in items:
                short = preview[:120].replace('\n', ' ').strip()
                lines.append(f"  {fpath}: {short}...")
            messages.insert(1, {"role": "system", "content": "\n".join(lines)})

        self._notify("thinking", {"phase": "calling_llm", "message": "正在思考..."})

        def _on_token(token: str):
            self._notify("thinking.delta", {"text": token})

        def _on_retry(message: str, delay: float):
            self._notify("status.update", {
                "kind": "rate_limit",
                "text": f"API {message}，{int(delay)} 秒后重试...",
            })

        filtered_tools = self._get_filtered_tools(extra_categories=self._used_categories)
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
            detail = response.get("detail", "")
            full_msg = f"{error_msg} — {detail[:500]}" if detail else error_msg
            self._notify("error", {"content": full_msg, "error_type": error_type})
            # Non-retryable errors (400, 401, etc) — stop the session
            if not retryable:
                self.state = self.STATE_ERROR
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
            msg = {"role": "assistant"}
            if content:
                msg["content"] = content
            else:
                msg["content"] = None
            if tool_calls:
                msg["tool_calls"] = tool_calls
            self.history.append(msg)
            self._record_message("assistant", content=content)
        elif role == "system":
            self.history.append({"role": "system", "content": content})
        elif role == "tool" and tool_results:
            self.history.extend(tool_results)

    # ── 命令安全分级 ──

    # 白名单：日常安全命令，静默执行
    SAFE_COMMANDS = {
        "git", "ls", "cat", "echo", "python", "python3", "node", "npm", "npx",
        "pip", "pip3", "cd", "pwd", "mkdir", "cp", "mv", "grep", "find", "head",
        "tail", "wc", "curl", "wget", "du", "df", "whoami", "date", "env",
        "which", "man", "diff", "sort", "uniq", "touch", "file", "stat",
        "less", "more", "clear", "history", "type", "uname", "hostname",
        "go", "cargo", "rustc", "make", "cmake", "docker", "ps", "top",
        "tree", "xargs", "awk", "sed", "tr",
        "open",   # macOS: open apps/files/URLs
        "kill", "killall", "pgrep", "pkill",
        "osascript",    # macOS AppleScript automation
        "say",          # macOS text-to-speech
        "pbcopy", "pbpaste",  # macOS clipboard
        "screencapture", "sips",  # macOS screenshot / image
        "mdfind", "mdls", "mdutil",  # macOS Spotlight
        "launchctl", "defaults",  # macOS launch services / prefs
        "sw_vers", "system_profiler", "sysctl", "nettop",  # macOS system info
        "plutil", "pmset", "tmutil",  # macOS plist / power / time machine
        "diskutil", "hdiutil",  # macOS disk (read-only safe)
        "security", "codesign",  # macOS keychain / signing
        "ditto", "rsync",  # macOS file copy
    }

    # 黑名单：永远阻止的高危模式
    DANGEROUS_PATTERNS = [
        (r'rm\s+(-[rRf]|--recursive|--force)', "递归删除文件"),
        (r'sudo\s+', "提权操作"),
        (r'(chmod|chown)\s+.*777', "开放全部权限"),
        (r'>\s*/dev/(sd[a-z]+|disk\d+|nvme\d+n\d+|mmcblk\d+)', "直接写入磁盘设备"),
        (r'\bdd\s+if=', "磁盘镜像操作"),
        (r'mkfs\.', "格式化文件系统"),
        (r':\(\)\s*\{', "fork 炸弹"),
        (r'>\s*/etc/(passwd|shadow|sudoers|hosts)', "修改系统关键文件"),
        (r'(shutdown|reboot|halt|poweroff)', "系统关机/重启"),
        (r'curl.*\|\s*(ba)?sh', "管道执行远程脚本"),
        (r'wget.*\|\s*(ba)?sh', "管道执行远程脚本"),
        (r'git\s+push\s+.*--force', "强制推送"),
        (r'(scp|rsync|nc|netcat)\s+.*:', "远程文件传输/网络连接"),
        (r'\$\(', "命令替换注入 ($(...))"),
        (r'`[^`]+`', "反引号命令替换"),
        (r'curl.*\$\(', "curl + 命令替换"),
        (r'wget.*\$\(', "wget + 命令替换"),
    ]

    def _classify_command(self, command: str) -> tuple[str, str]:
        """分类命令：safe / dangerous / gray。返回 (等级, 原因)。

        检查优先级：
          1. 黑名单正则（全字符串匹配，拦截已知危险模式）
          2. 管道分段检查（每段独立判定，防止白名单命令夹带危险管道）
          3. 白名单（单命令，base_cmd 命中即安全）
          4. 灰名单（兜底，需用户确认）
        """
        if not command or not command.strip():
            return ("safe", "")

        cmd_clean = command.strip()
        base_cmd = cmd_clean.split()[0] if cmd_clean.split() else ""

        import re as _re

        # ── 第 1 步：全字符串黑名单 ──
        for pattern, reason in self.DANGEROUS_PATTERNS:
            if _re.search(pattern, cmd_clean):
                return ("dangerous", reason)

        # ── 第 2 步：管道分段检查 ──
        # 必须在白名单检查之前执行，否则 "ls | unknown_cmd"
        # 会以 "ls" 命中白名单而跳过后续管道的安全检查。
        if "|" in cmd_clean:
            for segment in cmd_clean.split("|"):
                seg = segment.strip()
                seg_cmd = seg.split()[0] if seg.split() else ""
                if not seg_cmd:
                    continue
                # 每段先过黑名单
                for pattern, reason in self.DANGEROUS_PATTERNS:
                    if _re.search(pattern, seg):
                        return ("dangerous", f"管道中的危险操作 — {reason}: {seg[:60]}")
                # 再检查白名单
                if seg_cmd in self.SAFE_COMMANDS:
                    continue
                # 不在白名单也不在黑名单 → 灰名单
                return ("gray", f"管道中包含未知命令: {seg_cmd}")
            # 所有段都通过 → 安全
            return ("safe", "")

        # ── 第 3 步：单命令白名单 ──
        if base_cmd in self.SAFE_COMMANDS:
            return ("safe", "")

        # ── 第 4 步：灰名单兜底 ──
        return ("gray", f"未知安全等级的命令: {base_cmd}")

    def _is_high_risk_tool(self, tool_name: str, tool_args: dict) -> Tuple[bool, str]:
        if tool_name == "execute_terminal":
            command = tool_args.get("command", "")
            level, reason = self._classify_command(command)
            if level == "dangerous":
                return True, f"🚫 危险操作 — {reason}: {command[:60]}"
            if level == "gray":
                return True, f"执行终端命令: {command[:60]}"
            # safe — 静默执行，不需要确认
            return False, ""

        if tool_name in ["delete_note", "move_note", "rename_note", "delete_folder"]:
            return True, f"文件操作: {tool_name}"

        # shell.exec RPC 方法始终需要确认（来自 TUI 直接输入）
        if tool_name == "shell.exec":
            command = tool_args.get("command", "")
            level, reason = self._classify_command(command)
            if level == "dangerous":
                return True, f"🚫 危险操作 — {reason}: {command[:60]}"
            return True, f"执行终端命令: {command[:60]}"

        return False, ""

    def _remove_emojis(self, text: str) -> str:
        emojis = ['😊', '🎉', '✅', '❌', '👍', '👋', '🙏', '💡', '📝', '🔍', '📂', '🏷️', '⚙️', '🔧', '📧', '📅', '⏰', '💾', '🔄', '✨', '🔥', '💪', '🤔', '🧠', '💭']
        for em in emojis:
            text = text.replace(em, '')
        return text

    def _needs_verification(self, content: str) -> bool:
        """Check if the LLM's response needs verification."""
        # 移除 round 限制，所有轮次都检测（第二里程碑修复）
        # Check for completion claims without tool evidence
        completion_markers = ["已完成", "已经完成", "已创建", "已写入",
                              "done", "finished", "created", "written",
                              "fixed", "已修复", "已修改", "已添加", "已删除",
                              "完成", "阶段"]
        text_lower = content.lower()
        for marker in completion_markers:
            if marker.lower() in text_lower:
                return True
        return False

    def _append_verification_note(self):
        """Inject a verification note asking the LLM to confirm its work."""
        note = (
            "[验证] 你声称完成了操作，但本轮没有调用任何工具。\n"
            "如果你确实完成了，请提供具体证据（文件路径、返回值、截图等）。\n"
            "如果你实际上没有执行操作，请如实告知用户。\n"
            "如果你需要重新执行，请使用对应的工具。"
        )
        self._append_to_history("system", note)

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
        # _check_guards 移到最外层，每个 step 都检查，防止无限循环
        if self._check_guards():
            self.state = self.STATE_ERROR
            return

        if self.state == self.STATE_IDLE:
            result = self._handle_pre_input(self.current_user_input)
            if result is not None:
                self._notify("complete", {"content": result})
                self.state = self.STATE_DONE
                return
            if self.current_user_input:
                self._append_to_history("user", self.current_user_input)
            self.state = self.STATE_THINKING
        elif self.state == self.STATE_THINKING:
            content, tool_calls = self._call_llm()
            self._pending_content = content
            self._pending_tool_calls = tool_calls
            if tool_calls:
                # 工具执行前保存快照，用于回退
                tool_names = [tc.get("function", {}).get("name", "") for tc in tool_calls]
                self._save_checkpoint(f"调用: {', '.join(tool_names[:3])}")
                self.state = self.STATE_EXECUTING
            else:
                # flash model sometimes returns empty — retry once
                if not content and not self._pending_tool_calls and self.current_depth < 2:
                    self._pending_content = None
                    self._pending_tool_calls = None
                    self.current_depth += 1
                    self.state = self.STATE_THINKING  # retry
                # 检查是否需要验证：LLM 声称完成但没有使用任何工具
                elif content and self._needs_verification(content) and not self._verification_attempted:
                    self._verification_attempted = True
                    self._append_to_history("assistant", content)
                    self._append_verification_note()
                    self._pending_content = None
                    self._pending_tool_calls = None
                    self.current_depth += 1
                    self.state = self.STATE_THINKING
                else:
                    self.state = self.STATE_RESPONDING
        elif self.state == self.STATE_EXECUTING:
            # 冲突检测：检查多个编辑操作是否要改同一文件的同一段
            if self._pending_tool_calls and len(self._pending_tool_calls) > 1:
                edit_tools = {"edit_file", "file_operation"}
                edits_by_file = {}
                conflicts = []
                for tc in self._pending_tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    if name in edit_tools:
                        try:
                            import json as _je
                            args = _je.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments", ""), str) else fn.get("arguments", {})
                            path = args.get("file_path", "") or args.get("path", "")
                            old_start = args.get("old_string", "")[:50] if name == "edit_file" else ""
                            if path:
                                if path in edits_by_file and edits_by_file[path]:
                                    conflicts.append(f"{path}（被多个编辑操作命中）")
                                edits_by_file[path] = edits_by_file.get(path, 0) + 1
                        except Exception:
                            pass
                if conflicts:
                    msg = f"检测到编辑冲突: {'; '.join(conflicts)}。请调整计划，先改一个文件，结果返回后再改另一个。"
                    self._append_to_history("assistant", msg)
                    self._pending_content = None
                    self._pending_tool_calls = None
                    self.current_depth += 1
                    self.state = self.STATE_THINKING
                    return

            tool_results = self._execute_tool_loop(self._pending_tool_calls)
            self._append_to_history("assistant", self._pending_content,
                                    tool_calls=self._pending_tool_calls)
            self._append_to_history("tool", tool_results=tool_results)
            # 检测阶段完成信号
            if self._pending_content and self._is_phase_complete(self._pending_content):
                self._phase_pending_cleanup = True
            # 记录工具调用用于循环检测
            if self._pending_tool_calls:
                for tc in self._pending_tool_calls:
                    name = tc.get("function", {}).get("name", "")
                    args = str(tc.get("function", {}).get("arguments", ""))[:60]
                    self._recent_tool_calls.append((name, args))
                self._recent_tool_calls = self._recent_tool_calls[-12:]
                # 边执行边扩张：根据实际调用的工具名，把对应分类加入已启用集合
                for tc in self._pending_tool_calls:
                    n = tc.get("function", {}).get("name", "")
                    for cat, tools in self.TOOL_CATEGORIES.items():
                        if n in tools:
                            self._used_categories.add(cat)
            # 记录改动日志
            if name in ("edit_file", "file_operation"):
                try:
                    import json as _je
                    a = _je.loads(tc.get("function", {}).get("arguments", "{}"))
                    fpath = a.get('file_path', '') or a.get('path', '')
                    if fpath:
                        if not hasattr(self, '_change_log'):
                            self._change_log = []
                        if name == "edit_file":
                            old = a.get("old_string", "")[:40]
                            new = a.get("new_string", "")[:40]
                            desc = f"{fpath}: {old} → {new}"
                        else:
                            desc = f"{fpath}（{a.get('action','write')}）"
                        self._change_log.append({"ts": time.time(), "desc": desc})
                except Exception:
                    pass
            # 记录已读文件，便于上下文压缩后恢复
            if name == "read_local_file":
                try:
                    import json as _j
                    a = _j.loads(args) if isinstance(args, str) else args
                    fpath = a.get('file_path', '') or a.get('path', '')
                    if fpath and tool_results and len(str(tool_results)) > 40:
                        if not hasattr(self, '_read_files'):
                            self._read_files = {}
                        self._read_files[fpath] = str(tool_results)[:200]
                        if len(self._read_files) > 10:
                            self._read_files = dict(list(self._read_files.items())[-10:])
                        # Track last step for this file
                        if not hasattr(self, '_file_last_step'):
                            self._file_last_step = {}
                        self._file_last_step[fpath] = self.current_depth
                except Exception:
                    pass
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
                self._notify("thinking", {"phase": "continuing", "message": "步骤已用完，正在生成最终回复..."})
                self.state = self.STATE_RESPONDING
                break
            if self._step_count >= 50 and self._step_count % 5 == 0:
                self._notify("thinking", {"phase": "continuing",
                    "message": f"已用 {self._step_count}/{self.MAX_STEPS} 步"})
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
        self._recent_tool_calls = []
        self._used_categories = set()
        self._plan_reminded = False
        self._file_checkpoints.clear()
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0
        self._all_confirmed = False
        self._verification_attempted = False
        self._checkpoints.clear()
        self._notify("reset", {})
