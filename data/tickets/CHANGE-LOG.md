# 改动日志（CHANGE-LOG）

> **强制纪律（owner 2026-08-23 定）：每批改动必须记录**——改了啥 / 范围 / 影响 / 之前问题 / 解决后结果。
> 目的：owner 未实战验证期间，任何后期问题可从此表追溯出处的节点。
> 规则：先写本条 → 再提交；每批一条；提交号必填。
> **排布节奏（owner 2026-08-23 定）：微观/宏观交替**——每批记录后必须紧跟"宏观快照"（当前路线图位置、到 engine 还差几步）。
> 读法：HARCHITECTURE 是纯宏观（原则）；本 log 是微观(批次)→宏观(快照)交替——两个层次都在这里，不许只写细节。

---

## 批次记录

### B1 · main 修绿 A 批 —— 提交 `24c855c5`（2026-08-23）

- **之前问题**：main 全量 61 失败（当时误判"全为存量"，后修正为其中 6 个是 D1 合法改动触发治理守卫）。
- **改动内容**：
  1. FakeCtx/_Ctx 补 `computer_use_mode` 属性（9 文件：goal_gate、gui_f6/f7/f8/f9/f11/f24、desk 系）——修"老测试假上下文没跟上 sessions.py 新字段"。
  2. 治理守卫登记 `TICKET-DEMOLISH-OFFICE-DUO` 授权（v4/v4b/tel_8/p1 零干涉测试；含整文件删除白名单即授权、data/tickets 与 scripts/step_baseline 非代码跳过）。
  3. v2b3_5 命令目录断言移除 `/duo`（功能已删）。
  4. stash 事故遗留修复：duo_orchestrator.py 删除补入 git 索引。
- **范围**：tests/ 9+4 文件；无 core/gateway 运行时代码改动。
- **解决后**：~22 个测试转绿（61 → 39）；治理守卫认识新票号（守卫未被削弱）。
- **遗留影响**：v4b0_2 busy_gate、v2b3_1、desk v2a/v2b css 为 main 前端存量（dist 被 main 票改动），未修，待前端票。

### B2 · main 修绿 B 批 —— 提交 `7bacf6e2`（2026-08-23）

- **之前问题**：B 类行为断言失败 16 个，初判为 16 个独立判研。
- **根因发现**：`TICKET-COMPUTER-USE-INTENT`（COST-3）的 `parse_intent` 在 `run()` 开头对命中意图闸的输入（帮我/查/打开…）消费一次 LLM 调用 → 全部 mock 队列错位。**16 个中大部分是这一根因的批量症状**。
- **改动内容**：
  1. goal_gate：mock 队列前补意图占位响应 + call_count 3→4（16 测试全绿）。
  2. e4a：输入措辞"帮我执行一个命令"→"请执行一个命令"避开意图闸（7 测试全绿）。
  3. cost1b：c8 零干涉守卫登记 `core/duo_orchestrator.py` 删除豁免（D1 合法改动，同 B1 治理登记性质）。
  4. note_pointer：注入器预算键期望集移除 `office`（D1 拆除 office 键的测试侧同步）。
- **范围**：tests/ 4 文件；无运行时代码改动。
- **解决后**：~26 个测试转绿（累计 61 → 剩余 ~13）。
- **遗留影响**：perf_1/core_r3 疑同根因未验证；skill_audit（注入行为）、core_int2/computer_use_core（环境类）、eng1/scan/g3（待查）、watchdog（暂缓）、前端 4（归前端票）。

### B0 · D1 拆除批 —— 提交 `b79297eb` + `788f2c6c`（2026-08-23）

- **之前问题**：office/duo 模式使用效率不符预期（owner 终裁拆除）；engine 2,545 行超载。
- **改动内容**：engine 8 块 office 逻辑、injector O4 块、command_safety 受保护路径函数、duo_orchestrator/office_manager 整文件、gateway /office /duo 命令分支与 office 状态；测试 6 删 4 适配。
- **范围**：core/ 3 文件 + gateway 3 文件 + tools 1 文件 + tests 10 文件 + 文档（ARCHITECTURE-MAP、DESIGN_STEP_PIPELINE、TICKET-DEMOLISH-OFFICE-DUO）。
- **解决后**：engine 2,545→2,208；工具 83→82；行为基线 diff=0（6 场景）；auto 197 全绿。
- **遗留影响**：D2 前端痕迹、D3 数据/文档清扫未做；治理守卫未同步登记（B1 已补）。

### B3 · 文档批 —— 提交 `1a029fc5` / `fbc745e7` / `1b1edb6c`（2026-08-23）

- **改动内容**：DESIGN_STEP_PIPELINE §0 第一原则（模块纯粹性）；ENGINE-RESPONSIBILITY.md（engine 职责分析）；修绿汇总入票。
- **范围**：docs/ + data/tickets/；零运行时代码改动。
- **影响**：为流水线圈与后续圈提供设计依据；无行为影响。

