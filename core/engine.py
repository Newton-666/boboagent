"""Engine — 核心对话调度器（集成教学模式）"""

import sys
import os
import json
import re
import time
import logging
import threading
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
from core.command_safety import (classify_command, is_high_risk_tool, is_auto_readonly_command,
                                 classify_side_effect, _has_real_git_command, is_blacklisted,
                                 _find_git_subcommand, is_protected, load_protected_paths,
                                 is_git_readonly_subcommand)
from core.verifier import Verifier
from core.checkpoint import CheckpointManager
from core.skill_loader import SkillLoader
from core.llm_caller import LLMInterrupted  # 票 INT-1：流式可中断——捕获走 interrupted 路径
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

    MAX_STEPS = int(os.environ.get("BOBO_MAX_STEPS", 500))

    def __init__(self, llm_caller, tool_executor=None, callback: Callable = None,
                 confirm_callback: Callable = None, test_mode: bool = False,
                 auto_mode_getter: Callable[[], bool] = None,
                 computer_use_mode_getter: Callable[[], bool] = None):
        self.llm_caller = llm_caller
        self.tool_executor = tool_executor or execute_tool
        self.callback = callback
        self.confirm_callback = confirm_callback
        self.test_mode = test_mode or ('pytest' in sys.modules)
        self._auto_mode_getter = auto_mode_getter  # 票 A：会话级 AUTO MODE 开关读取器（放 ctx，engine 只读）
        self._computer_use_mode_getter = computer_use_mode_getter  # TICKET-COMPUTER-USE-ROUTE（COST-3 特批标记）：会话级 computer use 开关读取器
        self.history = []
        # ── 票 DESK-P1（特批标记）：会话项目根。null=默认现状（工作目录即
        # BOBO_Project_Backup），绝对兼容；gateway 经 engine_adapter 注入
        # （session["project_root"]）。injector 据此注入尾部动态段，
        # tool_runner 据此给 execute_terminal 注入默认 cwd。 ──
        self.project_root: str | None = None
        # 会话标识：gateway 在 open_session 中设 self.sid；无会话时走时间戳兜底
        _now = time.time()
        self.sid = f"boot-{int(_now)}-{os.urandom(2).hex()}"
        # ── 票 O-1：OFFICE MODE 角色读取——唯一身份来源是搭建器注入的
        # BOBO_ROLE 环境变量（无任何 session 名嗅探/环境检测兜底，v0.3.1 裁决）。
        # staff/dispatcher 之外的任何值（含未设置）→ 普通模式，零限制。
        _raw_role = os.environ.get("BOBO_ROLE", "").strip().lower()
        self.office_role = _raw_role if _raw_role in ("staff", "dispatcher") else None
        if _raw_role and self.office_role is None:
            self._write_office_audit("role", f"BOBO_ROLE={_raw_role!r} 非法（仅 staff/dispatcher），按无角色普通模式处理")
        elif self.office_role is not None:
            self._write_office_audit("role", f"BOBO_ROLE={self.office_role} 注入生效")
        # ── 票 O-1：当前会话票据 = BOBO_TICKET（启动注入，同 BOBO_ROLE 一并由
        # 搭建器注入）。豁免只看这一张票；未设置 → 无豁免。
        _raw_ticket = os.environ.get("BOBO_TICKET", "").strip()
        self.office_ticket = _raw_ticket or None
        if self.office_ticket is not None:
            self._write_office_audit("ticket", f"BOBO_TICKET={self.office_ticket} 注入生效")
        self.system_prompt = self._build_system_prompt()

        self.teaching_mode = False
        self.recorded_messages = []
        self.current_skill_name = None

        self.skill_executor = get_skill_manager()

        self.state = self.STATE_IDLE
        self.current_user_input = None
        self.current_depth = 0
        self.current_tool_round = 0
        # 票 CORE-R1：60% 水位提示只发一次（默认 150 轮的 90 轮）
        self._watermark_notified = False
        self._pending_content = None
        self._pending_tool_calls = None
        self._step_count = 0
        self._exit_reason = "completed"
        self._all_confirmed = False
        self._compressing = False
        self._compressed_this_turn = False  # 本轮已压缩过——不再触发
        self._just_compressed = False  # 票 TICKET-021：上轮压缩过，下轮置顶提示
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
        self._session_written_files: set[str] = set()  # 票 TICKET-025：会话级只增集合，压缩不塌缩
        self._extra_tools: set[str] = set()  # 票 TICKET-E2b：describe_tool 取件注册，会话级只增，压缩不清空
        self.tracker = RoundTracker(self)  # 回合后处理（change_log / read_files / pattern）
        # ── 票 K v2：任务台账（收工闸核心） ──
        self.task_ledger: list[dict] = []  # [{"id":str, "title":str, "status":"pending"|"in_progress"|"done"}]
        self._ledger_reinject_count: int = 0  # 连续回注计数（硬熔断 2 次）
        self._ledger_field_deny_count: int = 0  # 票 C：台账缺字段 deny 计数（独立，无熔断上限）
        self._last_reasoning: str = ""  # 票 P：上一轮 reasoning 思考过程（展示用 + TICKET-GUI-F8 落 assistant 消息 thinking 字段进历史）
        self._interrupt_event: threading.Event | None = None
        # 票 AUTO-G2：待人工清单"已交接水位线"（events.jsonl 事件 ts）。
        # 收工只列 ts > 水位线的 auto 拒绝；None = 首回合/无记录 → 列全部（兼容现状）。
        # run_engine 注入会话旧值、收工回写 session 持久化；/clear-handoff 推到最新。
        self.handoff_watermark: float | None = None
        self._handoff_last_ts: float | None = None  # 本回合扫到的最后一条 deny ts（收工后作新水位线）
        self._recent_tool_calls: list[tuple[str, str]] = []  # (tool_name, args_key) for loop detection
        self._used_categories: set[str] = set()  # 边执行边扩张的工具分类
        self._phase_pending_cleanup: bool = False
        self._phase_summary: str = ""
        self._worker_reminded: bool = False
        self._work_anchor: dict | None = None  # 票 COST-3：工作锚点属性化（不入 history），压缩时刷新、injector 尾部注入
        self._ledger_reminded: bool = False  # 票Z 缝1：无账提醒标记
        self._ledger_backfill_suspect: bool = False  # 票 O8-2：事后补账嫌疑（工具轮批量创建即全 done）
        self._reply_quality_reinject_count: int = 0  # 票 R2b：答复质量闸打回计数（每回合至多 1 次，防死循环）
        self._round_had_write_tool: bool = False  # 票 R2b：本回合是否含写类工具（问答回合无台账段判定）
        self._round_tool_exec_count: int = 0  # 票 R3-b：本轮工具执行次数（读/查施工豁免证据）
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
        # ── 票 O-1：OFFICE MODE 执法层——BOBO_ROLE 存在即激活（普通模式零变化）。
        # 必须排在 auto 决策树之前：auto 是背景技术，不豁免员工限制
        # （v0.3.1：员工限制由注入的角色携带，与 auto 开关正交）。
        if self.office_role is not None:
            _office_verdict, _office_reason = self._office_decide(tool_name, tool_args, reason)
            if _office_verdict != "allow":
                return False
        # 票 A：AUTO MODE 决策树——必须排在 _all_confirmed 之前（火 A-2：
        # 否则用户点过 always 后灰名单会绕过 auto 风险评估直接放行）
        if self._auto_mode_getter is not None and self._auto_mode_getter():
            _allow = self._auto_decide(tool_name, tool_args, reason)
        elif self._all_confirmed:
            _allow = True
        elif self.confirm_callback:
            result = self.confirm_callback(tool_name, tool_args, reason)
            if result == "all":
                self._all_confirmed = True
                _allow = True
            else:
                _allow = result
        else:
            _allow = False
        # ── 票 O3-1：写类工具通过决策链后 → 受保护路径 md5 快照（office 角色会话）。
        # 只挂 office 角色 + 写工具；普通模式/非写工具零开销零行为变化（对照组铁律）。
        # 快照是抓漏不是执法：失败静默降级，绝不阻塞工具链。
        if _allow and self.office_role is not None and tool_name in self._OFFICE_WRITE_TOOLS:
            self._snapshot_protected_paths()
        return _allow

    def _auto_decide(self, tool_name: str, tool_args: dict, reason: str) -> bool:
        """AUTO MODE 决策树 v2（票 B）：副作用三级分类 + 快照 + 审计字段扩展。

        v2 规则（票 B-1/B-2/B-3）：
        - execute_terminal 按 classify_side_effect 逐段分级：
          * pure-read（git 只读子命令 / classify safe 段）→ 直接放行；
          * local-reversible（git 本地写 / gray 本地命令）→ 决策时刻快照（B-2，
            串行完成，禁止挪到执行线程）后放行；
          * external-irreversible（git push / curl 写 / scp / npm publish 等）
            → 转弹窗（B-3），超时无人应答默认 deny（安全默认，火 2）；
        - 非 terminal 文件工具（edit_file/file_operation 等）→ 快照（复用
          file_writer checkpoint）后放行。
        每次决策写 auto.decide 审计，字段含 side_effect_level / snapshot_ref /
        rollback_path（B-4）。
        """
        # 非 terminal 文件工具：快照（复用 file_writer checkpoint 自动备份）后放行
        if tool_name in ("edit_file", "file_operation", "delete_file"):
            snapshot = self._snapshot_for_rollback(f"file:{tool_name}")
            # TICKET-GUI-F4 F4-6（Kimi 特批）：补传缺失的 command 实参——原调用 6 参传 5，
            # snapshot 错位进 side_effect_level，AUTO 下文件工具必 TypeError 崩溃。
            _fcmd = str(tool_args.get("path") or tool_args.get("filepath") or tool_args.get("file_path") or tool_args.get("file") or "")[:200]
            self._write_auto_audit("allow", tool_name, _fcmd, "auto 决策树 v2：文件工具（file_writer checkpoint）",
                                   "local-reversible", snapshot)
            return True

        if tool_name == "execute_terminal":
            command = tool_args.get("command", "")
            # ── 票 AUTO-D D-1：黑名单硬锁——auto 下最高优先级，即时拒绝 ──
            # is_blacklisted 独立于 classify_side_effect（后者把黑名单并入
            # external-irreversible，无法区分两档审计 reason）。
            black_hit, black_reason = is_blacklisted(command)
            if black_hit:
                self._write_auto_audit("deny", tool_name, command[:120],
                                       f"危险黑名单硬锁：auto 即时拒绝（{black_reason}）",
                                       "external-irreversible", None)
                return False

            level, side_reason = classify_side_effect(command)
            if level == "pure-read":
                # 双保险：仍要求逐段只读（classify_side_effect 与票 A 判定同源，
                # 理论一致；不一致时保守拒绝）
                if is_auto_readonly_command(command):
                    self._write_auto_audit("allow", tool_name, command[:120],
                                           f"auto 决策树 v2：纯读命令（{side_reason}）",
                                           "pure-read", None)
                    return True
            elif level == "local-reversible":
                snapshot = self._snapshot_for_rollback(command)
                self._write_auto_audit("allow", tool_name, command[:120],
                                       f"auto 决策树 v2：本地可回滚（{side_reason}）",
                                       "local-reversible", snapshot)
                return True

            # ── 票 AUTO-D D-1：外部不可逆灰名单——auto 下不弹窗（弹窗=卡死），
            # 即时拒绝 + 留痕 + 收工时输出待人工执行清单（v0.7 裁决一）──
            self._write_auto_audit("deny", tool_name, command[:120],
                                   f"auto 模式：外部不可逆操作，拒绝并记入待人工执行清单（{side_reason}）",
                                   "external-irreversible", None)
            return False

        # ── 票 AUTO-D D-1（Q1 裁决）：非 terminal 灰名单意外落入兜底 → 统一 deny ──
        # auto 不弹窗是铁律：任何意外落入兜底的未分类操作即时拒绝+留痕，
        # 不留 120s 卡死路径（原 confirm_callback 弹窗在 auto 下废除）。
        self._write_auto_audit("deny", tool_name, str(tool_args)[:120],
                               f"auto 模式：未分类操作落入兜底，即时拒绝（{reason}）",
                               "external-irreversible", None)
        return False

    def _snapshot_for_rollback(self, command: str) -> dict:
        """票 B-2：决策时刻为 local-reversible 命令生成快照引用（phase 1 串行）。

        不做真·回滚执行器（票 B 边界）：只记录快照引用与回滚路径描述。
        - git 类：subprocess 只读取 HEAD + dirty 摘要（2s 超时，失败兜底描述）；
        - 文件类：复用 file_writer checkpoint（data/trash 自动备份）；
        - 包管理类：记录 before 状态描述；
        - 其他：generic 描述。
        """
        cmd = command.strip()
        if cmd.startswith("file:"):
            return {"kind": "file", "ref": "file_writer 自动备份（data/trash checkpoint）",
                    "rollback": "restore_checkpoint 恢复"}
        if _has_real_git_command(cmd):
            try:
                import subprocess as _sp
                head = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=2)
                head_sha = head.stdout.strip() if head.returncode == 0 else "(unknown)"
                status = _sp.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=2)
                dirty = sum(1 for _l in status.stdout.splitlines() if _l) if status.returncode == 0 else -1
                return {"kind": "git", "ref": f"HEAD={head_sha[:12]}, dirty_files={dirty}",
                        "rollback": f"git reset --hard {head_sha[:12]}（或按 dirty 情况 git revert）"}
            except Exception as e:
                return {"kind": "git-failed", "ref": f"快照失败: {e}", "rollback": "快照不可用，回滚需人工"}
        if re.search(r'\b(pip|pip3|npm)\s+install\b', cmd):
            return {"kind": "pkg", "ref": "安装前状态（pip list --format=freeze / package.json）",
                    "rollback": "pip/npm uninstall 并装回原版本"}
        return {"kind": "generic", "ref": "本地写命令（shell）",
                "rollback": "按命令类型人工回滚（无自动执行器，票 B 边界）"}

    def _write_auto_audit(self, verdict: str, tool_name: str, command: str, reason: str,
                          side_effect_level: str, snapshot: dict | None) -> None:
        """票 B-4：auto.decide 审计统一出口（字段扩展：side_effect_level /
        snapshot_ref / rollback_path）。"""
        event = {
            "sid": getattr(self, "sid", ""),
            "tool_name": tool_name,
            "command": command,
            "verdict": verdict,
            "reason": reason,
            "auto": True,
            "side_effect_level": side_effect_level,
        }
        if snapshot:
            event["snapshot_ref"] = snapshot.get("ref", "")
            event["rollback_path"] = snapshot.get("rollback", "")
        event_bus.write("auto.decide", event)

    # ── 票 O-1：OFFICE MODE 员工能力矩阵（staff/dispatcher 分档硬拦） ────────

    _OFFICE_WRITE_TOOLS = frozenset({
        "edit_file", "file_writer", "delete_file", "file_operation",
    })
    _TICKETS_DIR = os.path.join("data", "tickets")

    # ── 票 O3-1：受保护路径快照（guardsnap，抓漏不执法） ──────────────────
    _GUARDSNAP_DIR = "data"
    _GUARDSNAP_PREFIX = "guardsnap_"
    _GUARDSNAP_RETENTION_DAYS = 7

    def _guardsnap_path(self) -> str:
        """票 O3-1：当前会话快照文件路径（sid 维度）。"""
        return os.path.join(self._GUARDSNAP_DIR, f"{self._GUARDSNAP_PREFIX}{self.sid}.json")

    def _snapshot_protected_paths(self) -> dict | None:
        """票 O3-1：写类工具通过决策链后，对受保护路径做 md5 快照（sid 维度滚动，7 天）。

        - 展开 data/protected_paths.json 的 globs → 实际文件 → md5 摘要；
        - 写 data/guardsnap_<sid>.json（含前后缀、时间戳、文件→md5 映射）；
        - 顺带清理过期快照（> 7 天，sid 维度滚动保留）；
        - 任何异常静默降级（快照是抓漏，不是执法，绝不阻塞工具链）。
        """
        try:
            import glob as _glob
            import hashlib as _hash
            globs = load_protected_paths()
            if not globs:
                return None
            files: set[str] = set()
            for g in globs:
                for p in _glob.glob(g, recursive=True):
                    if os.path.isfile(p):
                        files.add(p)
            snap = {}
            for f in sorted(files):
                try:
                    with open(f, "rb") as _fh:
                        snap[f] = _hash.md5(_fh.read()).hexdigest()
                except OSError:
                    continue
            path = self._guardsnap_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as _fh:
                json.dump({
                    "sid": self.sid,
                    "ts": int(time.time()),
                    "files": snap,
                }, _fh, ensure_ascii=False, indent=2)
            self._prune_guardsnap()
            return snap
        except Exception:
            return None

    def _prune_guardsnap(self) -> None:
        """票 O3-1：清理超过 7 天的 guardsnap_*.json（sid 维度滚动保留）。"""
        try:
            cutoff = time.time() - self._GUARDSNAP_RETENTION_DAYS * 86400
            for name in os.listdir(self._GUARDSNAP_DIR):
                if not name.startswith(self._GUARDSNAP_PREFIX) or not name.endswith(".json"):
                    continue
                p = os.path.join(self._GUARDSNAP_DIR, name)
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                except OSError:
                    continue
        except OSError:
            pass

    def _verify_snapshot(self) -> list[dict]:
        """票 O3-1：收工时比对快照与当前 md5；不一致 → office.snap 审计（不阻断）。

        返回差异列表 [{"path", "before", "after"}]；无快照/读失败 → 空列表。
        抓漏不是执法：只写审计 + 由调用方决定告警展示，绝不 deny 收工。
        """
        path = self._guardsnap_path()
        if not os.path.exists(path):
            return []
        try:
            import hashlib as _hash
            with open(path, "r", encoding="utf-8") as _fh:
                snap = json.load(_fh)
            diffs = []
            for f, old_md5 in (snap.get("files") or {}).items():
                cur = None
                if os.path.exists(f):
                    with open(f, "rb") as _fh:
                        cur = _hash.md5(_fh.read()).hexdigest()
                if cur != old_md5:
                    diffs.append({"path": f, "before": old_md5, "after": cur})
            for d in diffs:
                self._write_office_audit(
                    "snap",
                    f"受保护路径变更: {d['path']} md5 {d['before']}→{d['after']}",
                )
            return diffs
        except Exception:
            return []

    def _office_decide(self, tool_name: str, tool_args: dict, reason: str) -> tuple:
        """票 O-1：OFFICE MODE 员工能力矩阵硬拦。

        返回 (verdict, reason)，verdict ∈ {"allow", "deny"}；deny 时已写
        office.guard 审计。矩阵（v0.3.1 终版，普通模式零变化）：
        - git 写操作（不在只读集合的子命令）→ staff/dispatcher 全禁；
        - 文件写（编辑/新建/删除/批量）→ dispatcher 全禁；staff 仅票据
          authorized_paths 豁免路径可写（受保护路径/票据外路径同规则）；
        - shell 命令显式写路径（> >> tee cp mv rm mkdir touch sed -i）→
          同文件写规则；
        - 其余（读、搜索、记忆、汇报等）→ 放行。
        """
        # 1) execute_terminal：git 写子命令全禁 + shell 显式写路径执法
        if tool_name == "execute_terminal":
            command = tool_args.get("command", "") or ""
            sub = _find_git_subcommand(command)
            if sub is not None and not is_git_readonly_subcommand(sub):
                detail = f"git 写操作全禁（git {sub}）"
                self._write_office_audit("guard", detail)
                return ("deny", f"OFFICE MODE（{self.office_role}）：{detail}")
            for p in self._extract_shell_write_paths(command):
                v, r = self._office_path_write_rule(p)
                if v != "allow":
                    self._write_office_audit("guard", r)
                    return ("deny", f"OFFICE MODE（{self.office_role}）：{r}")
            return ("allow", "")
        # 2) 文件写工具：目标路径逐一执法
        if tool_name in self._OFFICE_WRITE_TOOLS:
            for p in self._extract_file_write_paths(tool_name, tool_args):
                v, r = self._office_path_write_rule(p)
                if v != "allow":
                    self._write_office_audit("guard", r)
                    return ("deny", f"OFFICE MODE（{self.office_role}）：{r}")
            return ("allow", "")
        # 3) 其余工具：放行
        return ("allow", "")

    def _extract_shell_write_paths(self, command: str) -> list[str]:
        """从 shell 命令提取显式写目标路径（尽力而为，防绕过）。

        覆盖：> / >> / 2> 重定向、tee/mkdir/touch（全部参数）、
        cp/mv（目标=最后一个非选项参数）、sed -i（目标=最后一个非选项参数）。
        排除 /dev/*（重定向到 /dev/null 是常态，不拦）与选项 token。
        提取不到 → 空列表（执法聚焦显式路径写，包管理类写留给票据/人工）。
        """
        paths = []
        try:
            import shlex as _shlex_mod
            tokens = _shlex_mod.split(command)
        except Exception:
            tokens = command.split()
        # 重定向目标
        for m in re.finditer(r'(?:\d?>|>)\s*([^\s;&|<>]+)', command):
            if not m.group(1).startswith(("-", "$")):
                paths.append(m.group(1))
        # 命令族
        for i, tok in enumerate(tokens):
            if tok in ("tee", "mkdir", "touch"):
                for t in tokens[i + 1:]:
                    if not t.startswith("-"):
                        paths.append(t)
            elif tok in ("cp", "mv"):
                args = [t for t in tokens[i + 1:] if not t.startswith("-")]
                if args:
                    paths.append(args[-1])
        # sed -i：目标=最后一个非选项参数
        if "sed" in tokens and any(t == "-i" or t.startswith("-i") for t in tokens):
            args = [t for t in tokens[tokens.index("sed") + 1:] if not t.startswith("-")]
            if args:
                paths.append(args[-1])
        return [p for p in paths if p and not p.startswith("/dev/")]

    def _extract_file_write_paths(self, tool_name: str, tool_args: dict) -> list[str]:
        """文件写工具的目标路径提取（edit_file/file_writer/delete_file/file_operation）。"""
        paths = []
        if tool_name == "edit_file":
            p = tool_args.get("file_path") or tool_args.get("path")
            if p:
                paths.append(str(p))
        elif tool_name == "file_writer":
            p = tool_args.get("path")
            if p:
                paths.append(str(p))
        elif tool_name == "delete_file":
            p = tool_args.get("path")
            if p:
                paths.append(str(p))
        elif tool_name == "file_operation":
            action = tool_args.get("action", "")
            if action in ("write", "batch_write", "delete"):
                p = tool_args.get("path") or tool_args.get("file_path")
                if p:
                    paths.append(str(p))
                for f in tool_args.get("files") or []:
                    if isinstance(f, dict) and f.get("path"):
                        paths.append(str(f["path"]))
        return paths

    def _office_path_write_rule(self, path: str) -> tuple:
        """票 O-1：单路径写规则——staff 票据豁免 / dispatcher 全禁。"""
        if self.office_role == "dispatcher":
            return ("deny", f"dispatcher 只读：禁止写 {path}")
        # staff：票据 authorized_paths 为唯一豁免通道（受保护路径豁免同此链）
        if self._office_ticket_allows(path):
            return ("allow", f"票据 authorized_paths 豁免写 {path}")
        return ("deny", f"staff 无授权：禁止写 {path}（票据 authorized_paths 为唯一豁免通道）")

    def _office_ticket_allows(self, path: str) -> bool:
        """票 O-1：票据授权书——只看 BOBO_TICKET 指定的当前会话票据。

        当前会话票据 = 环境变量 BOBO_TICKET（启动注入）。豁免判定：
        路径命中 该票据 frontmatter authorized_paths → staff 放行
        （dispatcher 无此通道，见 _office_path_write_rule）。
        未设置 BOBO_TICKET / 票据不存在 / 路径未列出 → 一律无豁免。
        绝不扫描全部 data/tickets/*.md（否则任何一张常驻票据都会变成
        永久豁免后门——TICKET-O1 自身 authorized_paths 含 core/engine.py，
        扫全目录等于让 staff 永远能写核心文件）。
        """
        ticket_id = getattr(self, "office_ticket", None)
        if not ticket_id:
            return False
        p = path.strip().lstrip("./")
        if p.startswith("/"):
            try:
                p = os.path.relpath(p, os.getcwd())
            except Exception:
                pass
        try:
            import glob as _glob
            import fnmatch as _fnmatch
            for fp in _glob.glob(os.path.join(self._TICKETS_DIR, "*.md")):
                try:
                    with open(fp, "r", encoding="utf-8") as _f:
                        text = _f.read()
                except Exception:
                    continue
                # 只认 frontmatter ticket 字段 == BOBO_TICKET 的那一张
                if self._parse_frontmatter_value(text, "ticket") != ticket_id:
                    continue
                for a in self._parse_frontmatter_list(text, "authorized_paths"):
                    a = a.strip().lstrip("./")
                    if not a:
                        continue
                    if (a in ("*", "**") or
                            p == a or p.startswith(a.rstrip("/") + "/") or
                            _fnmatch.fnmatch(p, a)):
                        return True
        except Exception:
            return False
        return False

    @staticmethod
    def _parse_frontmatter_value(text: str, key: str) -> str:
        """极简 frontmatter 标量字段解析（`key: value`），损坏/缺失 → ""。"""
        if not text.startswith("---"):
            return ""
        end = text.find("\n---", 3)
        block = text[3:end] if end > 0 else text[3:]
        for line in block.splitlines():
            line = line.strip()
            if line.startswith(key + ":"):
                return line.split(":", 1)[1].strip().strip('"').strip("'")
        return ""

    def _workspace_recon(self) -> str:
        """票 L1：收工自动对账 —— 只读 git 工作区实况注入。

        收工闸触发（放行/熔断/干净收工）时执行只读 git status + diff --stat，
        把"工作区实况"注入终稿，堵汇报失实（台账与汇报必须与实况一致）。
        只读命令（status/diff --stat），绝不执行写操作；失败静默返回空串，
        不阻塞收工（事件总线铁律）。
        """
        import subprocess as _sp
        try:
            r1 = _sp.run(
                ["git", "status", "--short"],
                capture_output=True, text=True, timeout=5,
                cwd=os.getcwd(),
            )
            r2 = _sp.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, timeout=5,
                cwd=os.getcwd(),
            )
            status_out = (r1.stdout or "").strip() if r1.returncode == 0 else ""
            diff_out = (r2.stdout or "").strip() if r2.returncode == 0 else ""
            if not status_out and not diff_out:
                return ""  # 工作区干净 → 无需对账注入
            parts = ["\n\n── 工作区实况（收工对账，只读）──"]
            if status_out:
                lines = status_out.splitlines()
                parts.append(f"git status --short: {len(lines)} 项变更")
                parts.append("\n".join(lines[:20]) + ("\n…（截断）" if len(lines) > 20 else ""))
            if diff_out:
                parts.append("git diff --stat:")
                parts.append(diff_out[:800])
            parts.append("台账与汇报必须与以上工作区实况一致（完成项逐条带证据，未完成项带原因与下一步）。")
            return "\n".join(parts)
        except Exception:
            return ""

    def _ledger_field_issues(self) -> list[dict]:
        """票 C：台账字段质量扫描（收工闸 auto 硬拦的判定内核）。

        返回缺字段项列表 [{id, missing: [字段名, ...]}]；全合规 → []。
        规则：每项必须有非空 verify；status==done 还必须有非空 evidence。
        老格式台账（无新字段）→ 一律视同缺字段（裁决 1，无迁移豁免）。
        """
        issues = []
        for e in self.task_ledger:
            missing = []
            if not (e.get("verify") or "").strip():
                missing.append("verify")
            if e.get("status") == "done" and not (e.get("evidence") or "").strip():
                missing.append("evidence")
            if missing:
                issues.append({"id": e.get("id", "?"), "missing": missing})
        return issues

    def _detect_ledger_backfill(self, prev_ledger: list, tool_names: list) -> bool:
        """票 O8-2：事后补账判定内核（收工闸补账闸的检测）。

        补账特征：本工具轮含 task_ledger 调用，且创建前台账为空（无历史轮次 = 非 resume），
        轮末新台账 >=2 项且 done 占比 >=80%（全部/大部直接标 done，创建与 done 无中间轮次）。
        resume 恢复既有台账（create 前已有非空台账 = 有历史轮次）→ 豁免，返回 False。
        票 R3-a：施工证据豁免——create 后存在任何非 ledger 工具轮（真实施工痕迹）→
        全 done 不算补账。补账的本质是"没干活直接标 done"，不是"干完活再登记"。
        """
        if "task_ledger" not in tool_names:
            return False
        if prev_ledger or len(self.task_ledger) < 2:
            return False
        # 票 R3-a：施工证据豁免——历史中任意非 ledger 工具轮 = 真实施工痕迹
        for _m in getattr(self, "history", []) or []:
            _tc = _m.get("tool_calls") if isinstance(_m, dict) else None
            if not _tc:
                continue
            for _call in _tc:
                _fn = (_call.get("function") or {}).get("name", "") if isinstance(_call, dict) else ""
                if _fn and _fn != "task_ledger":
                    return False
        done_cnt = sum(1 for e in self.task_ledger if e.get("status") == "done")
        return done_cnt >= max(1, int(len(self.task_ledger) * 0.8))

    @staticmethod
    def _parse_frontmatter_list(text: str, key: str) -> list[str]:
        """极简 frontmatter 列表解析（不依赖 pyyaml）：--- 块内 `key:` 下的
        `- item` 行。损坏/缺失 → 空列表。"""
        if not text.startswith("---"):
            return []
        end = text.find("\n---", 3)
        block = text[3:end] if end > 0 else text[3:]
        in_key = False
        out = []
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if ":" in line and not line.startswith("-"):
                in_key = (line.split(":", 1)[0].strip() == key)
                continue
            if in_key and line.startswith("- "):
                out.append(line[2:].strip().strip('"').strip("'"))
        return out

    def _write_office_audit(self, event_type: str, detail: str) -> None:
        """票 O-1：office.* 审计事件（office.role / office.guard）统一出口。"""
        event = {
            "sid": getattr(self, "sid", ""),
            "role": getattr(self, "office_role", None),
            "detail": detail,
        }
        event_bus.write(f"office.{event_type}", event)

    def _build_handoff_list(self) -> str:
        """票 AUTO-D D-2 + 票 AUTO-G2：收工交接清单——从 events.jsonl 现查本会话 auto 拒绝记录。

        过滤 type=="auto.decide" and sid==self.sid and verdict=="deny"，
        同命令去重（按 command 首次出现），黑名单与外部不可逆分节渲染。
        票 AUTO-G2 增量：只列 ts > self.handoff_watermark 的新拒绝；水位线为 None
        （首回合/无记录）时列全部（兼容现状）。扫描后把本回合最后一条 deny 的 ts
        记入 _handoff_last_ts，由 run_engine 回写 session 持久化为新水位线——
        下次收工不再重复糊出已交接条目（陈年旧账退场）。
        正常模式不写 auto.decide（无清单）；清单为空返回 ""。
        读失败 / 行解析失败 → 静默跳过，绝不阻塞收工（事件总线铁律）。
        """
        try:
            with open(event_bus.filepath, "r", encoding="utf-8") as _f:
                _lines = _f.readlines()
        except Exception:
            return ""
        _sid = getattr(self, "sid", "")
        _wm = self.handoff_watermark
        _last_ts = self._handoff_last_ts
        blacklisted: dict[str, str] = {}    # command -> reason
        irreversible: dict[str, str] = {}   # command -> reason
        for _line in _lines:
            _line = _line.strip()
            if not _line:
                continue
            try:
                _ev = json.loads(_line)
            except Exception:
                continue
            if _ev.get("type") != "auto.decide" or _ev.get("sid") != _sid:
                continue
            if _ev.get("verdict") != "deny":
                continue
            _ts = _ev.get("ts") or 0.0
            if _wm is not None and _ts <= _wm:
                continue  # 票 AUTO-G2：已交接旧账不重复糊出
            _cmd = (_ev.get("command") or "").strip()
            _reason = _ev.get("reason") or ""
            if not _cmd:
                continue
            if _ts > (_last_ts or 0.0):
                _last_ts = _ts
            if _reason.startswith("危险黑名单硬锁"):
                blacklisted.setdefault(_cmd, _reason)
            else:
                irreversible.setdefault(_cmd, _reason)
        self._handoff_last_ts = _last_ts  # 供 run_engine 收工回写为新水位线
        _parts: list[str] = []
        if blacklisted:
            _parts.append("【危险黑名单（系统硬锁，禁止任何途径执行）】")
            _parts += [f"- {c}：{r}" for c, r in blacklisted.items()]
        if irreversible:
            _parts.append("【外部不可逆（需人工确认后执行）】")
            _parts += [f"- {c}：{r}" for c, r in irreversible.items()]
        if not _parts:
            return ""
        return "\n\n📋 待人工执行清单\n" + "\n".join(_parts)

    # ── TICKET-COMPUTER-USE-ROUTE（COST-3 特批标记）：computer use 路由模式 helper 集 ──
    def _cu_active(self) -> bool:
        """computer use 模式是否开（只读 getter）。"""
        return bool(self._computer_use_mode_getter is not None
                    and self._computer_use_mode_getter())

    def _cu_system_prompt(self, sys_prompt: str) -> str:
        """computer use 模式 → 注入路由偏好到 system prompt（票 ④）。"""
        if not self._cu_active():
            return sys_prompt
        return sys_prompt + (
            "\n\n【computer use 模式】界面/搜索/操作类任务优先用 computer_use 工具"
            "快速直接操作，一次定位就操作，不深度推理。")

    def _cu_llm_kw(self, llm_has_tool_calls: bool) -> dict:
        """computer use 模式 + 工具轮 → thinking_disabled=True（快速直接操作，不深度推理）。"""
        if self._cu_active() and llm_has_tool_calls:
            return {"thinking_disabled": True}
        return {}

    def _build_system_prompt(self) -> str:
        return """你是 Bobo，一个专业的个人智能助手。

## 核心原则

- 用户让你做简单的事时直接执行。复杂任务先列计划再逐步执行。
- **可以一次发送多个不冲突的编辑操作（edit_file/file_operation）。不冲突的判断标准：同时改不同文件是安全的，同时改同一文件的不同部分是安全的。如果两个编辑操作要改同一段代码，先改一个，结果返回后再改另一个。**
- **重要规则：单独的纯文字回复 = 任务结束。如果你还有工作要做，回复必须同时包含工具调用。不要只做"进度汇报"而不调工具。**
- 如果工具调用失败，尝试替代方案，不要编造结果。诚实报告阻塞比伪造输出好。
- 在完成任务之前，继续调用工具。不要提前停止。

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

每个任务回合结束时，你的最后一条回复必须是简短的收工汇报，用自然的语言交底，逐条交底，禁止"OK / 完成 / 未完成"式一句话（质量硬性要求 · 票 LEDGER-1）：

- **答复优先**（票 R2b）：最终回复第一要义是**直接回答用户当前问题 / 汇报用户要的事**，把你对问题的分析结论落到纸上；台账状态、待人工清单只能作为附属段落跟在答复之后，禁止以台账/清单代替答复。
- **完成项**：逐条列出，每条必须带证据（文件路径 / 测试数字 / commit / 返回值）。例如"修好了 X（core/engine.py 字段闸改放行，py_compile 通过）"，不要只写"修好了 X"。
- **未完成项**：逐条列出，每条带具体原因与下一步动作（如"卡在 X：环境缺依赖，下一步装依赖后重跑"）。
- **台账对照**：有任务台账时对照台账逐项销账说明，与台账状态一致。
- **对账一致**：收工闸已注入"工作区实况"（git status/diff --stat）时，汇报内容必须与实况一致——实况里改了哪些文件，汇报就得交代哪些文件；实况有未跟踪改动，汇报不得声称全部完成。
- 全部完成就明确说"全部完成"，但"全部完成"必须建立在逐条证据之上。

禁止以工具调用框或半截过程话收尾。纯闲聊回合（问候、确认、问答）不受此限，自然回复即可。

## 任务台账（建账纪律 · 票 R2a 软引导版）

- 遇到多步施工任务（改代码/多文件/多阶段）时主动建账防丢；简单问答、查资料、一两步能做完的事不要建账，直接回答。台账是你的工具，不是仪式。
- 一旦自愿建账：调用 task_ledger create 时，每项必须**当场**带 verify（怎么算做完、怎么验证）与 evidence（完成证据）字段，禁止收工前补登记；字段闸/补账检测/批量销账检测照常执行——自建的账必须认真销。
- 完成一项立即 update 销账（标 done 时带 evidence）。
- 无账回合收工回复禁止出现台账段（📋 台账 只在真的有账时显示）。

## 可信度

- 工具失败时，尝试至少一种替代方法（web_search 超时就改 web_extract，grep 失败就改 os.walk）。
- 所有方法都失败时，直接告诉用户"我做不到"以及原因。不要假装成功。
- 每次声称完成时，提供具体证据（文件路径、返回值）。
- 删除、移动、重命名的文件会自动备份到回收站（~/.bobo/trash/），可用 restore_checkpoint 撤销。

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
        return None

    def _compress_changelog(self):
        self.tracker.compress_changelog()

    def _check_guards(self) -> bool:
        # 已移除 5 项不必要的护栏（2026-07-22 分析）：
        # - 搜索 ≥3 次注入停止提示 → 复杂任务天然需要多次搜索
        # - 同文件/搜索重复 ≥3 次 → 重读文件有合法理由
        # - current_depth 35/45 步提醒 → LLM 无法理解步数含义
        # 保留：
        # - current_tool_round 分流（票 CORE-R1：60% 水位早提示 + 150 线死循环/在推进分流）
        # - current_depth > 200 → 终极保险丝，防止真正的死循环
        # 铁律不动：200 深度硬断、500 步保险丝（MAX_STEPS）、收工闸语义。

        _max_rounds = self._max_tool_rounds()

        # ── 60% 水位早提示：只提示不限制（记 round.watermark，只发一次）──
        _watermark_round = max(1, int(_max_rounds * 0.6))
        if not self._watermark_notified and self.current_tool_round >= _watermark_round:
            self._watermark_notified = True
            _hint = (
                f"轮次过半（{self.current_tool_round}/{_max_rounds}）："
                "请合并工具调用、批量操作、优先完成最小闭环。"
            )
            self._append_to_history("user", _hint)
            event_bus.write("round.watermark", {
                "round": self.current_tool_round,
                "max": _max_rounds,
                "pct": 60,
                "watermark_round": _watermark_round,
            })
            logger.debug("ROUND watermark at %s/%s", self.current_tool_round, _max_rounds)

        # ── 撞线分流：死循环硬掐 / 仍在推进软着陆（记 loop.verdict）──
        if self.current_tool_round > _max_rounds:
            _verdict, _reason = self._judge_loop_verdict()
            event_bus.write("loop.verdict", {
                "round": self.current_tool_round,
                "max": _max_rounds,
                "verdict": _verdict,
                "reason": _reason,
            })
            if _verdict == "stuck":
                _summary = (
                    f"你已达到最大工具调用轮次上限（{_max_rounds} 轮），"
                    "且检测到死循环（连续 5 轮同模式或无推进信号）。"
                    "强制收尾：请立即停止工具调用，给出最终回复。"
                )
            else:
                _summary = (
                    f"你已进入长回合收尾阶段（{_max_rounds} 轮）："
                    "请先完成当前子任务并整理台账，然后收工。"
                )
            self._append_to_history("user", _summary)
            self.current_depth += 1
            return False
        if self.current_depth > 200:
            self._notify("error", {"content": "已达最大循环深度"})
            return True
        return False

    # ── 票 CORE-R1：轮次上限与死循环判定 ──────────────────────────────

    def _max_tool_rounds(self) -> int:
        """BOBO_MAX_TOOL_ROUNDS 环境变量（默认 150，非法值回退 150）。"""
        raw = os.environ.get("BOBO_MAX_TOOL_ROUNDS", "").strip()
        if not raw:
            return 150
        try:
            v = int(raw)
        except (TypeError, ValueError):
            return 150
        return v if v > 0 else 150

    def _round_sig(self, tool_calls: list) -> str:
        """规范化一轮工具调用的签名（同名同参 → 相同签名）。

        arguments 做 json 规范化（键序无关），排序后连接——顺序不同但
        工具集相同视为同模式（pattern 签名）。
        """
        _parts = []
        for _tc in tool_calls:
            _fn = _tc.get("function", {})
            _name = _fn.get("name", "")
            _args = _fn.get("arguments", "{}")
            try:
                _args = json.dumps(json.loads(_args), sort_keys=True, ensure_ascii=False)
            except Exception:
                pass
            _parts.append(f"{_name}|{_args}")
        return "::".join(sorted(_parts))

    def _last_n_tool_rounds(self, n: int = 5) -> list:
        """从 history 取最近 n 轮（带 tool_calls 的 assistant 消息）的签名与工具名。"""
        _rounds = []
        for _m in reversed(self.history):
            if _m.get("role") == "assistant" and _m.get("tool_calls"):
                _names = [_tc.get("function", {}).get("name", "")
                          for _tc in _m["tool_calls"]
                          if _tc.get("function", {}).get("name")]
                _rounds.append({
                    "sig": self._round_sig(_m["tool_calls"]),
                    "names": _names,
                })
                if len(_rounds) >= n:
                    break
        return _rounds

    def _has_progress_signal(self, recent: list) -> tuple[bool, str]:
        """最近 n 轮是否有推进信号：文件写入/diff、台账变更、新工具种类。

        轮级判定全部从 history 最近 n 轮取（recent 参数）——tracker._change_log
        是会话累计列表，不能直接判"本轮有写入"（累计非空 ≠ 最近 n 轮有推进）。
        保守方向：宁可判 progressing（软提醒）也不误掐正在推进的回合。
        """
        # 1) 文件写入/diff / 台账变更：最近 n 轮内出现写类工具调用
        #    （file_operation 可能 action=read，保守算推进——误判 progressing 比误掐安全）
        _WRITE_TOOLS = {"edit_file", "file_operation", "file_writer", "task_ledger"}
        for _r in recent:
            for _name in _r["names"]:
                if _name in _WRITE_TOOLS:
                    return True, f"写类工具调用: {_name}"
        # 2) 新工具种类：最近 n 轮用过的工具名集合 ⊄ 更早轮次集合
        _recent_names = {n for r in recent for n in r["names"]}
        _earlier = set()
        _count = 0
        for _m in reversed(self.history):
            if _m.get("role") == "assistant" and _m.get("tool_calls"):
                if _count >= len(recent):
                    for _tc in _m["tool_calls"]:
                        _nm = _tc.get("function", {}).get("name", "")
                        if _nm:
                            _earlier.add(_nm)
                _count += 1
        _new = _recent_names - _earlier
        # 更早轮次为空（会话刚开始即撞线，无从对比）→ 不判"新工具种类"推进
        if _earlier and _new:
            return True, f"新工具种类: {sorted(_new)[:3]}"
        return False, ""

    def _judge_loop_verdict(self) -> tuple[str, str]:
        """死循环判定：连续 5 轮同模式 或 无推进信号 → stuck，否则 progressing。"""
        _recent = self._last_n_tool_rounds(5)
        _reasons: list[str] = []
        _same = False
        if len(_recent) >= 5:
            _sigs = [r["sig"] for r in _recent]
            _same = all(s == _sigs[0] for s in _sigs)
            if _same:
                _reasons.append(f"连续{len(_recent)}轮同模式({_sigs[0][:60]})")
        _progress, _p_reason = self._has_progress_signal(_recent)
        if not _progress:
            _reasons.append("最近5轮无推进信号（无文件写入/台账变更/新工具种类）")
        if _same or not _progress:
            return ("stuck", "；".join(_reasons) or "连续同模式/无推进")
        return ("progressing", f"仍在推进（{_p_reason}）")

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

    def _extract_takeaways(self, fallback_content: str = "", history: list | None = None,
                           tool_round: int | None = None) -> list[str]:
        """从最近一轮对话中提取 1-2 条值得记住的关键结论（草稿记忆）。

        fallback_content: 当 history 中 assistant 消息未落账时，以此为源。
        history: 可选 history 快照（票 PERF-1 后台沉淀线程用，避免与下一轮
            并发写冲突）；None 时用 self.history（主线程原行为不变）。
        tool_round: 可选工具轮次快照；None 时用 self.current_tool_round。
        """
        import os as _os
        if _os.environ.get("BOBO_TAKEAWAYS", "").lower() == "off":
            return []
        try:
            _hist = history if history is not None else self.history
            _tool_round = tool_round if tool_round is not None else getattr(
                self, "current_tool_round", 0)
            # ── 票 E4a：user 窗口从 [-4:] 扩大为向前回溯 20 条 ──
            # 根因：多轮工具执行后收工，history 末尾常为 assistant/tool 交替，
            # [-4:] 内无 user → user_msg 空 → 静默 return []（失语）。
            _window = _hist[-20:]
            user_msgs = [m.get("content", "") for m in _window
                         if m.get("role") == "user" and m.get("content")]
            asst_msgs = [m.get("content", "") for m in _hist[-4:]
                          if m.get("role") == "assistant" and m.get("content")]
            if not user_msgs or not asst_msgs:
                # 收工闸推迟落账时，用 fallback_content 替代
                if asst_msgs:
                    pass  # 有历史消息正常用
                elif fallback_content:
                    asst_msg = fallback_content
                else:
                    # ── 票 E4a：禁止静默轮——无可提取内容时留原因事件 ──
                    event_bus.write("takeaway.skipped", {
                        "reason": "no_history_content",
                        "sid": getattr(self, "sid", ""),
                    })
                    return []
            else:
                asst_msg = asst_msgs[-1]
            user_msg = user_msgs[-1] if user_msgs else ""
            if not user_msg:
                # ── 票 E4a：回溯仍无 user → 留原因事件，不静默 ──
                event_bus.write("takeaway.skipped", {
                    "reason": "no_user_msg_in_window",
                    "sid": getattr(self, "sid", ""),
                })
                return []
            # ── 预筛闸门：不值得则零成本跳过 ──
            # 终审补漏（2026-07-29）：工具回合无条件放行——工作回合默认有
            # 沉淀价值（任务单原则：宁可多打不可漏记），即便收尾文字很短。
            _has_tool_round = _tool_round > 0
            if not _has_tool_round and not self._takeaway_worthy(user_msg, asst_msg):
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
            # ── ENG-1：提取 LLM 调用补 llm.call 事件（观测盲区修复）+ 小 max_tokens 提速 ──
            # 盲区：_extract_takeaways 直接调 self.llm_caller，绕过了 _call_llm 的事件写入点，
            # events.jsonl 看不到提取调用 → "尾部静默"假象。此处补写 + 限制 512 tokens
            # （提取只需 1-2 条 ≤60 字结论），实测可将 55.7s 级耗时显著压缩。
            _extract_t0 = time.time()
            try:
                response = self.llm_caller(
                    prompt, use_tools=False, max_tokens=512,
                    _interrupt_event=self._interrupt_event,  # 票 INT-1：提取同样可中断
                )
            except LLMInterrupted:
                # 票 INT-1：中断时放弃沉淀（静默返回空，不留 notes.error——
                # 用户主动 stop 不是错误；回合已在主线程正常退场）
                return []
            event_bus.write("llm.call", {
                "session_id": getattr(self, "sid", ""),
                "msg_count": len(prompt),
                "has_tool_calls": False,
                "duration_ms": int((time.time() - _extract_t0) * 1000),
                "stage": "takeaway_extract",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            })
            if isinstance(response, dict) and "error" in response:
                # ── 票 E4a：LLM 提取失败留痕，不静默 ──
                logger.warning("takeaway extract llm error (sid=%s): %s",
                               getattr(self, "sid", ""), response.get("error"))
                event_bus.write("notes.error", {
                    "session_id": getattr(self, "sid", ""),
                    "error": str(response.get("error")),
                    "stage": "takeaway_extract",
                })
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
        except Exception as _e:
            # ── 票 E4a：提取异常留痕（WARNING + notes.error），不静默吞 ──
            logger.warning("takeaway extract failed (sid=%s): %s",
                           getattr(self, "sid", ""), _e)
            event_bus.write("notes.error", {
                "session_id": getattr(self, "sid", ""),
                "error": str(_e),
                "stage": "takeaway_extract",
            })
            return []

    def _run_sedimentation(self, pending_content: str) -> None:
        """票 PERF-1 事故 1（要求 b）：后台沉淀线程主体。

        takeaway 提取 + 草稿记忆镜像 + living_notes 成文整体移出回合关键路径：
        主线程发完回复先退场（message.complete 不被 LLM 调用阻塞），沉淀在
        daemon 线程跑；失败只留事件（WARNING + notes.error），绝不影响回合。

        输入用快照（history 浅拷贝 + 工具轮次），避免与下一轮并发写冲突；
        event_bus 自带 threading.Lock，事件写入线程安全。
        """
        _sid = getattr(self, "sid", "")
        try:
            _hist_snap = list(self.history)
            _tool_round_snap = getattr(self, "current_tool_round", 0)
            takeaways = self._extract_takeaways(
                fallback_content=pending_content,
                history=_hist_snap,
                tool_round=_tool_round_snap,
            )
            if takeaways:
                # ── 草稿记忆镜像（失败静默，原语义不变）──
                try:
                    from tools.v5_memory import add_entry, _save, _load, _write_lock
                    for t in takeaways:
                        entry = add_entry(t, entry_type="draft")
                        if entry:
                            entry["signal_score"] = 30
                            entry["is_draft"] = True
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
                # ── 主题笔记钩子（LN-2，失败只留痕不阻塞）──
                try:
                    from tools.living_notes import write_living_notes
                    _ln_user_msgs = [
                        m.get("content", "") for m in _hist_snap[-20:]
                        if m.get("role") == "user" and m.get("content")
                    ]
                    _ln_asst_msgs = [
                        m.get("content", "") for m in _hist_snap[-4:]
                        if m.get("role") == "assistant" and m.get("content")
                    ]
                    _full_reply = (_ln_asst_msgs[-1] if _ln_asst_msgs
                                   else (pending_content or ""))
                    def _ln_llm(prompt, **kw):
                        # 票 INT-1：沉淀 LLM 调用同样接受中断——非流式入口前检查，
                        # 置位即抛 LLMInterrupted 放弃本次沉淀（由下方 except 单独捕获）
                        if (self._interrupt_event is not None
                                and self._interrupt_event.is_set()):
                            raise LLMInterrupted("interrupt during living notes")
                        kw.setdefault("_interrupt_event", self._interrupt_event)
                        # TICKET-PROVIDER-ADAPTER（COST-3 特批标记，P5-400 同款教训）：
                        # living_notes 在异步线程里用主流程 llm_caller 实例做独立
                        # 新对话（无历史、use_tools=False）——必须 thinking_disabled=True
                        # 冷调用，否则与主流程工具轮链并发时破坏 DeepSeek thinking
                        # 回传状态 → HTTP 400 "reasoning_content must be passed back"
                        # （实弹 2026-08-21 18:34，living_notes 超时线程 + 主流程并发）。
                        kw.setdefault("thinking_disabled", True)
                        return self.llm_caller(prompt, **kw)
                    write_living_notes(
                        takeaways,
                        _ln_user_msgs[-1] if _ln_user_msgs else "",
                        _sid,
                        _ln_llm,
                        full_reply=_full_reply,
                    )
                except LLMInterrupted:
                    # 票 INT-1：中断时放弃沉淀——用户主动 stop，不留 notes.error
                    logger.info("living notes hook interrupted (sid=%s)", _sid)
                except Exception as _ln_err:
                    logger.warning("living notes hook failed (sid=%s): %s",
                                   _sid, _ln_err)
                    event_bus.write("notes.error", {
                        "session_id": _sid,
                        "error": str(_ln_err),
                        "stage": "ln_hook",
                    })
                # ── 票 P0-2 通道 A：对话信号判定（只记录不动作）──
                # guidance 四条（工作流/负强化/隐含偏好/强信号）LLM 判定，
                # 命中写 data/logs/signal_log.jsonl。零动作铁律：绝不写
                # knowledge_base / memory / 不注入；失败静默降级不阻塞回合。
                try:
                    from tools.signal_logger import judge_and_log_signal
                    _sig_user_msgs = [
                        m.get("content", "") for m in _hist_snap[-20:]
                        if m.get("role") == "user" and m.get("content")
                    ]
                    _sig_last = (_sig_user_msgs[-1] if _sig_user_msgs else "")
                    if _sig_last:
                        def _sig_llm(prompt, **kw):
                            # 票 INT-1：判定 LLM 调用同样接受中断
                            if (self._interrupt_event is not None
                                    and self._interrupt_event.is_set()):
                                raise LLMInterrupted(
                                    "interrupt during signal judge")
                            kw.setdefault("_interrupt_event",
                                          self._interrupt_event)
                            return self.llm_caller(prompt, **kw)
                        _sig_t0 = time.time()
                        _sig_result = judge_and_log_signal(
                            _sig_last, _sid, _sig_llm,
                            history=_sig_user_msgs,
                        )
                        # 复用 ENG-1 先例：判定 LLM 调用补 llm.call 事件
                        if _sig_result.get("llm_called"):
                            event_bus.write("llm.call", {
                                "session_id": _sid,
                                "msg_count": 2,
                                "has_tool_calls": False,
                                "duration_ms": _sig_result.get(
                                    "duration_ms",
                                    int((time.time() - _sig_t0) * 1000)),
                                "stage": "signal_judge",
                                "prompt_tokens": 0,
                                "completion_tokens": 0,
                                "total_tokens": 0,
                            })
                        if _sig_result.get("logged"):
                            logger.info(
                                "signal logged (sid=%s type=%s reason=%s)",
                                _sid,
                                _sig_result["record"].get("signal_type"),
                                _sig_result.get("reason"))
                except LLMInterrupted:
                    # 票 INT-1：中断时放弃判定——用户主动 stop
                    logger.info("signal judge interrupted (sid=%s)", _sid)
                except Exception as _sig_err:
                    logger.warning("signal judge hook failed (sid=%s): %s",
                                   _sid, _sig_err)
                    event_bus.write("notes.error", {
                        "session_id": _sid,
                        "error": str(_sig_err),
                        "stage": "signal_judge",
                    })
        except Exception:
            logger.exception("sedimentation failed (sid=%s)", _sid)

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
        # 票 COST-3：insert(0) 改为 append——头部插入会断裂 DeepSeek 前缀缓存
        # （首个工具轮触发后，后续所有轮 prompt 头部多出该条，与首轮公共前缀
        # 只剩系统提示，实测命中率 97%→52.8%）。append 到 history 末尾：工具
        # 结果之后、下一轮 user 之前，位置固定后跨轮逐字节稳定，前缀不破坏。
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
                self.history.append({
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

        # ── TICKET-024：token 驱动压缩（主线），条数 200 硬上限兜底 ──
        # 只在空闲态压缩——工具执行中途修改 history 会导致
        # tool_calls/tool_result 配对断裂 → API 报错 → engine 崩溃。
        # 每轮最多压缩一次。
        if (not self._compressing and not self._compressed_this_turn
                and self.state != self.STATE_EXECUTING):
            from core.context import _get_msg_count_budget, _estimate_tokens, _get_context_budget

            est_tokens = _estimate_tokens(self.history)
            token_budget = _get_context_budget()
            msg_count = len(self.history)
            msg_budget = _get_msg_count_budget()

            # TICKET-024：token 优先触发
            trigger_token = est_tokens > token_budget
            # 条数兜底（200 硬上限）
            trigger_msg = msg_count > msg_budget

            if trigger_token or trigger_msg:
                trigger_reason = "token" if trigger_token else "msg_fallback"
                if os.environ.get("BOBO_SHOW_COMPRESS") == "1":
                    self._notify("thinking", {
                        "phase": "compressing",
                        "message": f"正在压缩历史上下文...（{est_tokens} tokens, "
                                   f"预算 {token_budget}, 触发: {trigger_reason}）"
                    })
                self._compress_history()
                self._compressed_this_turn = True
            elif est_tokens > token_budget * 0.5:
                # 接近阈值时打补记标记（retroactive mark）
                self.tracker.retroactive_mark()

        # ── TICKET-COMPUTER-USE-ROUTE（COST-3 特批标记）：computer use 模式 → 路由偏好注入 system prompt ──
        _sys_prompt = self._cu_system_prompt(self.system_prompt)

        messages = self.injector.build_messages(
            system_prompt=_sys_prompt,
            user_input=self.current_user_input or "",
            tools_schema=TOOLS_SCHEMA,
            extra_categories=self._used_categories,
            session_id=getattr(self, 'sid', ""),
        )

        self._notify("thinking", {"phase": "calling_llm", "message": "正在思考..."})

        # ── 票 TICKET-021：本轮压缩完成后，下轮置顶"历史已压缩"指引 ──
        if self._compressed_this_turn:
            self._just_compressed = True

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


        # 票 COST-3：工具集会话内逐字节稳定——不再按查询分类过滤。
        # 原 _get_filtered_tools 每轮按分类发 15~31 个不同子集 → tools 段逐轮变
        # → 请求前缀在 tools 处断裂 + 能力随分类抖动（rounds.jsonl 实测：tools
        # 变化的轮命中跌至 2.9%）。全量 31 个 schema 固定发送（TOOLS_SCHEMA 为
        # 静态列表，顺序稳定）。成本账（真实数据，见票据报告）：全量 ≈8020
        # tokens/轮、命中 1/10 价 ≈802 当量；过滤子集 ≈5691 tokens/轮但未命中
        # 全价 + 前缀断裂拖累 messages 命中 → 全量稳定更优，且工具可用性 100%
        # 不缩水（owner 红线）。describe_tool 取件的 _extra_tools 走执行器注册，
        # 不依赖 prompt schema，不受影响。
        filtered_tools = TOOLS_SCHEMA
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

        # ── TICKET-COMPUTER-USE-ROUTE（COST-3 特批标记）：computer use 模式 + 工具轮 → thinking_disabled=True ──
        # （快速直接操作工具，不深度推理；关闭模式则不注入，恢复正常 thinking）
        _call_kw = self._cu_llm_kw(_llm_has_tool_calls)

        response = self.llm_caller(
            messages,
            stream_callback=_on_token,
            retry_callback=_on_retry,
            tools_override=filtered_tools,
            session_id=self.sid,
            reasoning_callback=_on_reasoning,
            _interrupt_event=self._interrupt_event,  # 票 INT-1：流式每 chunk 可中断
            **_call_kw,
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
                    _interrupt_event=self._interrupt_event,  # 票 INT-1：重试同样可中断
                    **_call_kw,
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
                           tool_calls: list = None, tool_results: list = None,
                           thinking: str = None):
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
            # TICKET-GUI-F8：思考文本随 assistant 消息落盘（只记录，不改 TUI 渲染路径
            # 与思考生成逻辑；resume 时 GUI 据此恢复折叠思考框）
            if thinking:
                msg["thinking"] = thinking
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
            try:
                content, tool_calls = self._call_llm()
            except LLMInterrupted:
                # 票 INT-1：流式中断（思考中 stop）→ 走既有 interrupted 路径正常退场。
                # 事件链 engine.cancel.requested → STATE interrupted → adapter 见
                # interrupt_event.is_set() → thread.exit reason=interrupted。
                self._emit_state_change(self.STATE_ERROR, "interrupted")
                return
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
                # 票 R3-c：仅当声称完成且本回合零 tool.exec 才触发（干完活正常收尾不误伤）
                elif self.verifier.check_and_inject(self.history, content,
                                                    tool_exec_count=self._round_tool_exec_count):
                    self._pending_content = None
                    self._pending_tool_calls = None
                    self.current_depth += 1
                    self._emit_state_change(self.STATE_THINKING, "tool calls pending")
                else:
                    # ── 票 G2-1：收工闸前移（先账后复）──
                    # 四个闸在进入 RESPONDING 前执行；账不平 → 回注 THINKING（用户只看到 Working）。
                    # 闸全过才进 RESPONDING（放行路径）。纯聊天快速通道语义保留（tool_round==0 直放）。
                    # ── 票 G2-E4a：提取/笔记前移到闸前（旧语义对齐）──
                    # 旧时序：回复文本一生成即进 RESPONDING 提取 takeaways 并写笔记（提取先于闸）。
                    # G2 把闸前移到 THINKING 后，若提取仍留 RESPONDING，闸回注会先消耗提取用的
                    # LLM 响应预算（E4a 回归：提取被饿死 → takeaway.extracted 丢失）。
                    # 故提取+笔记块整体前移到此（闸之前）：事件链 takeaway.extracted → notes.written
                    # 与旧语义一致，闸只决定"回注不发回复"，不干扰提取。
                    if self._pending_content and self.proactive.mode != "off":
                        # ── 票 PERF-1 事故 1（要求 b）：沉淀后台化 ──
                        # takeaway 提取 + 草稿记忆镜像 + living_notes 成文整体移出
                        # 回合关键路径：主线程发完回复先退场（message.complete 不被
                        # LLM 调用阻塞），沉淀在 daemon 线程跑；失败只留事件不影响回合。
                        # 事件链 takeaway.extracted → notes.written 语义保留（延迟到后台）。
                        if self.test_mode:
                            # 测试模式：同步执行——E4a 等测试断言 run 返回后事件已发，
                            # 时序确定性优先；生产（gateway）走后台线程。
                            self._run_sedimentation(self._pending_content)
                        else:
                            try:
                                import threading as _threading
                                _sed_thread = _threading.Thread(
                                    target=self._run_sedimentation,
                                    args=(self._pending_content,),
                                    daemon=True,
                                    name=f"sediment-{getattr(self, 'sid', '')}",
                                )
                                _sed_thread.start()
                            except Exception as _sed_err:
                                logger.warning("sedimentation thread start failed (sid=%s): %s",
                                               getattr(self, "sid", ""), _sed_err)
                                event_bus.write("notes.error", {
                                    "session_id": getattr(self, "sid", ""),
                                    "error": str(_sed_err),
                                    "stage": "ln_hook",
                                })
                    # ── 票 O3-1：收工闸快照比对（抓漏不执法：只审计+告警，不阻断收工）──
                    # office 角色会话：回合内写类工具通过决策链后已生成 guardsnap，
                    # 收工比对当前 md5——不一致 → office.snap 审计 + 回复明示告警。
                    # 普通模式（office_role is None）整段跳过，零开销零行为变化。
                    if self.office_role is not None and self._pending_content:
                        _snap_diffs = self._verify_snapshot()
                        if _snap_diffs:
                            _snap_paths = "; ".join(
                                d["path"] for d in _snap_diffs[:3]
                            ) + ("…" if len(_snap_diffs) > 3 else "")
                            _snap_warn = (
                                "\n\n⚠️ OFFICE MODE 快照告警：受保护路径在回合内被改写"
                                f"（{len(_snap_diffs)} 项：{_snap_paths}）——已写 office.snap"
                                "审计，属事后抓漏，不阻断收工。"
                            )
                            self._pending_content = (self._pending_content or "") + _snap_warn
                    # ── 票Z 缝2：承诺检测闸（未来时模式识别，共享 _ledger_reinject_count） ──
                    if self._pending_content:
                        _COMPLETION_WORDS = {"已完成", "全部完成", "测试通过", "已交付", "已全部完成"}
                        if not any(w in self._pending_content for w in _COMPLETION_WORDS):
                            _PROMISE_RE = re.compile(
                                r'(我将|我会|让我|接下来|下一步|稍后|一会|待会).{0,10}(继续|执行|运行|跑|处理|完成|修复|修改|测试)'
                                r'|(现在|马上|这就).{0,6}(跑|执行|运行|开始)'
                            )
                            if _PROMISE_RE.search(self._pending_content):
                                _has_pending = any(e.get("status") != "done" for e in self.task_ledger)
                                if _has_pending or not self.task_ledger:
                                    event_bus.write("goal_gate.promise_detected", {
                                        "session_id": getattr(self, "sid", ""),
                                        "content_snippet": self._pending_content[:100],
                                    })
                                    # 票 R3-d：熔断前开确认通道——检测到施工证据（写类工具/多次工具执行）
                                    # 直接放行，不逼模型"继续"（有真实施工痕迹就不是空口承诺）。
                                    if self._round_had_write_tool or self._round_tool_exec_count >= 3:
                                        event_bus.write("goal_gate.released", {
                                            "session_id": getattr(self, "sid", ""),
                                            "reason": "construction_evidence",
                                            "tool_exec_count": self._round_tool_exec_count,
                                        })
                                        warning = "\n\n⚠️ 施工证据已确认，引擎放行"
                                        self._pending_content = (self._pending_content or "") + warning
                                    elif self._ledger_reinject_count < 2:
                                        self._ledger_reinject_count += 1
                                        rej_msg = "检测到未完成的承诺。请继续执行，不要说明、不要道歉，直接继续。"
                                        self._append_to_history("user", rej_msg)
                                        self._pending_content = None
                                        self._pending_tool_calls = None
                                        self.current_depth += 1
                                        logger.debug("GATE promise re-injection #%d",
                                                     self._ledger_reinject_count)
                                        self._emit_state_change(self.STATE_THINKING, "promise re-injection")
                                        return
                                    else:
                                        event_bus.write("goal_gate.released", {
                                            "session_id": getattr(self, "sid", ""),
                                            "reason": "promise_exhausted",
                                            "reinject_count": self._ledger_reinject_count,
                                        })
                                        warning = "\n\n⚠️ 承诺检测达熔断上限，引擎放行"
                                        self._pending_content = (self._pending_content or "") + warning
                    # ── 票 R2b：答复质量闸（先答问题再交账；思考落纸） ──
                    # 轻量启发式（不依赖语义理解）：
                    # 1) 台账/清单腔：回复开头即台账段/清单且总长过短（<120 字）→ 未直接回答问题
                    # 2) 思考落纸：thinking 有实质分析（≥60 字）但回复过短（<80 字）→ 分析没落到回复
                    # 打回每回合至多一次（_reply_quality_reinject_count，防死循环）；
                    # 写类施工回合豁免（施工收尾以交账为主，不误伤）。
                    # 票 R3-b：豁免面扩大——本轮 tool.exec ≥3 次即豁免（读/查施工同样有实质干活，
                    # 不再只认写类工具；有实际执行就不算空口台账腔）。
                    if (self._pending_content and not self._reply_quality_reinject_count
                            and not self._round_had_write_tool
                            and self._round_tool_exec_count < 3):
                        _content = self._pending_content
                        _len = len(_content)
                        _stripped = _content.strip()
                        _quality_hit = False
                        # 台账/清单腔：开头即台账段/清单/纯清单腔
                        _ledgerish_head = (
                            _stripped.startswith("📋")
                            or _stripped.startswith("任务台账")
                            or _stripped.startswith("待人工执行清单")
                            or _stripped.startswith("台账")
                            or _stripped.startswith("完成项")
                        )
                        if _ledgerish_head and _len < 120:
                            _quality_hit = True
                        # 思考落纸：thinking 分析 ≥60 字但回复 <80 字
                        _r = (self._last_reasoning or "").strip()
                        if not _quality_hit and len(_r) >= 60 and _len < 80:
                            _quality_hit = True
                        if _quality_hit:
                            self._reply_quality_reinject_count += 1
                            _rej = (
                                "你的最终回复没有直接回答用户的问题：台账/清单腔过重，或思考里的分析结论"
                                "没落到回复上。请先直接回答用户当前问题、把分析结论的实质内容写到回复里，"
                                "台账状态只能作为附属段落跟在答复之后，然后收工。"
                            )
                            self._append_to_history("user", _rej)
                            self._pending_content = None
                            self._pending_tool_calls = None
                            self.current_depth += 1
                            logger.debug("GATE reply-quality re-injection #1")
                            self._emit_state_change(self.STATE_THINKING, "reply-quality re-injection")
                            return
                    # ── 票 C 收工闸 auto/office 硬拦：台账字段质量闸（先于 pending 回注/熔断判定） ──
                    # 激活条件（票 O8-1）：auto on 或 office on（会话级 get_office_on）。
                    # 普通模式（两者皆无）→ 整段物理跳过，连判定都不经过（零影响铁律）。
                    _gate_active = (self._auto_mode_getter is not None and self._auto_mode_getter())
                    _gate_label = "AUTO MODE"
                    if not _gate_active:
                        try:
                            from bobo_tui_gateway.server import get_office_on as _get_office_on
                            _gate_active = bool(_get_office_on(getattr(self, "sid", "")))
                            if _gate_active:
                                _gate_label = "OFFICE MODE"
                        except Exception:
                            _gate_active = False
                    if _gate_active:
                        # ── 票 O8-2：补账检测闸（先于字段闸：批量创建即全 done = 事后补登记）──
                        # deny + history 追加指令（要求列出下一步真实待办）+ goal_gate.deny
                        # 审计（reason=ledger_backfill）。resume 豁免由 _detect_ledger_backfill
                        # 的 prev 非空判定保证（有历史轮次 → 不置嫌疑）。
                        if self._ledger_backfill_suspect:
                            rej_msg = (
                                f"{_gate_label} 收工拒绝（补账检测）：台账 {len(self.task_ledger)} 项在本轮"
                                "批量创建且全部/大部直接标 done，无中间施工轮次——视为事后补登记。"
                                "请用 task_ledger update 将未完成项改为 pending 并列出下一步真实待办"
                                "（verify/evidence 按字段闸要求补齐），然后继续。不要说明、不要道歉，直接做。"
                            )
                            self._append_to_history("user", rej_msg)
                            self._pending_content = None
                            self._pending_tool_calls = None
                            self.current_depth += 1
                            event_bus.write("goal_gate.deny", {
                                "session_id": getattr(self, "sid", ""),
                                "reason": "ledger_backfill",
                                "items": len(self.task_ledger),
                            })
                            self._emit_state_change(self.STATE_THINKING, "ledger backfill deny")
                            return
                        field_issues = self._ledger_field_issues()
                        if field_issues:
                            # ── 票 L1：deny 降本 —— 缺字段不再强制全上下文重跑 ──
                            # 精简补正指令本轮放行 + 执法记录照留（goal_gate.deny 审计 + 计数）。
                            # 不 return、不 append history 重跑：补正指令随终稿带出，
                            # 模型下轮自然补（省掉全上下文重跑一轮的 +15s 成本）。
                            # 铁律保留：台账执法能力不删（缺字段仍被记录、仍被点名），
                            # 只改同步与成本结构（票 L1 裁决）。
                            self._ledger_field_deny_count += 1
                            _parts = "; ".join(
                                f'{i["id"]} 缺 {", ".join(i["missing"])}' for i in field_issues
                            )
                            event_bus.write("goal_gate.deny", {
                                "session_id": getattr(self, "sid", ""),
                                "reason": "ledger_field_missing",
                                "field_issues": field_issues,
                                "deny_count": self._ledger_field_deny_count,
                                "mode": "pass_with_note",  # L1：本轮放行 + 执法记录照留
                            })
                            logger.debug("LEDGER field-gate note #%d (pass-with-note): %s",
                                         self._ledger_field_deny_count, _parts)
                            self._pending_content = (self._pending_content or "") + (
                                f"\n\n⚠️ {_gate_label} 字段闸记录（第 {self._ledger_field_deny_count} 次，"
                                f"本轮放行）：台账 {len(field_issues)} 项缺字段（{_parts}）。"
                                "收工汇报需给出补正计划：补齐 verify（怎么算做完/怎么验证）与 done 项的 "
                                "evidence（完成证据），或写明卡点转 pending 交接/上报调度员。"
                            )
                    # ── 票 K v2 收工闸：台账检查（引擎执法，不由模型嘴决定收工） ──
                    pending_items = [e for e in self.task_ledger if e.get("status") != "done"]
                    if pending_items:
                        # 票 R3-d：熔断前开确认通道——检测到施工证据（写类工具/多次工具执行）
                        # 直接放行，不逼模型"继续"（有真实施工痕迹就不是空口承诺）。
                        if self._round_had_write_tool or self._round_tool_exec_count >= 3:
                            pending_titles = ", ".join(
                                f'"{e["title"][:30]}"' for e in pending_items
                            )
                            event_bus.write("goal_gate.released", {
                                "session_id": getattr(self, "sid", ""),
                                "reason": "construction_evidence",
                                "tool_exec_count": self._round_tool_exec_count,
                                "pending_items": len(pending_items),
                            })
                            warning = (
                                f"\n\n⚠️ 施工证据已确认，引擎放行（台账 {len(pending_items)} 项未销账：{pending_titles}）"
                            )
                            self._pending_content = (self._pending_content or "") + warning
                            logger.debug("GATE ledger construction-evidence release: %d pending",
                                         len(pending_items))
                        elif self._ledger_reinject_count < 2:
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
                            logger.debug("GATE ledger re-injection #%d: %d items pending",
                                         self._ledger_reinject_count, len(pending_items))
                            self._emit_state_change(self.STATE_THINKING, "ledger re-injection")
                            return
                        else:
                            # 已达 2 次熔断上限 → 放行 done，终稿附加 ⚠️ 遗言 + 事件
                            pending_titles = ", ".join(
                                f'"{e["title"][:30]}"' for e in pending_items
                            )
                            warning = (
                                f"\n\n⚠️ 台账 {len(pending_items)} 项未销账，引擎放行：{pending_titles}"
                            )
                            self._pending_content = (self._pending_content or "") + warning
                            event_bus.write("goal_gate.released", {
                                "session_id": getattr(self, "sid", ""),
                                "reason": "ledger_exhausted",
                                "reinject_count": self._ledger_reinject_count,
                                "pending_items": len(pending_items),
                            })
                            logger.debug("GATE ledger force-release: %d items still pending",
                                         len(pending_items))
                    elif not self.task_ledger:
                        # ── 票 R2a（v2 软限制版）：无账硬闸已拆除 ──
                        # owner 终裁：让 LLM 自己理解复杂度，软限制不做硬限制。
                        # 任何回合不再因为"没建账"被回注；纯读问答/简单任务直接收工。
                        # 自愿建账后的字段闸/补账检测/批量销账检测全部保留（见上方分支）。
                        event_bus.write("task.no_ledger", {
                            "session_id": getattr(self, "sid", ""),
                            "reason": "no ledger (soft limit, R2a)",
                            "tool_round": self.current_tool_round,
                        })
                        logger.debug("GATE no ledger — soft limit (R2a), direct done")
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

            # ── 票 O9：台账基线快照必须在工具执行前 ──
            # O8-2 判定内核前提是"create 前台账为空（无历史轮次 = 非 resume）"。
            # 原实现把 _prev_ledger 放在 _execute_tool_loop 之后快照——task_ledger
            # 工具执行后 engine.task_ledger 已被替换为新账（同轮批量建账全 done），
            # prev 非空 → 误判为 resume 豁免 → 补账闸永不触发（A2 FAIL 根因，TICKET-O9）。
            _prev_ledger = list(self.task_ledger)
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
            # ── 票 O8-2：事后补账检测（紧跟同步，先于一切收工判定）──
            # 工具轮含 task_ledger → 重新评估补账嫌疑：create 前台账为空（无历史轮次，
            # 非 resume）+ 新账 >=2 项且 done 占比 >=80%（全部/大部直接标 done）→ 嫌疑。
            # resume 恢复既有台账（create 前已有非空台账 = 有历史轮次）→ 豁免。
            # agent 修正（update 出 pending 项 / create 含 pending）→ 自动清除嫌疑。
            # 不含 task_ledger 的工具轮 → 嫌疑保持不变（防绕过：不动账直接收工仍被 deny）。
            if self._pending_tool_calls:
                _tc_names = [
                    tc.get("function", {}).get("name", "")
                    for tc in self._pending_tool_calls
                ]
                if "task_ledger" in _tc_names:
                    self._ledger_backfill_suspect = self._detect_ledger_backfill(
                        _prev_ledger, _tc_names
                    )
            self._append_to_history("assistant", self._pending_content,
                                    tool_calls=self._pending_tool_calls,
                                    thinking=self._last_reasoning or None)
            # 票 TICKET-PROVIDER-ADAPTER（COST-3，400 第 4 引信）：_last_reasoning
            # 是全局单值，工具轮链中若不清，下一条 assistant 会复用上一条的
            # reasoning → 历史多条 assistant 共享同一 thinking → REASONING-ECHO
            # 给多条补同一 reasoning_content → DeepSeek 拒绝 → HTTP 400。
            # 落 history 后立即消费即清（下一条 assistant 无新 reasoning 则不落）。
            self._last_reasoning = ""
            self._append_to_history("tool", tool_results=tool_results)
            # ── 票 L1：自动销账辅助（建议性，模型可推翻）──
            # 检测强完成信号：run_tests 全绿（N passed 且无 failed）→ 注入建议，
            # 提示模型用 task_ledger update 标 done（带 evidence）。
            # 只建议不改账（引擎不替模型记账：台账由模型执笔，铁律保留）。
            if tool_results and self.task_ledger:
                _pending_cnt = sum(1 for e in self.task_ledger if e.get("status") != "done")
                if _pending_cnt:
                    for _tr in tool_results:
                        if not isinstance(_tr, dict):
                            continue
                        _c = _tr.get("content") or ""
                        if isinstance(_c, list):
                            _c = " ".join(
                                str(x.get("text", "")) for x in _c if isinstance(x, dict)
                            )
                        _c = str(_c)
                        # 全绿信号：N passed 且无 [1-9] failed（0 failed 不算失败）
                        if re.search(r"\d+\s+passed", _c) and not re.search(r"[1-9]\d*\s+failed", _c):
                            # 票 LEDGER-400 = COST-7（2026-08-19 开票，owner 定调最后信任票）
                            # F2/F3 分支落地：原实现 history.append {"role":"system"} 会把
                            # system 消息硬插在工具轮链中间（assistant(tool_calls)→tool→
                            # system→assistant），DeepSeek thinking 模式要求该结构中间
                            # assistant 带 reasoning_content，而 history 里没有 → HTTP 400
                            # （bobo 施工时反复触发）。修复：改为 COST-6 动态块模式——
                            # 追加到最后一个 user 消息 content（用户消息 content 扩展不
                            # 破坏结构，模型仍可见建议）。
                            _suggest_text = (
                                "💡 检测到测试全绿强完成信号（run_tests）。"
                                f"台账仍有 {_pending_cnt} 项 pending：若对应工作已由测试"
                                "验证完成，请用 task_ledger update 标 done（带 evidence："
                                "测试数字/文件路径）；否则忽略本条建议（模型可推翻）。"
                            )
                            _appended = False
                            for _m in reversed(self.history):
                                if _m.get("role") == "user":
                                    _m["content"] = (
                                        (_m.get("content") or "") + "\n\n" + _suggest_text
                                    )
                                    _appended = True
                                    break
                            if not _appended:
                                # 理论不可达（每轮必有 user 输入）；兜底用独立 system 消息
                                self.history.append({
                                    "role": "system",
                                    "content": _suggest_text,
                                })
                            event_bus.write("ledger.auto_suggest", {
                                "session_id": getattr(self, "sid", ""),
                                "pending_count": _pending_cnt,
                            })
                            logger.debug("LEDGER auto-suggest: %d pending after all-green tests",
                                         _pending_cnt)
                            break
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
                                    self.tracker.log_change(f"{old} → {new}", path=fpath)
                                else:
                                    self.tracker.log_change(f"{a.get('action','write')}", path=fpath)
                                self._session_written_files.add(fpath)
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
            self._round_had_write_tool = False  # 票 R2b：每工具轮重置，按本轮工具名重算
            if self._pending_tool_calls:
                round_names = [tc.get("function", {}).get("name", "")
                              for tc in self._pending_tool_calls
                              if tc.get("function", {}).get("name")]
                # 票 R2b：本回合是否含写类工具（问答回合无台账段判定；写类施工回合答复质量闸豁免）
                _WRITE_TOOL_NAMES = {"edit_file", "file_operation", "file_writer", "delete_file"}
                self._round_had_write_tool = any(n in _WRITE_TOOL_NAMES for n in round_names)
                # 票 R3-b：本回合 tool.exec 累计次数（读/查施工也算，≥阈值豁免 R2b 质量闸；
                # 累计而非每轮重置，保证多轮施工后收尾回复仍能豁免）
                self._round_tool_exec_count += len(round_names)
                self.tracker.record_tool_pattern(round_names, self.current_user_input or "")
            self._notify("thinking", {"phase": "continuing", "message": "工具执行完成"})
            self._pending_content = None
            self._pending_tool_calls = None
            self.current_depth += 1
            self.current_tool_round += 1
            # ── 票 R2a（v2 软限制版）：票Z 缝1 无账强制提醒已拆除 ──
            # owner 终裁：软限制不做硬限制，运行时不再因"没建账"注入任何提醒；
            # 建账与否由 LLM 依据系统提示词软引导自行判断。
            self._emit_state_change(self.STATE_THINKING, "next tool round")
        elif self.state == self.STATE_RESPONDING:
            if self._pending_content:
                # ── 票K/Z 收工闸在前，内容推迟落 history（闸可能回注/修改） ──
                # 自动草稿记忆 + 笔记钩子已前移到 THINKING 闸前（票 G2-E4a 回归修复：
                # 提取先于闸执行，闸回注不消耗提取的 LLM 响应预算；事件链
                # takeaway.extracted → notes.written 与旧语义对齐）。
                # 自动 skill 发现：检查候选模式并主动提议
                if self.proactive.mode != "off":
                    logger.debug("RESPONDING maybe_propose_skill start")
                    self.tracker.maybe_propose_skill()
                    logger.debug("RESPONDING maybe_propose_skill done")
                # ── 票 G2-1：四个收工闸已前移到 THINKING 分支（先账后复）──
                # 账不平在进 RESPONDING 前已被回注；走到这里 = 闸已全过（纯放行路径）。
                self._ledger_reinject_count = 0  # 干净收工时重置计数
                self._ledger_reminded = False  # 票Z：同步重置
                self._reply_quality_reinject_count = 0  # 票 R2b：答复质量闸计数重置
                # 注意：_round_had_write_tool 不在 RESPONDING 重置——它由 EXECUTING 每工具轮
                # 重置重算，供本回合收尾轮判定"写类施工 vs 问答回合"（问答回合无工具轮 → 保留初始 False）。
                # ── 票 L1：收工自动对账（堵汇报失实）──
                # 有工具轮 → 引擎只读 git status/diff --stat 注入工作区实况。
                # 票 LEDGER-1B：对账段改内部上下文 —— 只并入 history（供模型写汇报时
                # 对账），不再拼进用户可见终稿；git 原文不上屏，可见回复只留模型
                # 自己组织的自然语言对账说明。对账机制/汇报质量标准不动。
                # 工作区干净 → _workspace_recon 返回 ""，零注入零开销。
                _recon = ""
                if self.current_tool_round > 0:
                    _recon = self._workspace_recon()
                # ── 所有闸通过，内容落 history ──
                _hist_content = self._pending_content
                if _recon:
                    _hist_content = (_hist_content or "") + _recon
                self._append_to_history("assistant", _hist_content,
                                        thinking=self._last_reasoning or None)
                self._last_reasoning = ""  # 落历史即清（防纯文本 assistant 复用残留 reasoning）
                # 引用追踪：LLM 回复中若引用了注入的记忆，自动加分
                if getattr(self.proactive, '_last_memory_ids', None):
                    self.proactive.track_citation(self._pending_content, self.proactive._last_memory_ids)
                    self.proactive._last_memory_ids = []
                # ── 票 K v2 §4 降级方案：终稿尾部附台账摘要行（面板替代） ──
                # 票 R2b：仅写类施工回合注入；纯问答回合（无写类工具）不交账——没账可交时不交账。
                if self.task_ledger and self._round_had_write_tool:
                    done_cnt = sum(1 for e in self.task_ledger if e.get("status") == "done")
                    total = len(self.task_ledger)
                    self._pending_content = (self._pending_content or "") + f"\n\n📋 台账: {done_cnt}/{total} done"
                # ── 票 AUTO-D D-2：收工交接清单（auto 拒绝记录，从 events 现查） ──
                # 仅 auto 模式有 auto.decide deny 事件；清单空则零影响（正常模式天然空）。
                _handoff = self._build_handoff_list()
                if _handoff:
                    self._pending_content = (self._pending_content or "") + _handoff
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
        self._exit_reason = "completed"
        self._all_confirmed = False
        self.verifier.attempted = False
        # 票 R3-b/c：每回合重置本轮工具执行计数（防上一回合残留值污染本轮判定）
        self._round_tool_exec_count = 0

        if self.history and not self._compressing:
            from core.context import _estimate_tokens, _get_context_budget
            if _estimate_tokens(self.history) > _get_context_budget(self):
                self._compress_history()
                self._compressed_this_turn = True

        while self.state not in (self.STATE_DONE, self.STATE_ERROR):
            self._step_count += 1
            if self._step_count > self.MAX_STEPS:
                # ── 票 W：步数熔断 — 保险丝不许伪装成正常收工 ──
                self._exit_reason = "max_steps"
                # 合成收尾消息（不调 LLM，直接模板化）
                pending_items = [e for e in self.task_ledger if e.get("status") != "done"]
                if pending_items:
                    pending_titles = "、".join(f'「{e["title"][:30]}」' for e in pending_items)
                    ledger_line = f"台账 {len(pending_items)} 项未完成：{pending_titles}"
                else:
                    ledger_line = ""
                fuse_msg = (
                    '⚠️ 步数保险丝触发（已用 {self._step_count}/{self.MAX_STEPS} 步），回合强制收尾。\n'
                    '{ledger_line}\n'
                    '发送「继续」即可接着干，进度在台账里。'
                ).format(self=self, ledger_line=ledger_line)
                self._notify("complete", {"content": fuse_msg})
                event_bus.write("engine.step_fuse", {
                    "session_id": getattr(self, "sid", ""),
                    "step_count": self._step_count,
                    "pending_items": len(pending_items) if pending_items else 0,
                    "tool_round": self.current_tool_round,
                })
                self._emit_state_change(self.STATE_DONE, "max_steps fuse")
                break
            if self._step_count >= int(self.MAX_STEPS * 0.8):
                if self._step_count % 10 == 0:
                    self._notify("thinking", {"phase": "continuing",
                        "message": f"已用 {self._step_count}/{self.MAX_STEPS} 步"})
            elif self._step_count >= 100 and self._step_count % 25 == 0:
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
