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

### B4 · main 修绿 B 批追加 —— 提交（待填，随本批）· 2026-08-23

- **之前问题**：perf_1（成文挂死超时测试）与 core_r3（R2b ≥3 次工具豁免测试）失败——同为意图闸错位根因（B2 发现的 COST-3 意图调用吞 mock 首响应）。
- **改动内容**：
  1. perf_1：输入措辞"帮我选一下数据库方案"→"请选择数据库方案"避开意图闸（保住 HangOnFourthCall 第 4 次挂死定位）。
  2. core_r3：mock 队列前补意图占位（"查"为场景语义不可改措辞）。
- **范围**：tests/ 2 文件；无运行时代码改动。
- **解决后**：两文件全绿（累计 61 → 剩余 ~11：skill_audit 1、core_int2 1、computer_use_core 1、eng1 5、scan 6、g3 2、前端 4、watchdog 5——watchdog 与前端按既定策略不在本地批）。

---

## 宏观快照（每批后刷新 · 2026-08-23 更新于 B5）

```
阶段 0：D1 拆除 office/duo        ✅（engine 2,545→2,208）
阶段 1：main 修绿（测试债）       ✅ 已收口（61→15，精确数已核实；15 = watchdog 5 + cost1a_sandbox 3 + tool_park_1 1 + 前端 4 + gui_f4 1 + tel_8 1）
阶段 2：测试分层                 🔵 施工完成（live 标记 + addopts + CI 覆盖；分支 feat/test-layering，待验证后合 main）
阶段 3：engine 流水线圈            ⬜ ← 目标
```

**到 engine 还差几步**：
1. 分层后全量复跑（预期本地 15→10，watchdog 5 进 CI）
2. 阶段 2 合 main（owner 验收后）
3. 前端票（4 个）+ socket-gap 票（并行）
4. cost1a_sandbox 3 + tool_park_1 1（校准类，随阶段 2 后或前端票一起）

→ 阶段 2 收口后，阶段 3（engine 流水线圈）开工。
本次记录批次：B0–B8。下次批次合入时：先写微观条目，再刷新本快照（强制，无需提醒）。

---

### B5 · main 修绿 B 批追加二 —— 提交（待填）· 2026-08-23

- **之前问题**：待查 7 文件——eng1(5)+scan(6) 为接口迁移类（run_engine 签名新增 computer_use_mode，测试调用没跟上）；g3(2) 为 D1 的 /duo 帮助文本残留；computer_use_core 为测试桩过时（lambda 签名 + element_id 键）；core_int2 为 **llm_caller 真 bug**。
- **改动内容**：
  1. eng1/scan_l3b/scan_l3c/scan_l3_connect/g3：run_engine 调用补 `computer_use_mode={}`、SimpleNamespace/_FakeCtx 补属性、/duo 断言更新为现存命令。
  2. computer_use_core：`_capture_png` lambda 补 pid 参数 + `_collect_elements` 桩补 `element_id` 键。
  3. **core/llm_caller.py 真 bug 修复（判研产出）**：中断路径 `_sock_holder.get("sock")` → `getattr(_sock_holder, "sock", None)`——threading.local 无 .get，原代码中断时崩 AttributeError 而非抛 LLMInterrupted。**本批唯一运行时代码改动，范围 1 行**。
  4. **遗留裁决点**：skill_audit 断言 research 应注入，但 `data/skills/enabled.json` 里 `research: false`（运行时治理配置）——配置与测试冲突，**待 owner 裁决**（research 是否故意禁用）。
- **范围**：tests/ 8 文件 + core/llm_caller.py 1 行；其余为测试侧改动。
- **解决后**：eng1/scan 系/g3/computer_use_core/core_int2 全绿；真 bug 修复（中断路径不再崩溃）。
- **遗留影响**：skill_audit 1 个待裁决；watchdog 5（D 类暂缓）；前端 4（归前端票）；另记 socket 关闭语义 gap（主线程读不到 worker 线程 sock，中断时不关 socket 只抛异常——候选真 bug，另票评估）。

### B6 · main 修绿收口 —— 提交（待填）· 2026-08-23

- **之前问题**：skill_audit 断言 research 应注入，但 `data/skills/enabled.json` 为 research=false——配置与测试冲突，待 owner 裁决。
- **owner 裁决**（2026-08-23）：**所有禁用技能均为 owner 手动操作**——research 禁用是故意的，测试断言过时。
- **改动内容**：
  1. skill_audit 行为测试隔离运行时 enabled 配置（夹具 all_skills_enabled 置全开）——匹配/excludes 逻辑测试不再依赖治理状态，且修掉三个排除测试在禁用下的"空转通过"。
  2. 新增 `test_behavior_research_disabled_by_governance`——锁定"research 禁用时不注入"的治理行为（防误启）。
- **范围**：tests/ 1 文件；无运行时代码改动。
- **解决后**：阶段 1 全部 owner 可决项清零——61 个原始失败全部修复或明确归类（剩 watchdog 5 = D 类进阶段 2；前端 4 = 前端票）。
- **遗留影响**：无新增。

### B7 · 工作区清零 + 宪法入库 —— 提交（待填）· 2026-08-23

- **之前问题**：工作区有未提交残留——① duo_orchestrator.py 删除被 stash 操作反复弹回索引（D1 已提交过，属索引反复回退）；② docs/HARCHITECTURE.md 宪法修订（Principle 5 协作协议 + v1.1）长期滞留工作区。
- **owner 定调**（2026-08-23）：**GitHub 必须对齐，不能有未提交的东西；一切改动（哪怕一行代码、一个测试）必须入 CHANGE-LOG**——追溯源头 + backup 余地。
- **改动内容**：① duo_orchestrator.py 删除重新 stage 并入库；② HARCHITECTURE.md（宪法 Principle 5 + v1.1 修订）正式入库——内容 owner 已于当日批准。
- **范围**：git 索引修复 + 1 文档文件；无运行时代码改动。
- **解决后**：工作区代码侧清零（仅剩会话前既存的 dist/index.html 脏构建产物与 untracked 杂项，非本次产生）。
- **遗留影响**：dist/index.html 为会话前既有脏文件，未动；98 个 untracked 为会话前既有杂项。

### B8 · 阶段 2 分层施工 —— 提交（待填）· 2026-08-23（分支 feat/test-layering）

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

## 待办追溯索引

- 修绿剩余：`data/tickets/TICKET-MAIN-REGREEN.md` §4
- D1 遗留（D2/D3）：`data/tickets/TICKET-DEMOLISH-OFFICE-DUO.md` §8