---

### B4 · main 修绿 B 批追加 —— 提交 `d2527666` · 2026-08-23

- **之前问题**：perf_1（成文挂死超时测试）与 core_r3（R2b ≥3 次工具豁免测试）失败——同为意图闸错位根因（B2 发现的 COST-3 意图调用吞 mock 首响应）。
- **改动内容**：
  1. perf_1：输入措辞"帮我选一下数据库方案"→"请选择数据库方案"避开意图闸（保住 HangOnFourthCall 第 4 次挂死定位）。
  2. core_r3：mock 队列前补意图占位（"查"为场景语义不可改措辞）。
- **范围**：tests/ 2 文件；无运行时代码改动。
- **解决后**：两文件全绿（累计 61 → 剩余 ~11：skill_audit 1、core_int2 1、computer_use_core 1、eng1 5、scan 6、g3 2、前端 4、watchdog 5——watchdog 与前端按既定策略不在本地批）。

---

## 宏观快照（每批后刷新 · 2026-08-23 更新于 B11）

```
阶段 0：D1 拆除 office/duo        ✅（engine 2,545→2,208）
阶段 1：main 修绿（测试债）       ✅ 已收口
阶段 2：测试分层 + 前端票          ✅ 全部收口——本地全量首次全绿（2855 过/0 败）
阶段 3：engine 流水线圈            ⬜ ← 目标（地基已清，手术可开）
```

**到 engine 还差几步**：
1. 全量复跑确认本地全绿（预期 4→0）
2. 阶段 2 合 main（owner 验收）——已合过一次（48e5ebd9），本次前端批单独合
3. socket-gap 评估票 + 构建管线迁移票（长期，可并行）

→ 全绿确认后即 engine 开工。本次记录批次：B0–B11。
下次批次合入时：先写微观条目，再刷新本快照（强制，无需提醒）。

---

### B5 · main 修绿 B 批追加二 —— 提交 `3601dc9e` · 2026-08-23

- **之前问题**：待查 7 文件——eng1(5)+scan(6) 为接口迁移类（run_engine 签名新增 computer_use_mode，测试调用没跟上）；g3(2) 为 D1 的 /duo 帮助文本残留；computer_use_core 为测试桩过时（lambda 签名 + element_id 键）；core_int2 为 **llm_caller 真 bug**。
- **改动内容**：
  1. eng1/scan_l3b/scan_l3c/scan_l3_connect/g3：run_engine 调用补 `computer_use_mode={}`、SimpleNamespace/_FakeCtx 补属性、/duo 断言更新为现存命令。
  2. computer_use_core：`_capture_png` lambda 补 pid 参数 + `_collect_elements` 桩补 `element_id` 键。
  3. **core/llm_caller.py 真 bug 修复（判研产出）**：中断路径 `_sock_holder.get("sock")` → `getattr(_sock_holder, "sock", None)`——threading.local 无 .get，原代码中断时崩 AttributeError 而非抛 LLMInterrupted。**本批唯一运行时代码改动，范围 1 行**。
  4. **遗留裁决点**：skill_audit 断言 research 应注入，但 `data/skills/enabled.json` 里 `research: false`（运行时治理配置）——配置与测试冲突，**待 owner 裁决**（research 是否故意禁用）。
- **范围**：tests/ 8 文件 + core/llm_caller.py 1 行；其余为测试侧改动。
- **解决后**：eng1/scan 系/g3/computer_use_core/core_int2 全绿；真 bug 修复（中断路径不再崩溃）。
- **遗留影响**：skill_audit 1 个待裁决；watchdog 5（D 类暂缓）；前端 4（归前端票）；另记 socket 关闭语义 gap（主线程读不到 worker 线程 sock，中断时不关 socket 只抛异常——候选真 bug，另票评估）。

### B6 · main 修绿收口 —— 提交 `96771de2` · 2026-08-23

- **之前问题**：skill_audit 断言 research 应注入，但 `data/skills/enabled.json` 为 research=false——配置与测试冲突，待 owner 裁决。
- **owner 裁决**（2026-08-23）：**所有禁用技能均为 owner 手动操作**——research 禁用是故意的，测试断言过时。
- **改动内容**：
  1. skill_audit 行为测试隔离运行时 enabled 配置（夹具 all_skills_enabled 置全开）——匹配/excludes 逻辑测试不再依赖治理状态，且修掉三个排除测试在禁用下的"空转通过"。
  2. 新增 `test_behavior_research_disabled_by_governance`——锁定"research 禁用时不注入"的治理行为（防误启）。
- **范围**：tests/ 1 文件；无运行时代码改动。
- **解决后**：阶段 1 全部 owner 可决项清零——61 个原始失败全部修复或明确归类（剩 watchdog 5 = D 类进阶段 2；前端 4 = 前端票）。
- **遗留影响**：无新增。

