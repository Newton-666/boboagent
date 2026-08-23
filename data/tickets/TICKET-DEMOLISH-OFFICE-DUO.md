# TICKET-DEMOLISH-OFFICE-DUO

> 类型：架构偿还（模式拆除）
> Owner 裁决：2026-08-23 —— office 模式与 duo 模式使用效率不符预期，整体移除
> 战役位置：`_step()` 拆解战役的**前置圈**（先拆模式，后拆函数）
> 依据文档：`docs/DESIGN_STEP_PIPELINE.md` §0 前置圈
> 红线：**AUTO 模式的全部共享路径零影响**（逐项清单见 §4）
> 拆除范围：仅 office/duo 两个模式。AUTO 模式不在本次范围。

---

## 1. 拆除对象总览（按层）

| 层 | 删除（A） | 简化（B：分支删、主体留） | 保留（C：仅改注释/文字） |
|---|---|---|---|
| 引擎 core/ | engine.py 6 块 office 专属代码 | engine.py 2 处（权限链分支、O8 闸激活条件） | — |
| 网关 gateway/ | server.py `_office_state`/`get_office_on` | prompts.py（/office、/duo 商讨分支+帮助文本）、sessions.py（响应字段）、eval_runner.py（office_on 场景） | metrics.py 注释、tool_runner.py 注释 |
| 工具 tools/ | office_manager.py（518 行整文件+注销注册）、team_relay_v2 的 RELAY_SESSION 默认名可留 | — | team_relay_v2 历史注释 |
| 编排 core/ | duo_orchestrator.py（167 行整文件） | — | tool_runner.py:133 注释 |
| 前端 ui-tui/ | officeOn 状态链（uiStore/interfaces/事件处理/恢复/状态栏 OFFICE 徽章） | branding.tsx（BOBO_ROLE → 常量 'Bobo Agent'） | idleExit.ts 历史事故注释 |
| 数据 data/ | office_audit.jsonl、office_manager_registry.json、protected_paths.json、office_roles.json | — | — |
| 技能标准 | duo/standard.md、tmux-office/standard.md | — | hermes-pi-duo（**见 §5 裁决点 2**） |
| 测试 tests/ | 6 个整文件删除 | 6 个文件适配 | ~20 个文件一行级触碰 |
| 文档 docs/ | duo 设计/task 文档 4 份（或归档） | 活文档 7 份更新（SELF/ROADMAP/ARCHITECTURE-MAP/HARCHITECTURE/SELF_HOSTING/GUI-DESIGN/EVAL_*） | ~30 份历史记录保持原样（是历史，不是现状） |

## 2. engine.py 逐块清单（行号为 2026-08-23 快照）

**A 类（整体删除，engine 预计减 ~300 行）：**
| 行 | 内容 |
|---|---|
| 105–115 | `office_role`/`office_ticket` 初始化（BOBO_ROLE/BOBO_TICKET 环境变量） |
| 244–248 | guardsnap 触发（`_snapshot_protected_paths` 调用点） |
| 369–436 | `_OFFICE_WRITE_TOOLS`、`_guardsnap_path`、`_snapshot_protected_paths` |
| 438–466 | `_verify_snapshot`（O3-1 收工比对，唯一调用方是 office 收尾块） |
| 468–600 | `_office_decide` + `_extract_shell_write_paths` + `_extract_file_write_paths` + `_office_path_write_rule` + `_office_ticket_allows` |
| 733–740 | `_write_office_audit` |
| 1972–1986 | `_step()` 收尾的 office 快照告警块（S2 闸） |

**B 类（分支删、主体留）：**
| 行 | 内容 | 保留的共享主体 |
|---|---|---|
| 225–228 | 工具权限链的 office enforcement 分支 | 下方 `_auto_decide` 决策树 + confirm 回调链 |
| 2079–2087 | O8 闸的 `get_office_on` 回退激活 | 闸体（补账+字段闸）改为仅 auto 激活；`_gate_label` 固定 "AUTO MODE" |

**拆除红利**：同时消除两处 **core→gateway 反向 import**（engine.py:2081、injector.py:627 的 `from bobo_tui_gateway.server import get_office_on`）——这两处是分层泄漏，删除即修复。

## 3. 其他层要点

