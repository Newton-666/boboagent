# 写审批 / high_risk 覆盖（GitHub #4）

> 圈 1.5 / P0。补 `write_approval` 与 `is_high_risk_tool` 对执行通道的覆盖缺口。
> 审计交叉：`reports/boboagent_main_readonly_audit_2026-09-21.md` §4.3 #2/#4（仓外只读审计）。

## 本票不改确认闸 120s 策略（P1）

`core/engine_adapter._wait_for_confirmation` 默认 **timeout=120**，超时返回 **False = deny**。

- Accept → allow，工具继续执行
- Reject **或 120s 无人应答** → deny，工具返回拒绝结果，模型换方法
- **禁止**把超时改成 allow，也禁止用缩短/取消等待换一条静默放行路径
- 超时策略本身的调整（例如改秒数、改默认）属后续 **P1**，不在本票

补齐覆盖后的硬约束：**不得引入新的静默放行。**

## 两道闸

| 闸 | 位置 | 何时生效 | 覆盖 |
|---|---|---|---|
| `is_high_risk_tool` → `Engine._confirm` | `core/command_safety.py` → `core/tool_runner.py` | 始终（默认确认路径） | 见下表 |
| `write_approval` → `_guarded_execute` | `core/engine_adapter.py` | 会话 `session.set_write_approval on:true` | 原 WRITE_TOOLS + 下表高危调用 |

写审批闸在**执行前**再问一次。因此 `_all_confirmed` 粘性放行、AUTO 对 local-reversible 终端的快照放行，都不能让高危通道在写审批开启时静默落地。

确认闸超时仍走同一 `_wait_for_confirmation(120)`：超时 = deny。

## 风险匹配表

| 工具 | `is_high_risk_tool` | 写审批开启时 |
|---|---|---|
| `execute_terminal` safe（如 `ls`） | 否（静默） | 不抬闸 |
| `execute_terminal` gray / dangerous | 是 → `_confirm` | 必须确认 |
| `code_execution` | 始终是 | 必须确认 |
| `computer_use` `capture` | 否（只读看屏） | 不抬闸 |
| `computer_use` click / type / key / open_app / scroll / 未知 action | 是 → `_confirm` | 必须确认 |
| `edit_file` / `file_operation` | 否（沿用 VSC-2B：只走写审批闸） | 必须确认（原行为） |

AUTO 模式不弹窗（铁律，避免 120s 卡死）：`code_execution` 与高危 `computer_use` 即时 **deny** + 留痕，不静默执行。

## 相关代码

- `core/command_safety.py` — `is_high_risk_tool`
- `core/engine_adapter.py` — `needs_write_approval` / `_guarded_execute` / `_wait_for_confirmation`
- `core/engine.py` — `_auto_decide` 对高危执行通道即时 deny
- `tests/test_issue4_write_approval_high_risk.py` + `tests/test_command_safety.py::TestHighRiskTool`