### B7 · 工作区清零 + 宪法入库 —— 提交 `9baa73d7` · 2026-08-23

- **之前问题**：工作区有未提交残留——① duo_orchestrator.py 删除被 stash 操作反复弹回索引（D1 已提交过，属索引反复回退）；② docs/HARCHITECTURE.md 宪法修订（Principle 5 协作协议 + v1.1）长期滞留工作区。
- **owner 定调**（2026-08-23）：**GitHub 必须对齐，不能有未提交的东西；一切改动（哪怕一行代码、一个测试）必须入 CHANGE-LOG**——追溯源头 + backup 余地。
- **改动内容**：① duo_orchestrator.py 删除重新 stage 并入库；② HARCHITECTURE.md（宪法 Principle 5 + v1.1 修订）正式入库——内容 owner 已于当日批准。
- **范围**：git 索引修复 + 1 文档文件；无运行时代码改动。
- **解决后**：工作区代码侧清零（仅剩会话前既存的 dist/index.html 脏构建产物与 untracked 杂项，非本次产生）。
- **遗留影响**：dist/index.html 为会话前既有脏文件，未动；98 个 untracked 为会话前既有杂项。

### B8 · 阶段 2 分层施工 —— 提交 `5b46546a` · 2026-08-23（分支 feat/test-layering）

- **之前问题**：测试"一锅粥"——快件/慢件/socket 时序件全混一层，watchdog 本地时好时坏/卡死，污染日常信号。
- **owner 定调**：测试分层 = 把"模块纯粹性"原则用到测试体系自身（每层有目的、有跑道）；**先走分支，测好再合并 main**。
- **改动内容**：
  1. pyproject.toml：新增 `live` 标记声明 + addopts 加 `-m "not live"`（本地默认跳过 live 层）。
  2. .github/workflows/test.yml：CI 显式 `-m "live or not live"` 覆盖 addopts（**CI 全量含 live**——覆盖保留，只是换跑道）。
  3. tests/test_headers_watchdog_live.py：模块级 `pytestmark = pytest.mark.live`（整个文件皆真 socket）；tests/test_headers_watchdog.py 两个 stall 测试打 `@pytest.mark.live`（ok_server/env 单测保留快件层）。
  4. 新开两票：TICKET-FRONTEND-GREEN（前端存量 4）、TICKET-LLM-CALLER-SOCKET-GAP（候选真 bug）。
- **范围**：pyproject 配置 + CI workflow + 2 测试文件标记 + 2 新票；零运行时代码改动。
- **解决后**：本地日常不再被 socket 件拖卡（收集验证 9/16，7 个 live 跳过）；live 覆盖保留在 CI。
- **遗留影响**：分层后的精确全量数字待下轮全量复跑（预期本地 15→10：watchdog 5 跳过后剩 cost1a_sandbox 3 + tool_park_1 1 + 前端 4 + gui_f4 1 + tel_8 1（待复核））。

### B9 · 校准批（C 类）—— 提交 `c5f6beba` · 2026-08-23（分支 feat/test-layering）

- **之前问题**：cost1a_sandbox 3 + tool_park_1 1 失败——校准值停留在 D1 前工具集（A=32/D=79/schema 税 3,997），实际已变（D1 删 office_manager + main 新增 computer_use/vision schema）。
- **改动内容**：
  1. cost1a_sandbox：validate 期望 A 32→31、D 79→82；config_a 断言 32→31；config_d 断言 79→82（测试名原本写 82，断言却是旧的 79）。
  2. tool_park_1：schema 税目标 3,997→4,287（实际 4,286.75，超旧目标 7.2%——main 新工具 schema 推高，非 D1 所致）；"节省"测试（saved=4,327）本就在范围内，未动。
- **范围**：tests/ 2 文件；零运行时代码改动。
- **解决后**：校准类全绿（40 过）。分层后全量预期 10 → 4（剩前端 5 + tel_8 1）。
- **遗留影响**：schema 税 4,287 是现实值——若后续继续加工具，注意重新校准；本批不改任何工具集本身。

---

## 全量回归记录（每次全跑的精确结果，全部入档）

