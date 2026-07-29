# 票 M：TUI 状态灯 / 回合边界可见化

**优先级**：高（"假停"感知问题的治本）｜ **风险**：低（纯网关侧，不动 core 引擎逻辑可降级）
**分支**：`feat/tui-status-light` ｜ **禁止**：merge / push，完成后五查汇报 + git status 原文等 Kimi 终审

---

## 一、背景（为什么做）

2026-07-28~29 两天内发生 8+ 次"用户以为 bobo 死了"事件，其中绝大多数经票 W 摄像头鉴定为 `engine.thread.exit reason=completed`——**正常收工，但用户无法分辨**。

根因：TUI 的状态显示只有两个语义——工作中（contemplating/synthesizing）和 ready。引擎"正常干完活"和"线程无声死亡"在用户眼里长得一模一样：都变成 ready。

已具备的物证基础：
- 票 W 摄像头：`engine.thread.start` / `engine.thread.exit`（含 reason）已落事件总线
- 事件链：engine._notify → engine_adapter.on_event → emit("status.update") → TUI

## 二、目标

让用户一眼能分辨三种状态：

| 状态 | 现在的显示 | 目标显示 |
|---|---|---|
| 引擎工作中 | contemplating 等（但长时间无变化像卡住） | 工作中文案 + **心跳**（"仍在工作 · 已运行 42s"） |
| 正常收工 | ready（和死亡一样） | 明确的**回合结束标记**（"回合完成 · 耗时 Xs"） |
| 引擎异常退出 | ready（无任何提示！） | **红色/警告级退出标记**，含 exit reason |

## 三、范围与约束

### 允许改
- `bobo_tui_gateway/`（entry.py / handlers / engine_adapter 接线）
- `core/engine_adapter.py` 的 on_event 翻译层
- 如需引擎侧补事件：`core/engine.py` 只允许**新增 _notify 调用**，禁止改状态机逻辑

### 禁止 / 降级原则
- **首选零前端改动**：`bobo_tui_gateway/static/entry.js` 是 3MB minified bundle，无源码。所有新状态必须复用 TUI 已渲染的 status.update 通道。
- **第一步必须做侦察**：在 entry.js 里定位 kind→文案 映射表（"contemplating" 在 bundle 中出现 1 次），确认哪些 kind 会被渲染、未知 kind 会不会被丢弃。侦察结论写进五查汇报。若未知 kind 被丢弃，则复用已渲染的 kind 承载新文案。
- 若侦察证明前端可安全小改（如只是加一行映射），需单独向 Kimi 报批后才可动 entry.js。

## 四、功能需求

1. **回合边界事件**：engine 一轮 run 开始 → 网关收到首个事件时记 turn_start；`complete`/`error` 事件 → 记 turn_end。网关侧向 TUI 推送明确的边界状态（如 "回合完成 · 耗时 12s · 工具调用 3 次"）。
2. **引擎退出标记**：engine 线程退出时（gateway 已有 join/监控点，票 W 摄像头位置），向 TUI 推送 `status.update`，文案含 exit reason：completed → 正常结束；其他 → "⚠️ 引擎异常退出：{reason}"。
3. **心跳**：engine 线程存活但连续 N 秒（建议 15s，环境变量 `BOBO_TUI_HEARTBEAT_SEC` 可调）无任何事件 → 网关推送心跳状态（"仍在工作 · 已运行 Xs"）。心跳线程必须 daemon、engine 结束即停，禁止产生新的孤儿线程（票 H 教训）。
4. **不刷屏**：心跳只更新同一条状态，不产生消息流新条目。

## 五、验收标准（真撞闸，禁止合成）

1. 起真实 bobo（scripts/smoke_boot.py 或手动），跑一个长任务（如让它读大文件+分析），观察 TUI：工作中每 15s 心跳更新。
2. 正常收工后 TUI 出现"回合完成"标记，不是光秃秃 ready。
3. 模拟异常（测试环境向 engine 注入致命错误或直接 kill 引擎线程），TUI 出现含 reason 的异常退出标记。
4. `data/logs/events.jsonl` 中边界事件与 TUI 显示一致。
5. 全量 pytest 基线 1012 passed / 2 skipped 不回归，新增用例覆盖：turn 边界计时、心跳触发与停止、exit reason 映射、**回合小结生成（含工具统计/耗时/台账行的正确性，以及闲聊回合的省略路径）**。
6. 重启检查：改了 core/ 下 .py 则五查第 6 项必填"是"。
7. **撞闸验收追加**：真实 bobo 跑一个带工具调用的任务，收工后肉眼确认最后可见内容是回合小结，而不是工具调用框。

## 五.bis、回合小结（Turn Summary）——用户需求追加

**用户原话**："每次干完活应该做个小汇报，而不是留一个调用工具的界面。"

回合结束（complete/error）时，引擎必须产出一段简短的回合小结作为该回合的**最后一条可见内容**，而不是让屏幕定格在最后一个工具调用框上。

要求：
1. **触发时机**：engine 发出 `complete` 事件前，把小结作为正常回复的一部分输出（或网关侧在 complete 时追加一条 status.update 承载，二选一，以实现简洁者为准；若走网关侧，文案由网关从本轮事件统计生成，不额外消耗 LLM 调用）。
2. **内容**（从本轮已有事件统计生成，**禁止为此多发一次 LLM 调用**）：
   - 本轮干了什么（工具调用 N 次：工具名列表去重）
   - 结果状态（完成 / 出错及原因）
   - 耗时
   - 若有台账（task_ledger）：附 "台账 N/M done" 一行（复用票 K 降级摘要行的数据）
3. **形式**：复用已渲染的 status.update 通道或作为回复正文尾部，禁止依赖前端改动；若侦察证明前端可安全小改，可升级为独立卡片，单独报批。
4. **例外**：纯闲聊回合（无工具调用、无台账）可省略工具统计，只留一句话收尾，不强制模板化。

## 六、交付物

- 改动代码 + 新测试
- entry.js kind 映射侦察结论（写进五查汇报）
- 五查汇报 + git status 原文
