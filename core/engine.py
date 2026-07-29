"""Engine — 核心对话调度器（集成教学模式）"""

import sys
import os
import json
import re
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple

logger = logging.getLogger(__name__)

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from tools import TOOLS_SCHEMA, report_load_errors
from core.tool_executor import execute_tool
from core.skill_manager import get_skill_manager
from core.context import ContextMixin, clean_orphan_tool_calls
from core.event_bus import event_bus
from core.tool_runner import ToolRunnerMixin
from core.round_tracker import RoundTracker
from core.emoji_cleaner import remove_emojis
from core.command_safety import classify_command, is_high_risk_tool
from core.verifier import Verifier
from core.checkpoint import CheckpointManager
from core.skill_loader import SkillLoader
from core.proactive import ProactiveManager
from core.injector import PromptInjector

# ── 票 S：takeaway 预筛正则 ──
_TAKEAWAY_VALUE_KEYWORDS = re.compile(
    r'决定|以后|记住|偏好|喜欢|习惯|以后都|改成|不要再用|规则|流程|'
    r'选型|方案定|上线|部署|密码|密钥|配置'
)
_TAKEAWAY_CONFIRM_PATTERN = re.compile(
    r'^(好的|好|嗯|行|ok|OK|谢谢|继续|收到|对|是的?|可以的?)[。！!~\s]*$'
)

# ── 票 H：运行时孤儿防线工具函数 ──

def _is_tool_pairing_400(response: dict) -> bool:
    """判断 HTTP 400 错误是否由 tool_calls 配对断裂引起。

    只检查错误文本中的关键词，不解析 JSON body。
    非配对类 400（参数错误等）不匹配，不触发重试。
    """
    if response.get("error_type") != "bad_request":
        return False
    detail = response.get("detail", "")
    error_msg = response.get("error", "")
    combined = (detail + " " + error_msg).lower()
    pairing_keywords = [
        "tool_call_id",
        "messages with role 'tool' must be a response to a preceding message",
        "tool message must be preceded by",
        "requires a corresponding tool call",
    ]
    return any(kw.lower() in combined for kw in pairing_keywords)


class Engine(ContextMixin, ToolRunnerMixin):
    _tool_load_warning_shown = False  # 进程级：工具加载失败警告只打印一次

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
        # 会话标识：gateway 在 open_session 中设 self.sid；无会话时走时间戳兜底
        _now = time.time()
        self.sid = f"boot-{int(_now)}-{os.urandom(2).hex()}"
        self.skills_dir = Path(__file__).parent.parent / "skills"
        self.system_prompt = self._build_system_prompt()

        self.teaching_mode = False
        self.recorded_messages = []
        self.current_skill_name = None

        self.skill_manager = get_skill_manager()
        self.skill_executor = get_skill_manager()

        self.state = self.STATE_IDLE
        self.current_user_input = None
        self.current_depth = 0
        self.current_tool_round = 0
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0
        self._all_confirmed = False
        self._compressing = False
        self._compressed_this_turn = False  # 本轮已压缩过——不再触发
        self._tool_failures: dict[str, int] = {}
        self._last_usage: dict = {}
        self._pending_diff: str = ""
        self.verifier = Verifier()  # 防止验证死循环
        self.checkpoint_mgr = CheckpointManager(
            history_getter=lambda: self.history,
            file_checkpoints_getter=lambda: self._file_checkpoints,
            workspace_dir=getattr(self, 'WORKSPACE_DIR', ''),
        )
        self._file_checkpoints: dict[str, str] = {}  # path -> content before write（每实例独立）
        self.tracker = RoundTracker(self)  # 回合后处理（change_log / read_files / pattern）
        # ── 票 K v2：任务台账（收工闸核心） ──
        self.task_ledger: list[dict] = []  # [{"id":str, "title":str, "status":"pending"|"in_progress"|"done"}]
        self._ledger_reinject_count: int = 0  # 连续回注计数（硬熔断 2 次）
        self._last_reasoning: str = ""  # 票 P：上一轮 reasoning 思考过程（展示用，不进历史）
        self._interrupt_event: threading.Event | None = None
        self._recent_tool_calls: list[tuple[str, str]] = []  # (tool_name, args_key) for loop detection
        self._used_categories: set[str] = set()  # 边执行边扩张的工具分类
        self._phase_pending_cleanup: bool = False
        self._phase_summary: str = ""
        self._worker_reminded: bool = False
        # 主动模式管理器（含记忆连接 + 参与度追踪）
        self.proactive = ProactiveManager(llm_caller=self.llm_caller)
        # 技能标准加载器
        self.skill_loader = SkillLoader(lambda: self.history)
        # Prompt 注入管道
        self.injector = PromptInjector(self)

        # 启动时报告工具加载失败（每进程只打印一次，不注入 system prompt）
        if not Engine._tool_load_warning_shown:
            warning = report_load_errors()
            if warning:
                print(warning, file=sys.stderr)
                logger.warning(warning)
            Engine._tool_load_warning_shown = True

    def _notify(self, event_type: str, data: dict):
        if self.callback:
            self.callback(event_type, data)

    def _emit_state_change(self, to_state: str, reason: str = ""):
        """事件总线：状态变更。在 state 实际变更前调用。"""
        event_bus.write("state.change", {
            "session_id": getattr(self, "sid", ""),
            "from": self.state,
            "to": to_state,
            "reason": reason,
        })
        self.state = to_state

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
- Worker 成功后返回轻量标记 `[WORKER_COMPLETE:name]`，需要详细结果可通过 read_worker_result 获取
- 简单任务（1-2 步、1 个文件）直接调工具即可，不需要 spawn