| 日期 | 分支/环境 | 结果 | 备注 |
|---|---|---|---|
| 2026-08-23 | feat/demolish-office-duo-d1（D1 后） | 2813 过 / 61 败 / 2 跳过 / 3:18 | 61 败全部存量（抽查+分拣证实；其中 6 个为 D1 合法改动触发治理守卫） |
| 2026-08-23 | 同（A 批后） | 2835 过 / 39 败 / 2:52 | A 批净转绿 22 |
| 2026-08-23 | 同（B 批后，阶段 1 收口） | 2847 过 / 15 败 / 2:53 | B 批净转绿 24；15 = watchdog 5 + 校准 4 + 前端 5 + tel_8 1 |
| 2026-08-23 | feat/test-layering（分层后） | 2845 过 / 10 败 / 7 deselected(live) / 1:50 | 分层生效：watchdog 5 进 CI，本地 110s；10 = 校准 4 + 前端 5 + tel_8 1 |
| 2026-08-23 | 同（校准批 B9 后） | 待下一轮全量确认 | 预期 10→4（剩前端 5 + tel_8 1） |
| 2026-08-23 | main（前端批 B11 后） | **2855 过 / 0 败 / 2 跳过 / 7 deselected(live) / 1:53** | 🎉 **首次全绿**（61→0）；live 7 按设计进 CI；本地 113s |
| 2026-08-23 | main（流水线圈 13/14 房合后） | **2855 过 / 0 败 / 2 跳过 / 7 deselected(live) / 1:50** | 与搬房前完全一致——13 房搬移零行为差异，流水线圈收口 |

> 注：多轮出现 "RC=TIMEOUT" 假头——孤儿 pytest 进程占管道导致 wrapper 等待超时，摘要实际完整（详见各批记录）。已用 pkill 清理。

### B10 · 宪法 v1.2（Principle 6 蓝图先行）+ 前端票治理升级 —— 提交 `b27bb587` · 2026-08-23

- **之前问题**：前端 10 天漂移事故暴露——Hermes 直接改成品（dist）未同步图纸（src）与守卫，成品成为无图纸黑盒。
- **owner 终裁**：先图后物——任何改动先看蓝图；图纸不对先改图纸，禁止直接缝补成品（微观先行 = 缝缝补补；蓝图先行 = 宏观框架）。
- **改动内容**：
  1. HARCHITECTURE.md v1.1→v1.2：新增 Principle 6（Blueprint before product）——改动必须始于蓝图；禁止改构建产物而不先更新源；成品漂移的修复路径 = 反推蓝图 → 重建 → 对齐守卫；立法史记录前端 10 天事故。
  2. TICKET-FRONTEND-GREEN 升级：修复路径改为蓝图先行（反推 dist→src → vite 重建 → 守卫对齐）。
- **范围**：docs/HARCHITECTURE.md + data/tickets/；零运行时代码改动。
- **解决后**：宪法覆盖"宏观/微观"方法论（Principle 5 owner 保持地图层 + Principle 6 先图后物）；前端票有了正确的执行路径。
- **遗留影响**：前端票实际施工（反推 src）尚待执行。

### B11 · 前端票修绿（守卫对齐，成品不动）—— 提交 `54951d88` · 2026-08-23

- **之前问题**：前端 5 守卫失败——成品（dist）被前端票改动，守卫记忆过时（busy_gate/v2b3_1/gui_f4/css×2）。
- **调查发现**：dist 是手写维护的生产构件（Electron 直接加载），`src/` 是废弃存档（git 记录证实）——"蓝图"实为 dist 内 43 票注释 + 守卫。
- **owner 裁决**：成品不动（10 天工作是事实源）；蓝图 = MD 设计文档（docs/FRONTEND-BLUEPRINT.md）；守卫对齐。
- **改动内容**：
  1. **docs/FRONTEND-BLUEPRINT.md 新建**（蓝图 v1）：产品现状/接口契约（29 RPC + 20 事件 + DOM + localStorage）/维护纪律（动成品三步）/版本记录。
  2. **docs/GUIDANCE.md 挂入 FRONTEND CONTRACT**（契约层）：任何 agent 做前端改动必读蓝图——未来任何 agent 按仓库规范工作即发现。
  3. 守卫对齐（成品不动）：busy_gate 期望串更新（&& !img 选图参数）；v2b3_1 sendPrompt(text, img)；gui_f4 选择器正则（#auto-toggle, #computer-use-toggle）；css ×2 归一化豁免（computer-use 选择器扩展 + vision 图片规则两笔授权变更登记比对）。
  4. dist 现状提交为新冻结基线 tag rollback/pre-frontend-align（成品不动 = 捕获事实非编辑）。
- **范围**：docs 2 文件 + tests 4 文件 + dist 提交 + 1 tag；成品本身零编辑。
- **解决后**：前端 5 守卫全绿（前端守卫组 87 过）；本地全量预期 10→4（剩 tel_8 复核已过 + 校准已清）。
- **遗留影响**：构建管线迁移（另期长期票）；socket-gap 评估票。

### B12 · 流水线圈执行策略定稿 —— 提交（待填）· 2026-08-23

- **owner 定调（白话讨论）**：engine 是"走廊（核心 loop）+ 房间（纪律）"；解耦第一刀 = 走廊与房间先分家。
- **策略（写入 DESIGN_STEP_PIPELINE §0a）**：先看完全部房间 → 砌墙（最小骨架+接口，契约对着全部房间设计）→ 搬低耦合房间验证墙 → 搬高耦合房间。
- **反模式**：不砌墙先拆房 = 形式的流水线（禁止）。
- **验收两把尺子**：行为基线 diff=0 + LLM 调用次数不升（重构前先测每回合调用基线）。
- **范围**：docs/DESIGN_STEP_PIPELINE.md；零代码。
- **遗留影响**：数房间清单 + 砌墙设计为下一批实际施工内容。

