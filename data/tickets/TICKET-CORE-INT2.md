# TICKET-CORE-INT2 —— 桌面端中断失效取证 + 修复（P0）

> 施工前必读 docs/GUI-LESSONS.md。分支 feat/ticket-core-int2（自最新 main 切出）。未终审不 commit。
> owner 原话："切中断说了无数次，一刀切不断。" 本次原则：**先取证，再修复，不许再猜**。

## 现状（Kimi 已梳理，链路看起来是通的但实测无效）

- `handle_session_interrupt` → `core.engine_adapter.cancel(sid)` → `_running[sid]` 的 Event.set()，事件总线留有 `engine.cancel.requested` 痕迹
- 引擎检查点齐全：llm_caller 流式每 chunk（llm_caller.py:265）、重试、execute_terminal、engine.py:1318/1643/2212
- 但 owner 桌面端实测：按 Stop 后引擎继续跑

## 头号嫌疑（按优先级）

1. **双进程/多进程孤岛**：桌面端 gateway 与 TUI gateway 是独立进程，中断注册表互不相通；若存在多个 gateway 进程残留，UI 连的进程和跑引擎的进程不是同一个 → cancel 打了个空。实弹取证时必须先 `ps` 列出所有 bobo_tui_gateway / electron 进程确认
2. **sid 不一致**：interrupt 用的 sid 与 run_engine 注册的 sid 不是同一个值（如 resume 后 sid 变化、新建会话时序）
3. **Event 对象错位**：`engine._interrupt_event = interrupt_event`（engine_adapter.py:283）在引擎副本上是否真正生效——F9 后引擎跑在副本上，要确认副本拿到的是同一个 Event 实例

## 台账（建议 4 项）

- [ ] INT2-1 取证埋点：cancel 全链路打点——请求到达 / event 找到并 set / 引擎各检查点看到 is_set 的时刻与位置（llm 流式、工具执行、回合循环），全部写事件总线 `engine.cancel.*` 系列
- [ ] INT2-2 实弹复现：桌面端起长任务按 Stop，读事件总线日志，定位断在哪一环，写入取证小节
- [ ] INT2-3 按取证结论修复（若是进程孤岛：interrupt 走文件旗标或共享注册表等跨进程机制；若是 sid/副本错位：对齐）
- [ ] INT2-4 专项测试（模拟中断到达各检查点）+ 全量零回归 + 五查收工（L12 格式）

## 验收

- 取证小节必须给出"断在第几环"的确切结论 + 事件总线日志原文摘录
- 修复后实弹：桌面端起长任务按 Stop，引擎在 1 个检查点周期内停下（流式期间 ≤1 个 chunk）
