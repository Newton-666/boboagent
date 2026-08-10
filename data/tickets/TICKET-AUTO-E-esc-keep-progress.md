# TICKET-AUTO-E：ESC 硬终止保进度 + Ctrl+C 退出 + 前端按键统一

> 立案：2026-08-10 · 依据 v0.7 裁决二 + bobo 改动面核实报告（2026-08-10）
> 分支：feat/ticket-auto-e（自最新 main 切出）
> 纪律：branch 施工、五查汇报、未终审不 merge 不 push
> 改动面：后端 engine_adapter.py + 前端 useInputHandlers.ts 等 + 双端测试

---

## Kimi 对 Q1-Q4 的裁决

- **Q1（中断时发 message.complete）**：**发**。维持"回合必有一个结束事件"铁律；TUI 已有 interrupted 抑制逻辑，发了安全；
- **Q2（ESC 无活跃层时行为）**：分两种——**busy（引擎跑活中）→ 触发全局 interruptTurn**（这是 ESC 的主职责：用户拍停 bobo）；**idle（没在跑活）→ 无操作**，绝不清空 composer（防误触丢输入）；
- **Q3（焦点模型）**：从 `$overlayState` 推导焦点栈，**零新状态**，不建 focusStore；
- **Q4（组件级 ESC）**：逻辑**收敛到全局统一入口**（useInputHandlers），组件级仅保留提示文案；消除"组件级+全局级同时响应同一 ESC"的双处理。

---

## 一、施工内容

### E-1. 后端：中断保进度（core/engine_adapter.py，根因 285-287 行）

现状：中断即 `return`，其后 checkpoints/history/ledger 回写 + save_session_to_disk 全部跳过——本次回合进度全丢。

改为：**中断时照样回写**——
- `session["checkpoints"]`、`session["messages"] = engine.history`（中断瞬间的快照）、task_ledger 回写、`save_session_to_disk` 全部执行；
- 发 `message.complete`（Q1）；
- stdout 文本可标注"[已中断]"，但**进度必须落盘**；
- resume 后能看到中断前的写文件记录/台账/对话历史。

### E-2. 前端：ESC 统一分发（焦点优先级链，Q3/Q4）

useInputHandlers.ts 建单一 ESC 入口，优先级从高到低：

1. voice 组合键（ctrl/alt/super+escape，不动）；
2. 输入编辑态：queue-edit cancel > selection clear；
3. 最顶层 overlay：approval（deny）> clarify（typing→回退选择；否则 cancel）> confirm > pager（关闭）；
4. 常驻面板：sessions > agents > modelPicker > skillsHub > pluginsHub（关闭）；
5. 无活跃层：**busy → interruptTurn（session.interrupt）；idle → 无操作**（Q2）；

组件级（prompts.tsx / overlayControls.tsx / modelPicker.tsx）的 ESC 逻辑收敛到统一入口，组件只留提示文案。

### E-3. Ctrl+C 语义（保持现状即正确，核实钉死）

核实报告确认：Ctrl+C 现状已是 busy→中断 / 有输入→清空 / 否则退出——**与 v0.7 裁决一致**（中断归中断、退出归退出）。本项为核实+测试钉死，不改行为；若发现与描述不符才修。

### E-4. 测试

后端新增：mock interrupt_event 已 set → 断言 session checkpoints/messages 落盘、message.complete 发射（此前 tests 零 interrupt 覆盖）；
前端新增/更新：ESC 优先级链各层用例（overlay 在场不走 interrupt、busy 无 overlay 走 interrupt、idle 无操作）；Ctrl+C 三态钉死。

## 二、验收（终审口径）

1. 引擎跑活中（无 overlay）按 ESC → 中断，且**session 落盘含中断前进度**（checkpoints/messages 非空、resume 可见）；
2. approval overlay 在场按 ESC → deny，**不触发** interruptTurn；
3. idle 按 ESC → 无操作，composer 内容不丢；
4. 中断后发 message.complete；
5. Ctrl+C 三态行为不变；
6. auto 决策环零回归（票 A/B/D 测试全过）；
7. 全量 pytest + 前端测试零回归（pytest 基线 1682 passed / 2 skipped）；真实库 md5 闸门照旧。

## 三、边界（明确不做）

- 不动 auto 决策树（A/B/D 已闭环）；
- 不做 TUI 底栏 AUTO ON（AUTO-F）；
- 不做台账新字段（票 C）；
- 不建 focusStore；不改 voice 组合键。

## 四、五查汇报要求

照旧：改了什么 / 验收逐条 / 测试输出原文（pytest + 前端测试）/ commit 与分支 / git status 原文 / 是否需重启。
禁止项：未终审不 merge、不 push、不碰 main。