### B13 · 数房间清单 —— 提交（待填）· 2026-08-23

- **内容**：_step 现状 16 个评估对象按耦合度分档——入口控制流 2（高）、THINKING 收尾 7、EXECUTING 5、RESPONDING 2；搬移顺序：第一批低耦合 6 间（承诺/质量/补账/字段/台账/tracker）→ 第二批中 4 间 → 第三批高 4 间；P2 终稿组装另期。
- **落盘**：DESIGN_STEP_PIPELINE §0a.1。
- **遗留影响**：砌墙（骨架+接口）为下一步施工。

### B14 · 流水线圈首批：砌墙 + 承诺房间试住 —— 提交（待填）· 2026-08-23（分支 feat/step-pipeline）

- **内容**：
  1. 墙（骨架）：core/steps/base.py——StepContext（只读简报 + 白名单办事窗口：append_warning / request_reinjection / 共享计数器经窗口读写）+ StepResult（PASS/REINJECT）+ StepStage 基类；
  2. 第一间房：core/steps/promise_gate.py——承诺检测从 _step 内联迁出（票Z 缝2 + R3-d 施工证据放行 + 熔断），行为逐字节保持；
  3. engine 收尾段改为流水线调用（递简报→听回答→按回答行动），其余闸仍内联。
- **客观验证**：行为基线 diff=0（6/6 含承诺回注场景）；相关测试 117 过（goal_gate/engine_core/engine_e2e/auto）。
- **范围**：core/steps/ 新包 3 文件 + engine.py（import/挂墙/替换承诺块）；engine 行数净变化小。
- **遗留影响**：其余 13 间房待逐间搬入（顺序：第二批中 4 间 → 第三批高 4 间 → 另期 P2）；墙的接口按需演化（先保守后放宽）。

### B15 · 流水线圈房间②：答复质量闸迁出 —— 提交（待填）· 2026-08-23（feat/step-pipeline）

- **内容**：core/steps/quality_gate.py（票 R2b + R3-b）从 _step 内联迁出；base 扩展办事窗口（last_reasoning 只读 + reply_quality 计数窗口）；承诺房名改回 "promise" 保持状态原因逐字节一致。
- **客观验证**：行为基线 diff=0（6/6）；相关 50 测试过（goal_gate/core_r3/engine_core）。
- **遗留影响**：收尾段墙内现有 2 房（承诺+质量），顺序保持原内联版。

### B16 · 流水线圈房间③：补账检测闸迁出 —— 提交（待填）· 2026-08-23（feat/step-pipeline）
- core/steps/backfill_gate.py（票 O8-2）从内联迁出；auto 模式专用（office 已拆，gate_label 固定 AUTO MODE）；嫌疑 flag 由 EXECUTING 段经 ctx 只读。

### B17 · 流水线圈房间④：台账字段闸迁出 —— 提交（待填）· 2026-08-23（feat/step-pipeline）
- core/steps/field_gate.py（票 C + L1 pass-with-note）迁出；自持 deny 计数经 ctx 窗口；放行附注随终稿带出（L1 降本语义保留）。

### B18 · 流水线圈房间⑤：台账未销账闸迁出 —— 提交（待填）· 2026-08-23（feat/step-pipeline）
- core/steps/ledger_gate.py（票 K v2 + R3-d + 熔断 + R2a 无账软放行）迁出；无条件运行；共享 _ledger_reinject_count 经窗口保持与承诺房共用 2 次熔断预算（原语义不变）。

- 客观验证（B16-B18 合并）：行为基线 diff=0（6/6）；台账/auto 系 220 测试过（goal_gate/core_r3/r2a/r2_p2/g2/ledger_1/auto_mode×2）。
- 收尾段墙内现 5 房（承诺/质量/补账/字段/台账），顺序与原内联版一致；内联票C/票K 块已删。

### B19 · 流水线圈房间⑥：沉淀派发迁出 —— 提交（待填）· 2026-08-23（feat/step-pipeline）
- core/steps/sediment_dispatch.py（票 PERF-1）迁出；fire-and-forget：只判"要不要沉淀"，起线程动作走走廊办事窗口 _dispatch_sedimentation（test_mode 同步 + 生产 daemon 线程 + 启动失败 notes.error，语义保留）。
- perf_1 实现细节断言更新（源码字符串随重构迁移——其余行为断言全部保留并验证）。
- 客观验证：行为基线 diff=0（6/6）；E4a/perf_1 15 测试过。
- 墙内现 6 房：沉淀/承诺/质量/补账/字段/台账。