**简单任务**（1 个文件、几步就能完成）：直接执行，不需要规划阶段。

## 工具结果标记

工具结果以 [RESULT:摘要] 格式呈现——完整性不会丢失，只是不默认占上下文。
如需查看完整结果，调 load_result(id, max_chars)。
所有结果完整保存在本地 `~/.bobo/workspace/`，不会丢失。

**决策指南**（看到标记时按以下逻辑判断）：
1. 摘要已经回答了你的问题 → 不需要加载，直接基于摘要回答
2. 你需要看到具体内容才能判断 → 调 load_result(id)，拉一次全文（12KB 左右，远低于传统 23KB）
3. 不确定 → 加载。猜错的代价（额外一轮）比猜对省下的上下文更贵

**原则**：标注结果不是限制你获取信息——它是"按需取回"。加载全文不会破坏上下文预算，
因为即便每次标记都加载，上下文仍然比不标记时少一半。拿不准就加载，不要犹豫。

## 防循环规则（重要）

- **不要重复调用同一个工具读取同一个文件**。read_local_file 读一次就够了，内容不会变。
- 如果文件被截断了（输出末尾有"... (内容已截断，共 XXX 字符)"），用 offset+limit 分页继续读下一段。读完就停。
- grep_code 搜索一次就够了。如果无结果，换关键词或换搜索路径，不要原样重试。
- **最多连续调用同一个工具 3 次**。3 次后必须换方法或报告给用户。

## 对话规则

- 跟踪用户的原始目标。用户中途问别的问题时，回答完后回到原任务。
- 每次工具返回结果后，检查是否回答了用户的问题。如果没有，继续。
- 如果你需要更多信息才能继续，直接问用户。

## 收工汇报（重要）

每个任务回合结束时，你的最后一条回复必须是简短的收工汇报，用自然的语言交底：
- **做完了什么**（一两句话，别罗列每个工具调用）
- **还剩什么 / 下一步等什么**（如果有未完成事项；有任务台账时对照台账说明）
- 全部完成就明确说"全部完成"，别含糊。

禁止以工具调用框或半截过程话收尾。纯闲聊回合（问候、确认、问答）不受此限，自然回复即可。

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

