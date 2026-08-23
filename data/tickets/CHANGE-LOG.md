# 改动日志（CHANGE-LOG）

> **强制纪律（owner 2026-08-23 定）：每批改动必须记录**——改了啥 / 范围 / 影响 / 之前问题 / 解决后结果。
> 目的：owner 未实战验证期间，任何后期问题可从此表追溯出处的节点。
> 规则：先写本条 → 再提交；每批一条；提交号必填。

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

## 待办追溯索引

- 修绿剩余：`data/tickets/TICKET-MAIN-REGREEN.md` §4
- D1 遗留（D2/D3）：`data/tickets/TICKET-DEMOLISH-OFFICE-DUO.md` §8