### B20 · 流水线圈房间⑦：全绿销账建议迁出 —— 提交（待填）· 2026-08-23（feat/step-pipeline）
- core/steps/auto_suggest.py（票 L1 + COST-7/LEDGER-400）迁出为 EXECUTING 段观察房；改历史经办事窗口 append_suggestion_to_history（只扩最后 user 消息防 DeepSeek 400）；建议性可推翻、不改账（铁律保留）。
- 墙新增 EXECUTING 段走廊（_exec_post_stages，工具落历史后跑）。
- 客观验证：行为基线 diff=0（6/6）；LEDGER-400 系 4 测试过（另 ledger_1b/cost1b 4 过）。
- 墙内 7 房（收尾 6 + 执行 1）。

### B21 · 流水线圈房间⑧：工作区对账迁出 —— 提交（待填）· 2026-08-23（feat/step-pipeline）
- core/steps/workspace_recon.py（票 L1 + LEDGER-1B）迁出为 RESPONDING 段观察房；只读 git 对账经办事窗口 fetch_workspace_recon；产出经 ctx.recon_text 由走廊并入 history（不上用户终稿）。
- 墙新增 RESPONDING 段走廊（_respond_stages）。
- ledger_1b 静态断言更新（对账调用点迁至房间，语义保留）。
- 客观验证：行为基线 diff=0（6/6）；ledger_1b/goal_gate/e2e/desk_v2a 58 测试过。
- 墙内 8 房（收尾 6 + 执行 1 + 回复 1）。

### B22 · 流水线圈房间⑨：编辑冲突检测迁出 —— 提交（待填）· 2026-08-23（feat/step-pipeline）
- core/steps/edit_conflict.py 迁出为 EXECUTING 前置房（工具环前）；纯本地解析零 LLM；拦下时回注 assistant 消息（走廊执行重走动作）。
- 墙新增 EXECUTING 前置走廊（_exec_pre_stages）。
- 客观验证：行为基线 diff=0（6/6）；engine_core/e2e/bugfixes 102 测试过。
- **第二批（中耦合）全部完成：9/14 房已搬**（收尾 6 + 沉淀 + 销账 + 对账 + 冲突）。

### B23 · 流水线圈房间⑩⑪：台账基线快照 + 台账同步/补账嫌疑迁出 —— 提交（待填）· 2026-08-23（feat/step-pipeline-b3）
- core/steps/ledger_snapshot.py（票 O9）+ ledger_sync.py（票 K v2/L + O8-2）迁出；E2 入前置房（工具环前快照，_prev_ledger 存走廊侧）、E3 入新增中段走廊（工具环后同步+嫌疑评估，先于落账/销账——时序铁律）。
- 墙新增 EXECUTING 中段走廊（_exec_mid_stages）。
- 客观验证：行为基线 diff=0（6/6）；台账/auto 系 94 测试过（core_r3/goal_gate/auto_mode/r2a/ledger_1）。
- 墙内 11 房（收尾 6 + 执行前 2 + 执行中 1 + 执行后 1 + 回复 1）。

### B24 · 流水线圈房间⑫⑬：空响应重试 + 验证器迁出 —— 提交（待填）· 2026-08-23（feat/step-pipeline-b3）
- core/steps/empty_retry.py + verifier_check.py 迁出为 THINKING 入口房；墙扩展两种新回话（RETRY：空响应重试/报错；VERIFY_REINJECT：验证器命中清态回走）；控制流房间只判结果，走廊执行重试/报错/清态动作。
- 客观验证：行为基线 diff=0（6/6）；engine_core/e2e/goal_gate/interrupt 系 88 测试过。
- **13/14 房全部搬完**（P2 终稿组装为展示层债，另期 backlog）。墙形态：入口 2 + 收尾 6 + 执行前 2 + 执行中 1 + 执行后 1 + 回复 1。

### B25 · 流水线圈收口 —— 提交（待填）· 2026-08-23（已合 main：6985c7a1）

- **内容**：13/14 房全量收口验证——合并后 main 全量 **2855 过 / 0 败 / 7 deselected(live) / 110s**，与搬房前（2855/0）完全一致：行为零差异。
- **墙最终形态**：core/steps/ 包（入口 2 + 收尾 6 + 执行前 2 + 执行中 1 + 执行后 1 + 回复 1）；StepContext 简报+办事窗口、StepResult 五种回话（PASS/REINJECT/RETRY/VERIFY_REINJECT + 附一句）。
- **回溯链**：rollback/pre-pipeline-p1 → rollback/pre-pipeline-b3 → rollback/pre-pipeline-merge。
- **遗留**：P2 终稿组装（展示层债，backlog）；"调用次数不升"度量基线（下一圈验收尺子）；构建管线迁移票；socket-gap 评估票。

### B26 · 重构前后评估（token/速度/准确度）—— 提交（待填）· 2026-08-23

