# 票 Z v3：无账硬闸（no-ledger hard gate）

> 状态：待开工
> 前置：票 Z v2 收工闸（已 merge，commit 8fc5a3e）
> 分支：`feat/no-ledger-gate`（从最新 main 新建）

## 病灶

票 Z v2 收工闸只防"说了不做"（承诺检测）和"有账没销"（台账闸），
防不了"不说不做"：模型全程不建台账、收尾用中性陈述句（无承诺词、无完成词），
RESPONDING 闸走到 `elif not self.task_ledger:` 分支直接放行，
只留下一条 `task.no_ledger` 统计事件。

实战案例：票 X 复核任务全程 46 项工作零台账，正常收工。

## 铁律（用户原话）

回合结束 ≠ 事做完。没做完之前不许停，做完必须停。

## 处方

**判定信号已存在**：`self.current_tool_round > 0` 即本回合发生过工具调用
（run() 入口初始化，EXECUTING 每轮 +1）。这就是"工作回合"的权威判据。

修改 `core/engine.py` RESPONDING 收工闸的 `elif not self.task_ledger:` 分支：

### 1. 工作回合无账 → 视同未完成，强制回注

条件：`not self.task_ledger and self.current_tool_round > 0`

- 写事件 `goal_gate.no_ledger_detected`：
  `session_id`、`tool_round: self.current_tool_round`
- 共享现有 `_ledger_reinject_count` 熔断器（与承诺闸、台账闸同一个计数）：
  - `< 2`：计数 +1，回注 user 消息：
    `"本回合调用了工具但没有建立任务台账。请立即用 task_ledger 建账（已完成的列 done，未完成的列 pending），然后继续。不要说明、不要道歉，直接做。"`
    清 `_pending_content` / `_pending_tool_calls`，`current_depth += 1`，
    `_emit_state_change(STATE_THINKING, "no-ledger re-injection")`，return。
  - 达 2 次熔断：放行，终稿附加
    `"\n\n⚠️ 工作回合未建台账，引擎放行"`，
    写事件 `goal_gate.released`，`reason: "no_ledger_exhausted"`，
    带 `reinject_count` 和 `tool_round`。

### 2. 纯聊天回合 → 维持原样

条件：`not self.task_ledger and self.current_tool_round == 0`
（用户说"你好""谢谢"这类，零工具调用）

- 直接放行，`task.no_ledger` 事件照旧，**行为不变**。

### 3. 回注后被触发时的配合

回注后模型建账：若全 done → 干净收工；若有 pending → 落到现有台账闸，
继续走 `_ledger_reinject_count`（此时计数可能已用掉 1 次，属预期：
熔断器的设计意图就是"一个回合最多劝 2 次"，不按闸的种类分别计数）。

## 验收金标准（tests/test_goal_gate.py 追加新 class）

1. **工作回合无账被拦**：FakeLLM 模拟 1 轮工具调用后给中性收尾文本
   （无承诺词无完成词）→ 不回 complete，回注消息含"task_ledger"，
   事件 `goal_gate.no_ledger_detected` 落地。
2. **回注后建账全销 → 干净收工**：第二回合建账并全 done → 正常 done，
   history 中回注消息仅 1 条。
3. **两次熔断放行**：连续 2 回合不建账 → 放行，终稿含
   "⚠️ 工作回合未建台账"，事件 `goal_gate.released` reason=no_ledger_exhausted。
4. **纯聊天零误伤**：tool_round=0 且无台账 → 直接 done，
   `task.no_ledger` 事件照旧，history 无回注。
5. **回归**：现有票 Z v2 的 8 条测试 + 票 K v2 台账测试全部不动、全绿。

## 边界与纪律

- 只动 RESPONDING 闸的 no-ledger 分支 + 测试，**禁止顺手改其他闸逻辑**。
- 熔断计数、回注消息格式、`_pending_content` 清理顺序照抄现有台账闸的写法，保持闸家族一致性。
- 分支 `feat/no-ledger-gate`，开工前 `git branch --show-current` 确认。
- 完成后五查汇报（含 git status 原文 + git branch --show-current 原文），
  **禁止 merge、禁止 push**，等 Kimi 终审。
- 改了 `core/engine.py` → 五查第 6 项填"是，需重启生效"。