- **prompts.py**：`/office` 分支内 `import tools.office_manager.teardown`（371 行）是 office_manager 唯一的注册外引用——随分支一起删。`/duo 商讨` 分支（664–690）删。帮助文本与命令映射表同步清理。
- **protected_paths.json**：消费者仅 office 快照链 + 3 个 office 测试，确认随模式删除。**注意 command_safety.py 的 `is_git_readonly_subcommand`（1027–1031）吃的是 AUTO 的只读白名单，必须保留**——`load_protected_paths`/`is_protected` 才是删除对象。
- **前端**：office 的全部 UI 面 = 底部状态栏一个 OFFICE 徽章 + 恢复/切换时的状态回填。`appChromeStatusRule.test.tsx` 适配。
- **eval_runner.py:278**：直捅 `server._office_state` 私有字典——office_on 场景删除后这处耦合自然消失。
- **测试分拣**：删 `test_duo_orchestrator.py`、`test_ticket_o1/o2/o3/o4/o8`（6 文件）；适配 `test_bugfixes.py`（duo _briefing 段）、`test_ticket_g3_submit_wait_window.py`（duo 慢退出段）、`test_ticket_core_r3.py`（get_office_on monkeypatch 改纯 auto 路径）、`test_ticket_r2_p3.py`、`test_injector.py`（office 预算段）、`test_eval_runner.py`（office_on drive）。

## 4. 必须存活的 AUTO 共享路径（验收对照清单）

1. `_auto_decide` + `_snapshot_for_rollback` + auto 审计事件（`auto.decide`）——与 office 快照是**两套独立函数**，不可误删；
2. `command_safety.is_git_readonly_subcommand` / `_AUTO_READONLY_GIT_SUBCOMMANDS`；
3. O8 闸体（补账检测 + 字段闸）——激活条件收窄为仅 auto，逻辑不动；
4. 承诺检测闸、沉淀派发、交接清单——相邻不动；
5. **AUTO 模式回归测试全绿 = 本票最重要验收项**。

## 5. Owner 裁决记录（2026-08-23 已裁决）

1. **宪法 Principle 4（快照抓漏）：保留**。auto 的 `_snapshot_for_rollback` 为独立实现，不受拆除影响；宪法修订史记一条"适用面收窄至 auto"。
2. **hermes-pi-duo 技能：暂保留**（owner：删留皆可、不急，先搁置不动）。
3. **duo 的 4 份设计文档：保留**。owner 裁决理由：拆除时反向参考——看它当初怎么一步步设计出来，就怎么一步步反推拆除（设计文档 = 拆除路线图的逆向版）。移入 archive/ 的选项作废。

## 6. 执行顺序（建议分 3 批，各配回滚 tag）

| 批 | 内容 | 验收 |
|---|---|---|
| D0 | **auto 行为基线**：拆前用 mock 剧本录制 auto 模式与普通模式的完整会话（事件序列 + history + 终稿），存 `data/eval/step_baseline/pre_demolish/` | 基线落盘。**Owner 定调（2026-08-23）：auto 模式是系统核心组分，本票全部施工以 auto 安全为前提——宁可 office 残余，不可 auto 缺损** |
| D1 | 后端核心：engine.py A/B 类 + injector.py O4 块 + command_safety 删函数 + duo_orchestrator.py + server.py | pytest 全量绿；AUTO 回归绿；**auto 行为基线 diff=0**；core→gateway 反向 import 消失 |
| D2 | 网关命令面 + 工具注销：prompts.py 分支、office_manager.py、sessions.py、eval_runner、前端状态链、branding | /office /duo 不再出现在命令表；前端构建过；officeOn 状态链无残留引用；**auto 行为基线 diff=0** |
| D3 | 清扫：data/ 4 个工件、技能标准 2 份、文档 7+4 份、宪法修订史记条、测试分拣收尾 | grep -ri "office\|duo" 仅剩历史文档与注释（C 类清单内）；地图数字更新 |

## 7. 验收总则

- **auto 行为基线 diff=0 是贯穿 D1/D2 的硬门槛**（测试防已知路径，基线防未断言的隐含行为被顺带删走）；
- `grep -rli "office" core/ tools/ bobo_tui_gateway/ ui-tui/src apps/desktop/src` 结果 = §1 的 C 类清单，无超出；
- 拆除后 `engine.py` 行数与 `ARCHITECTURE-MAP.md` 载重表同步更新（预计 2,545 → ~2,200）。

---

## 8. 待办记录（2026-08-23，D1 合入后）

- **前端残留（owner 已知悉，暂不改，记录在案）**：TUI 状态栏 OFFICE 徽章、`officeOn` 状态链
  （uiStore/interfaces/createGatewayEventHandler/appLayout/appChrome 等）、branding 的
  BOBO_ROLE 显示仍在——表现层非本次调整范围（owner：整体调整以后端为准，前端显示问题
  不算本质性问题，何时改另行决定）。对应票内 D2 批，状态：**暂缓**。
- **D2 批内容不变**：前端状态链 + branding；**D3 批**：数据工件 4 个（office_audit.jsonl 等）、
  技能标准 2 份、文档 7+4 份、宪法修订史记条。