- **方法**：scripts/engine_eval.py（6 场景 × 前后两状态，计数 caller + 固定 usage + 中位耗时 + finals 对比）；pre = rollback/pre-pipeline-merge（b907b6fb），post = 当前 main。
- **结果**：
  | 场景 | 调用数（前后） | token（前后） | 中位耗时 ms（前→后） |
  |---|---|---|---|
  | N1 纯聊 | 1=1 | 200=200 | 1→8 |
  | N2 工具轮 | 2=2 | 400=400 | 38→54 |
  | N3 写拒绝 | 7=7 | 1400=1400 | 2→24 |
  | A1 auto 只读 | 2=2 | 400=400 | 34→52 |
  | A2 auto 写拒绝 | 2=2 | 400=400 | 1→8 |
  | P1 承诺回注 | 6=6 | 1200=1200 | 3→24 |
- **结论（诚实）**：调用数/token **零变化**（重构保持行为逐字节不变，含原有调用结构——结构性重构不省 token，这是设计使然）；finals 内容 **IDENTICAL**（准确度不变）；毫秒级耗时微升（墙的间接层开销，纯 Python 微秒级，相对真实 LLM 秒级延迟可忽略）。
- **关键认知**：token/速度的**下降不是本重构的产物**——行为保持型重构不改变调用结构；真正的省 token 是**下一圈**的事（结构已干净，可安全地减少回注次数/优化闸），本评估为下一圈立了基线（每场景调用数已知）。
- **遗留**：下一圈"调用次数优化"以此为对照基线；scripts/engine_eval.py 可复用。

### B27 · 宪法 v1.3：汇报必须带架构坐标 —— 提交（待填）· 2026-08-23
- **owner 定调**：汇报结构 = owner 判断模型——"5 个模块"式清单会掩盖耦合状态（走廊器官 vs 独立任务），导致判断走偏。
- **改动**：HARCHITECTURE Principle 5 新增"汇报必须带架构坐标"条款——任务/计划/状态汇报必须标明体系位置（走廊/门口/屋子）与耦合关系；禁止无坐标的平铺任务清单。
- **范围**：docs/HARCHITECTURE.md；零代码。
- **遗留影响**：后续所有汇报（含本轮 E1-E5）按此执行。

### B28 · 范式思考锚点：环路学习（RL 提议 parked）—— 提交（待填）· 2026-08-23
- **owner 提议（暂不实现）**：当前 harness 不形成学习环路；memory ≠ 强化学习；提议失败点即时强化。
- **中间形态候选**："失败点反射"（即时记录+注入下一次调用+可测复现率+自动过期）。
- **落盘**：docs/PARADIGM-REINFORCEMENT-LOOP.md（含待议问题，观点可演化）。
- **范围**：docs/ 1 文件；零代码。

### B29 · 范式修正：RL 对象 = harness（Agent 要有灵魂）—— 提交（待填）· 2026-08-23
- **owner 修正**：RL 不作用于模型（无能力也不需要），作用于 **harness 层**——模型不变，harness 在使用中学习用户。
- **核心理念**：Agent 要有灵魂 = 越用越契合用户、形成默契；实体 = harness 上随使用累积的用户适配层（记忆召回/工具选择/注入选择/闸参数/上下文组成，各一张按用户权重表，bandit 式在线更新），模型换代不丢。
- **落盘**：docs/PARADIGM-REINFORCEMENT-LOOP.md 更新（移除"与模型换代冲突"表述，新增可学习点+奖励信号表）。

### B30 · Harness 骨干通信设计定稿 —— 提交（待填）· 2026-08-23
- **owner 认可**"统一窗口"模式（走廊问、部门答；4 种接法 → 1 种）。
- **落盘**：docs/HARNESS-BACKBONE.md——五块坐标与现状耦合 + 统一窗口合同 + **收益假设（可验证）** + 执行顺序。
- **收益假设要点（诚实）**：内部收益确定（可重排/可测/可拆）；表象上 engine 缩小、准确度不变、速度持平；token **短期持平、中期下降**（解耦不省 token，省 token 是拆补偿约束的中期收益）。
- **执行顺序**：①安全 → ②工具执行 → ③上下文 → ④小屋 → ⑤出口；每步先白话设计过目再动手。

### B31 · E1 安全手册合一（骨干通信第 1 步）—— 提交 `f0ddc39b` · 2026-08-23（分支 feat/harness-backbone-e1）
- **改动**：execute_terminal 删除本地 DANGEROUS_PATTERNS 拷贝（12 条，已与主表漂移），引用 command_safety 权威表（20 条）为单一事实源；is_dangerous 循环适配 (pattern, reason) 元组。
- **安全政策（owner 定调 A：安全从严）**：终端最后防线由 12 条扩到 20 条——新增拦截 git push --force / killall/pkill / /etc 写 / shutdown / mkfs / 反引号 等；heredoc/引号骨架剥离逻辑保留（字面内容不误伤，auto-g2 用例验证）。
- **验证（快速，未跑全量）**：行为基线 6/6 diff=0；安全系 234 测试过（p0_fixes/auto_g2/command_safety）+ engine/auto 76 过。
- **收益假设对账（B30 假设①）**：连接方式 4→1 的第一步落地（终端不再持私有手册）；表象：安全更强、行为不变。