Bobo 的预设工作流标准（data/skill-standards/*/standard.md）在对话末尾自动注入。
当回复末尾出现"## 项目标准 — 以下规则优先级高于一切，违反即不合格"时，
说明当前话题命中了一个或多个预设工作流。你必须遵守标准中的状态机和禁止项。

你也可以录制自定义技能：
- 说"开始教学"来录制操作流程。
- 完成后说"保存为 skill <名称>"，Bobo 会保存到 data/skill-standards/ 目录。
- 个人技能保存在本地，不会提交到 GitHub。

## 工具并行

- 独立的操作（如搜索多个关键词）可以同时发送，不需要逐个等待。
- LLM 可以一次性发出多个工具调用，引擎会并行执行。

## 会话记忆

- 用户说"继续昨天的工作"、"接着上次的文件"时，先检查 [相关记忆] 中是否有记录。
- 如果记忆中没有，再搜索笔记库。
- 每完成一项主要工作，自动保存当前文件路径到记忆：save_memory("工作文件: <path>")。
- 这样下次继续时可以直接定位到文件，无需重新搜索。

## 代码修改工作流（重要）

- **做网页/前端项目直接写 HTML/CSS/JS 文件——不要用 Python 脚本生成 HTML。**
  你写的代码就是最终产品。不要绕一层中间脚本。
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
        # 每轮新用户消息到来时重置压缩标记
        self._compressed_this_turn = False
        # 主动模式：追踪用户是否在回应上轮连接提议
        self.proactive.track_engagement(user_input)
        teaching_result = self._handle_teaching_mode(user_input)
        if teaching_result is not None:
            return teaching_result
        # 对话回退：支持自然语言和 /undo 命令
        # 短关键词只做精确匹配，防止 "这个有回退机制吗" 误触发 undo（审计 #25）
        undo_exact = {"回退", "撤销", "undo", "revert", "go back", "/undo"}
        undo_substr = ["撤销刚才", "回到上一步", "回到之前", "恢复上一步"]
        stripped = user_input.strip().lower()
        if (stripped in undo_exact or any(kw in stripped for kw in undo_substr)) and self.checkpoint_mgr:
            success, msg, history, depth, tool_round, label = self.checkpoint_mgr.undo()
            if not success:
                return msg
            self.history = history
            self.current_depth = depth
            self.current_tool_round = tool_round
            self._pending_content = None
            self._pending_tool_calls = None
            # _notify 中的 file_info 已内嵌在 msg 内，此处复用 label 发通知
            self._notify("status.update", {"kind": "undo", "text": f"已回退到: {label}"})
            return msg
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
        self.tracker.compress_changelog()

    def _check_guards(self) -> bool:
        # 已移除 5 项不必要的护栏（2026-07-22 分析）：
        # - 搜索 ≥3 次注入停止提示 → 复杂任务天然需要多次搜索
        # - 同文件/搜索重复 ≥3 次 → 重读文件有合法理由
        # - current_depth 35/45 步提醒 → LLM 无法理解步数含义
        # 保留：
        # - current_tool_round > 90 → 确实跑太久了，提醒收束
        # - current_depth > 200 → 终极保险丝，防止真正的死循环

        if self.current_tool_round > 90:
            summary = (
                "你已达到最大工具调用轮次上限。请提供最终回复，"
                "总结你已完成的内容，不需要再调用工具。"
            )
            self._append_to_history("user", summary)
            self.current_depth += 1
            return False
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
        self.tracker._read_files = {}
        self._recent_tool_calls = []
        self.tracker._change_log = []

        # 4. 注入阶段摘要（放在 history 开头，紧接系统 prompt）
        self.history.insert(0, {"role": "system", "content": summary})

    @staticmethod
    def _takeaway_worthy(user_msg: str, asst_msg: str) -> bool:
        """纯本地预筛：判断本轮对话是否值得调用 LLM 提取 takeaways。

        优先级：放行信号 > 跳过条件。放行信号命中任一即放行，
        跳过条件命中任一即跳过。

        Returns:
            True → 放行（值得调 LLM）；False → 跳过（零 API 成本）。
        """
        user_stripped = user_msg.strip()
        asst_stripped = asst_msg.strip()

        # ── 放行信号（命中任一即放行，宁可多打不可漏记） ──
        # 1. 价值关键词命中
        if _TAKEAWAY_VALUE_KEYWORDS.search(user_stripped + asst_stripped):
            return True
        # 2. 内容足够长
        if len(user_stripped) > 100 or len(asst_stripped) > 300:
            return True

        # ── 跳过条件（命中任一即跳过） ──
        # 1. 短闲聊：双方均 < 40 字，且无价值关键词（已检查过）
        if len(user_stripped) < 40 and len(asst_stripped) < 40:
            return False
        # 2. 纯确认/过渡词
        if _TAKEAWAY_CONFIRM_PATTERN.match(user_stripped):
            return False
        # 3. 纯问答无沉淀：asst < 60 字且双方均无价值关键词
        if len(asst_stripped) < 60:
            return False

        return False

    def _extract_takeaways(self) -> list[str]:
        """从最近一轮对话中提取 1-2 条值得记住的关键结论（草稿记忆）。

        入口有预筛闸门 _takeaway_worthy，不值得的回合跳过 LLM 调用。
        总开关：环境变量 BOBO_TAKEAWAYS=off 可彻底禁用。
        """
        import os as _os
        if _os.environ.get("BOBO_TAKEAWAYS", "").lower() == "off":
            return []
        try:
            user_msgs = [m.get("content", "") for m in self.history[-4:]
                         if m.get("role") == "user" and m.get("content")]
            asst_msgs = [m.get("content", "") for m in self.history[-4:]
                          if m.get("role") == "assistant" and m.get("content")]
            if not user_msgs or not asst_msgs:
                return []
            user_msg = user_msgs[-1]
            asst_msg = asst_msgs[-1]
            # ── 预筛闸门：不值得则零成本跳过 ──
            if not self._takeaway_worthy(user_msg, asst_msg):
                event_bus.write("takeaway.skipped", {
                    "reason": "local_gate",
                    "user_len": len(user_msg),
                    "asst_len": len(asst_msg),
                })
                return []
            context = f"用户: {user_msg[:300]}\nBobo: {asst_msg[:300]}"
            prompt = [
                {"role": "system", "content": (
                    "你是一个对话总结器。从以下对话中提取 1-2 条值得记住的关键结论。"
                    "只提取对用户有长期价值的信息：偏好、决策、项目进展、技术选型。"
                    "不要提取闲聊、问候、过渡性内容。如果没有值得记住的，回复'无'。"
                    "每条结论一行，不超过 60 字。不要编号。"
                )},
                {"role": "user", "content": context},
            ]
            response = self.llm_caller(prompt, use_tools=False)
            if isinstance(response, dict) and "error" in response:
                return []
            content = (response.get("choices", [{}])[0]
                       .get("message", {}).get("content", ""))
            takeaways = [t.strip() for t in content.split("\n")
                         if t.strip() and t.strip() != "无" and len(t.strip()) > 5]
            results = takeaways[:2]
            if results:
                event_bus.write("takeaway.extracted", {
                    "count": len(results),
                    "items": results,
                })
            return results
        except Exception:
            return []

    def _truncate_history(self):
        """硬截断最早的消息（超过 MAX_HISTORY_MESSAGES），复用孤儿配对保护。"""
        user_indices = [i for i, m in enumerate(self.history) if m.get("role") == "user"]
        target_first = len(self.history) - self.MAX_HISTORY_MESSAGES
        split = target_first
        for idx in user_indices:
            if idx >= target_first:
                split = idx
                break
        # 孤儿保护：split 点不能切在 tool 消息上（它属于上一轮的 tool_calls 配对）
        while (split < len(self.history) and
               self.history[split].get("role") == "tool"):
            split += 1
        self.history = self.history[split:]

    def _call_llm(self) -> Tuple[str, list]:

        # 阶段交接清理：在当前 LLM 调用前清理上一阶段的上下文
        if self._phase_pending_cleanup:
            self._handle_phase_transition()
            self._phase_pending_cleanup = False

        # 首次工具调用后提醒 LLM 考虑用 spawn_worker 拆分子任务
        if not self._worker_reminded and self._step_count >= 1:
            has_worker = any(
                "spawn_worker" in str(m.get("content", ""))
                or any(
                    tc.get("function", {}).get("name") == "spawn_worker"
                    for tc in m.get("tool_calls") or []
                )
                for m in self.history
            )
            if not has_worker:
                self.history.insert(0, {
                    "role": "system",
                    "content": "注意：这个任务涉及多个步骤或文件。\n"
                    "选项 A：用 spawn_worker 拆分成独立子任务（推荐，可并行，各模块上下文隔离、质量更好）\n"
                    "选项 B：全部自己执行（请简要说明理由）\n"
                    "请在下一步回复中做出选择。"
                })
                self._worker_reminded = True

        # 硬限制：超过上限的消息数，丢弃最早的消息（复用孤儿配对保护）
        if len(self.history) > self.MAX_HISTORY_MESSAGES:
            self._truncate_history()

        # ── 票 T：msg_count 超阈值自动压缩归档 ──
        # 只在空闲态压缩——工具执行中途修改 history 会导致
        # tool_calls/tool_result 配对断裂 → API 报错 → engine 崩溃。
        # 每轮最多压缩一次，压缩后幂等检查（msg_count 降到预算内）。
        if (not self._compressing and not self._compressed_this_turn
                and self.state != self.STATE_EXECUTING):
            from core.context import _get_msg_count_budget, _estimate_tokens, _get_context_budget

            msg_count = len(self.history)
            msg_budget = _get_msg_count_budget()

            if msg_count > msg_budget:
                # 静默压缩（用户 2026-07-29 要求）：压缩在后台完成，不占 TUI 状态栏。
                # 调试时设 BOBO_SHOW_COMPRESS=1 恢复提示。可观测性走事件总线
                # context.compressed，不打扰用户。
                if os.environ.get("BOBO_SHOW_COMPRESS") == "1":
                    self._notify("thinking", {
                        "phase": "compressing",
                        "message": f"正在压缩历史上下文...（{msg_count} 条消息, 预算 {msg_budget} 条）"
                    })
                self._compress_history()
                self._compressed_this_turn = True
            else:
                # 仅当 msg_count 未超限时，降级做 token 预算检查（保留存量行为）
                est_tokens = _estimate_tokens(self.history)
                token_budget = _get_context_budget()
                if est_tokens > token_budget * 0.5:
                    self.tracker.retroactive_mark()
                if est_tokens > token_budget:
                    if os.environ.get("BOBO_SHOW_COMPRESS") == "1":
                        self._notify("thinking", {
                            "phase": "compressing",
                            "message": f"正在压缩历史上下文...（估算 {est_tokens} tokens, 预算 {token_budget}）"
                        })
                    self._compress_history()
                    self._compressed_this_turn = True

        messages = self.injector.build_messages(
            system_prompt=self.system_prompt,
            user_input=self.current_user_input or "",
            tools_schema=TOOLS_SCHEMA,
            extra_categories=self._used_categories,
            session_id=getattr(self, 'sid', ""),
        )

        self._notify("thinking", {"phase": "calling_llm", "message": "正在思考..."})

        # ── 票 H 运行时孤儿防线 Layer 1：发送前清洗（作用在发送副本上，不动 history） ──
        # 注意: messages 是新 list，但内层 dict 与 engine.history 共享引用。不可 mutate 元素内容。
        cleaned_messages, _orphan_report = clean_orphan_tool_calls(messages)
        if _orphan_report["inserted"] > 0 or _orphan_report["removed"] > 0:
            logger.warning(
                "运行时孤儿 tool_calls 清洗（发送前）: 补 %d 个占位, 删 %d 个游离, "
                "orphan_tc_ids=%s, orphan_tool_msg_ids=%s",
                _orphan_report["inserted"], _orphan_report["removed"],
                _orphan_report.get("orphan_tc_ids", []),
                _orphan_report.get("orphan_tool_msg_ids", []),
            )
            messages = cleaned_messages

        def _on_token(token: str):
            self._notify("thinking.delta", {"text": token})

        def _on_reasoning(token: str):
            # 票 P：reasoning 模型思考过程流（独立通道，不与正文混）
            self._notify("reasoning.delta", {"text": token})

        def _on_retry(message: str, delay: float):
            self._notify("status.update", {
                "kind": "rate_limit",
                "text": f"API {message}，{int(delay)} 秒后重试...",
            })


        filtered_tools = self._get_filtered_tools(extra_categories=self._used_categories)
        if filtered_tools is not None:
            names = [t.get("function", {}).get("name", "") for t in filtered_tools]
            self._notify("thinking", {"phase": "tool_filter", "message": f"加载 {len(filtered_tools)} 个工具 ({', '.join(names)})"})

        # 事件总线：计算 caller 传的实际 messages 条数和含 tool_calls 情况
        _llm_msg_count = len(messages)
        _llm_has_tool_calls = any(
            m.get("role") == "assistant" and m.get("tool_calls")
            for m in messages
        )
        _llm_t0 = time.time()

        response = self.llm_caller(
            messages,
            stream_callback=_on_token,
            retry_callback=_on_retry,
            tools_override=filtered_tools,
            session_id=self.sid,
            reasoning_callback=_on_reasoning,
        )
        if isinstance(response, dict) and "error" in response:
            # ── 票 H 运行时孤儿防线 Layer 2：配对类 400 → 清洗重试一次 ──
            if _is_tool_pairing_400(response):
                logger.warning(
                    "运行时孤儿防线: HTTP 400 配对断裂，清洗后重试一次。"
                    "原始错误: %s", response.get("error", "")
                )
                retry_messages, _retry_report = clean_orphan_tool_calls(messages)
                if _retry_report["inserted"] > 0 or _retry_report["removed"] > 0:
                    logger.warning(
                        "重试前清洗: 补 %d 个占位, 删 %d 个游离, "
                        "orphan_tc_ids=%s, orphan_tool_msg_ids=%s",
                        _retry_report["inserted"], _retry_report["removed"],
                        _retry_report.get("orphan_tc_ids", []),
                        _retry_report.get("orphan_tool_msg_ids", []),
                    )
                retry_response = self.llm_caller(
                    retry_messages,
                    stream_callback=_on_token,
                    retry_callback=_on_retry,
                    tools_override=filtered_tools,
                    session_id=self.sid,
                )
                if not isinstance(retry_response, dict) or "error" not in retry_response:
                    # 重试成功
                    logger.warning(
                        "运行时孤儿防线: 清洗后重试成功。orphan_tc_ids=%s",
                        _retry_report.get("orphan_tc_ids", []),
                    )
                    self._last_usage = retry_response.get("usage", {})
                    content, tool_calls = self._extract_response(retry_response)
                    content = remove_emojis(content or "")

                    # 事件总线：llm.call 重试成功
                    _retry_elapsed = int((time.time() - _llm_t0) * 1000)
                    _retry_usage = retry_response.get("usage", {}) if isinstance(retry_response, dict) else {}
                    event_bus.write("llm.call", {
                        "session_id": getattr(self, "sid", ""),
                        "msg_count": _llm_msg_count,
                        "has_tool_calls": _llm_has_tool_calls,
                        "duration_ms": _retry_elapsed,
                        "prompt_tokens": _retry_usage.get("prompt_tokens", 0),
                        "completion_tokens": _retry_usage.get("completion_tokens", 0),
                        "total_tokens": _retry_usage.get("total_tokens", 0),
                        "orphan": {
                            "inserted": _retry_report["inserted"],
                            "removed": _retry_report["removed"],
                        } if (_retry_report["inserted"] or _retry_report["removed"]) else None,
                        "retry": True,
                    })

                    return content or "", tool_calls
                # 重试仍失败 → 若仍是配对 400 则不再递归，直接走下方错误处理
                logger.warning(
                    "运行时孤儿防线: 清洗后重试仍失败。错误: %s",
                    retry_response.get("error", ""),
                )

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
                self._emit_state_change(self.STATE_ERROR, "LLM non-retryable error")

            # 事件总线：llm.call 出错
            _llm_elapsed = int((time.time() - _llm_t0) * 1000)
            event_bus.write("llm.call", {
                "session_id": getattr(self, "sid", ""),
                "msg_count": _llm_msg_count,
                "has_tool_calls": _llm_has_tool_calls,
                "duration_ms": _llm_elapsed,
                "error_type": error_type,
                "orphan": {
                    "inserted": _orphan_report["inserted"],
                    "removed": _orphan_report["removed"],
                } if (_orphan_report["inserted"] or _orphan_report["removed"]) else None,
            })

            return error_msg, []
        self._last_usage = response.get("usage", {})
        # 票 P：捕获 reasoning（思考过程，独立展示，不进正文/历史）
        if isinstance(response, dict) and response.get("reasoning"):
            self._last_reasoning = response["reasoning"]
        content, tool_calls = self._extract_response(response)
        content = remove_emojis(content or "")

        # 事件总线：llm.call 正常返回
        _llm_elapsed = int((time.time() - _llm_t0) * 1000)
        _llm_usage = response.get("usage", {}) if isinstance(response, dict) else {}
        event_bus.write("llm.call", {
            "session_id": getattr(self, "sid", ""),
            "msg_count": _llm_msg_count,
            "has_tool_calls": _llm_has_tool_calls,
            "duration_ms": _llm_elapsed,
            "prompt_tokens": _llm_usage.get("prompt_tokens", 0),
            "completion_tokens": _llm_usage.get("completion_tokens", 0),
            "total_tokens": _llm_usage.get("total_tokens", 0),
            "orphan": {
                "inserted": _orphan_report["inserted"],
                "removed": _orphan_report["removed"],
            } if (_orphan_report["inserted"] or _orphan_report["removed"]) else None,
        })

        return content or "", tool_calls

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


    def _extract_response(self, response) -> tuple:
        try:
            if isinstance(response, dict):
                choice = response.get("choices", [{}])[0]
                message = choice.get("message", {})
                content = message.get("content") or ""  # 处理 API 返回 content: null
                tool_calls = message.get("tool_calls") or []
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
        # 用户中断：收到新消息时 cancel 设置了中断信号，立刻退出
        if getattr(self, '_interrupt_event', None) and self._interrupt_event.is_set():
            self._emit_state_change(self.STATE_ERROR, "interrupted")
            return
        # _check_guards 移到最外层，每个 step 都检查，防止无限循环
        if self._check_guards():
            self._emit_state_change(self.STATE_ERROR, "guards triggered")
            return

        if self.state == self.STATE_IDLE:
            result = self._handle_pre_input(self.current_user_input)
            if result is not None:
                self._notify("complete", {"content": result})
                self._emit_state_change(self.STATE_DONE, "response complete")
                return
            if self.current_user_input:
                self._append_to_history("user", self.current_user_input)
            self._emit_state_change(self.STATE_THINKING, "user input")
        elif self.state == self.STATE_THINKING:
            content, tool_calls = self._call_llm()
            self._pending_content = content
            self._pending_tool_calls = tool_calls
            if tool_calls:
                # 快照由 tool_runner._execute_tool_loop 在 _file_checkpoints
                # 填充之后保存，确保首个修改轮次的文件也能回退（审计 #17）
                self._emit_state_change(self.STATE_EXECUTING, "executing tools")
            else:
                # 空响应处理：flash model / reasoning 模型 token 耗尽 → 重试一次
                if not content and not self._pending_tool_calls:
                    if self.current_depth < 2:
                        self._pending_content = None
                        self._pending_tool_calls = None
                        self.current_depth += 1
                        self._emit_state_change(self.STATE_THINKING, "retry")
                    else:
                        # 重试后仍然空 → 明确报错，不静默结束
                        err_msg = (
                            "模型返回了空响应。可能原因：\n"
                            "  - reasoning 模型的思考过程耗尽了 max_tokens（可调高 BOBO_MAX_TOKENS 环境变量）\n"
                            "  - temperature 设置与模型要求不匹配（reasoning 模型通常需要 temperature=1.0，可设置 BOBO_TEMPERATURE）\n"
                            "  - API 暂时异常"
                        )
                        self._pending_content = err_msg
                        self._emit_state_change(self.STATE_RESPONDING, "response error")
                # 检查是否需要验证：LLM 声称完成但没有使用任何工具
                elif self.verifier.check_and_inject(self.history, content):
                    self._pending_content = None
                    self._pending_tool_calls = None
                    self.current_depth += 1
                    self._emit_state_change(self.STATE_THINKING, "tool calls pending")
                else:
                    self._emit_state_change(self.STATE_RESPONDING, "responding")
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
                    self._emit_state_change(self.STATE_THINKING, "retry after verification")
                    return

            tool_results = self._execute_tool_loop(self._pending_tool_calls)
            # ── 票 K v2 + L：工具执行后同步台账 ──
            # task_ledger 工具在 ToolRunnerMixin 提供的 Engine 上下文中
            # 已经直接修改了 self.task_ledger；若当前线程仍存在上下文（旧测试/直接调用），
            # 则回退同步模块级变量。
            try:
                from tools.task_ledger import current_engine_var, _current_ledger
                if current_engine_var.get() is not None:
                    self.task_ledger = list(_current_ledger())
            except Exception:
                pass
            self._append_to_history("assistant", self._pending_content,
                                    tool_calls=self._pending_tool_calls)
            self._append_to_history("tool", tool_results=tool_results)
            # 检测阶段完成信号
            if self._pending_content and self._is_phase_complete(self._pending_content):
                self._phase_pending_cleanup = True
            # 边执行边扩张 + 改动日志 + 已读文件（审计 #24：全部在同一个
            # for 循环内，N3 修复取本条 tool_result 而非整轮聚合）
            if self._pending_tool_calls:
                import json as _je
                for tc in self._pending_tool_calls:
                    name = tc.get("function", {}).get("name", "")
                    args_str = tc.get("function", {}).get("arguments", "{}")
                    # 边执行边扩张
                    for cat, tools in self.TOOL_CATEGORIES.items():
                        if name in tools:
                            self._used_categories.add(cat)
                    # 改动日志 → tracker
                    if name in ("edit_file", "file_operation"):
                        try:
                            a = _je.loads(args_str) if isinstance(args_str, str) else args_str
                            fpath = a.get('file_path', '') or a.get('path', '')
                            if fpath:
                                if name == "edit_file":
                                    old = a.get("old_string", "")[:40]
                                    new = a.get("new_string", "")[:40]
                                    self.tracker.log_change(f"{fpath}: {old} → {new}")
                                else:
                                    self.tracker.log_change(f"{fpath}（{a.get('action','write')}）")
                        except Exception:
                            pass
                    # 已读文件 → tracker（按 tool_call_id 匹配，并行执行时索引不可靠）
                    if name == "read_local_file":
                        try:
                            a = _je.loads(args_str) if isinstance(args_str, str) else args_str
                            fpath = a.get('file_path', '') or a.get('filepath', '') or a.get('path', '')
                            tc_id = tc.get("id", "")
                            match = next((r for r in tool_results if r.get("tool_call_id") == tc_id), None)
                            content = match.get("content", "") if isinstance(match, dict) else ""
                            self.tracker.record_read(fpath, content)
                        except Exception:
                            pass
            # 工具调用模式 → tracker
            if self._pending_tool_calls:
                round_names = [tc.get("function", {}).get("name", "")
                              for tc in self._pending_tool_calls
                              if tc.get("function", {}).get("name")]
                self.tracker.record_tool_pattern(round_names, self.current_user_input or "")
            self._notify("thinking", {"phase": "continuing", "message": "工具执行完成"})
            self._pending_content = None
            self._pending_tool_calls = None
            self.current_depth += 1
            self.current_tool_round += 1
            self._emit_state_change(self.STATE_THINKING, "next tool round")
        elif self.state == self.STATE_RESPONDING:
            if self._pending_content:
                self._append_to_history("assistant", self._pending_content)
                # 引用追踪：LLM 回复中若引用了注入的记忆，自动加分
                if getattr(self.proactive, '_last_memory_ids', None):
                    self.proactive.track_citation(self._pending_content, self.proactive._last_memory_ids)
                    self.proactive._last_memory_ids = []
                # 自动草稿记忆：从本轮对话提取关键结论
                if self.proactive.mode != "off":
                    logger.debug("RESPONDING extract_takeaways start")
                    takeaways = self._extract_takeaways()
                    if takeaways:
                        try:
                            from tools.v5_memory import add_entry, bump_signal
                            for t in takeaways:
                                entry = add_entry(t, entry_type="draft")
                                if entry:
                                    # 草稿记忆：低初始分，写入磁盘
                                    entry["signal_score"] = 30
                                    entry["is_draft"] = True
                                    from tools.v5_memory import _save, _load, _write_lock
                                    with _write_lock:
                                        data = _load()
                                        for e in data.get("entries", []):
                                            if e.get("id") == entry["id"]:
                                                e["signal_score"] = 30
                                                e["is_draft"] = True
                                                break
                                        _save(data)
                        except Exception:
                            pass
                    logger.debug("RESPONDING extract_takeaways done: %d items", len(takeaways) if takeaways else 0)
                # 自动 skill 发现：检查候选模式并主动提议
                if self.proactive.mode != "off":
                    logger.debug("RESPONDING maybe_propose_skill start")
                    self.tracker.maybe_propose_skill()
                    logger.debug("RESPONDING maybe_propose_skill done")
                # ── 票 K v2 收工闸：台账检查（引擎执法，不由模型嘴决定收工） ──
                pending_items = [e for e in self.task_ledger if e.get("status") != "done"]
                if pending_items:
                    if self._ledger_reinject_count < 2:
                        # 回注次数 < 2 → 回注一条 user 消息，回到 THINKING
                        self._ledger_reinject_count += 1
                        titles = ", ".join(f'"{e["title"][:30]}"' for e in pending_items)
                        rej_msg = (
                            f"任务台账还有 {len(pending_items)} 项未完成：{titles}。"
                            "请继续执行，不要说明、不要道歉，直接继续。"
                        )
                        self._append_to_history("user", rej_msg)
                        self._pending_content = None
                        self._pending_tool_calls = None
                        self.current_depth += 1
                        logger.debug("RESPONDING ledger re-injection #%d: %d items pending",
                                     self._ledger_reinject_count, len(pending_items))
                        self._emit_state_change(self.STATE_THINKING, "ledger re-injection")
                        return
                    else:
                        # 已达 2 次熔断上限 → 放行 done，终稿附加 ⚠️ 遗言
                        pending_titles = ", ".join(
                            f'"{e["title"][:30]}"' for e in pending_items
                        )
                        warning = (
                            f"\n\n⚠️ 台账 {len(pending_items)} 项未销账，引擎放行：{pending_titles}"
                        )
                        self._pending_content = (self._pending_content or "") + warning
                        logger.debug("RESPONDING ledger force-release: %d items still pending",
                                     len(pending_items))
                elif not self.task_ledger:
                    # 台账为空：直接放行，写统计事件
                    from core.event_bus import event_bus
                    event_bus.write("task.no_ledger", {
                        "session_id": getattr(self, "sid", ""),
                        "reason": "no ledger created",
                    })
                    logger.debug("RESPONDING no ledger — direct done")
                # else: 台账全 done → 正常放行（clean done，无操作）
                self._ledger_reinject_count = 0  # 干净收工时重置计数
                # ── 票 K v2 §4 降级方案：终稿尾部附台账摘要行（面板替代） ──
                if self.task_ledger:
                    done_cnt = sum(1 for e in self.task_ledger if e.get("status") == "done")
                    total = len(self.task_ledger)
                    self._pending_content = (self._pending_content or "") + f"\n\n📋 台账: {done_cnt}/{total} done"
                content = self._format_final_output(self._pending_content)
                # ── 票 P 降级展示：reasoning 思考块（仅展示层，历史在上方已落账，零污染） ──
                if self._last_reasoning:
                    _r = self._last_reasoning
                    _r_show = _r if len(_r) <= 2000 else _r[:2000] + f"\n…（思考全文 {len(_r)} 字，已截断展示）"
                    content += f"\n\n── 💭 思考过程 ──\n{_r_show}\n── 思考结束 ──"
                    self._last_reasoning = ""  # 消费即清，防串回合
                logger.debug("RESPONDING emit complete start: len=%d", len(content))
                self._notify("complete", {"content": content, "usage": self._last_usage})
                logger.debug("RESPONDING emit complete done")
            else:
                self._notify("complete", {"content": "（没有生成回复内容）"})
            self._pending_content = None
            self._emit_state_change(self.STATE_DONE, "done")

    def run(self, user_input: str = None, stream: bool = True, depth: int = 0, tool_round: int = 0):
        self._emit_state_change(self.STATE_IDLE, "session start")
        self.current_user_input = user_input
        self.current_depth = depth
        self.current_tool_round = tool_round
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0
        self._all_confirmed = False
        self.verifier.attempted = False

        if self.history and not self._compressing:
            from core.context import _estimate_tokens, _get_context_budget
            if _estimate_tokens(self.history) > _get_context_budget(self):
                self._compress_history()
                self._compressed_this_turn = True

        while self.state not in (self.STATE_DONE, self.STATE_ERROR):
            self._step_count += 1
            if self._step_count > self.MAX_STEPS:
                self._notify("thinking", {"phase": "continuing", "message": "步骤已用完，正在生成最终回复..."})
                self._emit_state_change(self.STATE_RESPONDING, "continuing")
                break
            if self._step_count >= 50 and self._step_count % 5 == 0:
                self._notify("thinking", {"phase": "continuing",
                    "message": f"已用 {self._step_count}/{self.MAX_STEPS} 步"})
            # 检查中断信号
            if getattr(self, '_interrupt_event', None) and self._interrupt_event.is_set():
                self._notify("error", {"content": "用户中断了操作"})
                self._emit_state_change(self.STATE_ERROR, "user interrupted")
                break
            self._step()

    def reset(self):
        self.history = []
        from tools.file_operation import clear_cache
        clear_cache()
        self.teaching_mode = False
        self.recorded_messages = []
        self._emit_state_change(self.STATE_IDLE, "cleanup")
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
        self.verifier.attempted = False
        self.checkpoint_mgr.clear()
        self._notify("reset", {})