### B32 · E2 工具执行环：fallback 字典数据化 —— 提交（待填）· 2026-08-23（feat/harness-backbone-e1）
- **坐标**：走廊的动手段。
- **改动**：_TOOL_FALLBACKS（55 行内联字典，每调用重建）提为模块级常量；清理重复键 file_operation（dict 后者生效，前者死行，行为不变）。
- **验证（快速）**：行为基线 6/6；工具系 107 测试过；全量回归后台跑。
- **收益对账（B30 假设②）**：工具执行环向"工具执行部"迈第一步——失败建议从"方法内数据"变"模块级数据"（可独立测试/替换）。

### B33 · E4a computer use 政策搬出 —— 提交（待填）· 2026-08-23（feat/harness-backbone-e1）
- **坐标**：屋子（政策房）。
- **改动**：engine 6 个 _cu_* 方法（约 90 行）搬入 core/cu_policy.py（纯函数+参数化，不持有 engine 引用）；engine 保留薄壳委托（行为逐字节一致）；_CU_COOPERATION_TOOLS 随迁。
- **验证（快速）**：行为基线 6/6；computer use 系 37 测试过（core/awareness + e2e）。
- **收益对账（B30 假设④）**：政策房搬入独立模块——cu 政策可独立测试/替换，engine 瘦身。

### B34 · E4b 循环检测搬出 —— 提交（待填）· 2026-08-23（feat/harness-backbone-e1）
- **坐标**：屋子（观察房）。
- **改动**：engine 4 个循环检测方法（_round_sig/_last_n_tool_rounds/_has_progress_signal/_judge_loop_verdict，约 65 行）搬入 core/loop_detect.py（纯函数 + history 参数化）；engine 薄壳委托（行为不变）。
- **修正**：此前评估称"循环检测与 round_tracker 重复"——实查 round_tracker 无这些方法，是独立关注点长在 engine，本次搬为独立模块。
- **验证（快速）**：行为基线 6/6；engine_core/e2e/bugfixes 102 测试过。

### B35 · E4c 沉淀预筛闸搬出 —— 提交（待填）· 2026-08-23（feat/harness-backbone-e1）
- **坐标**：屋子（沉淀提取的纯判断部分）。
- **改动**：_takeaway_worthy + 价值关键词/确认词常量搬入 core/takeaway_filter.py（纯函数）；Engine._takeaway_worthy 薄壳委托（test 仍经 Engine 调用，行为不变）。
- **验证（快速）**：行为基线 6/6；takeaway_gate/e4a 17 测试过。
- **说明**：_extract_takeaways（LLM 提取编排）仍留 engine（依赖 history/事件/LLM，属走廊编排），纯判断闸已独立可测。

### B36 · E5 出口组装房（P2 终稿组装）—— 提交（待填）· 2026-08-23（feat/harness-backbone-e1）
- **坐标**：走廊的出口。
- **改动**：台账尾注/交接清单/format/思考块展示搬入 _assemble_final_output（走廊办事窗口）；FinalAssemblyStage 进回复段走廊；行为逐字节一致。
- **验证（快速）**：行为基线 6/6；goal_gate/e2e/ledger_1b/auto 97 测试过。
- **收益对账（B30 假设⑤）**：出口组装成为可独立测试的部门；E5 完成后 **E1-E5 全部落地**（安全单一源/fallback 数据化/cu 政策/循环检测/沉淀预筛/出口组装）。

### B37 · E1-E5 整批全量回归 —— 提交（待填）· 2026-08-23（feat/harness-backbone-e1）
- **结果**：2854 过 / 1 败 / 110s——唯一失败为 test_tel_8_zero_interference（**已知分支状态假象**：治理测试对分支新文件报未授权，合 main 自动转绿，此前两次合并已验证）。
- **结论**：E1-E5 整批行为零真实回归（每块基线 6/6 + 针对性测试全绿）。
- **收益对账（B30 假设，全部第一步落地）**：安全单一源 / fallback 数据化 / cu 政策模块 / 循环检测模块 / 沉淀预筛模块 / 出口组装房——"统一窗口"模式在 6 个点落地，engine 瘦身（6 个方法搬出 + 字典数据化 + 组装外移）。

## 待办追溯索引

- 修绿剩余：`data/tickets/TICKET-MAIN-REGREEN.md` §4
- D1 遗留（D2/D3）：`data/tickets/TICKET-DEMOLISH-OFFICE-DUO.md` §8
