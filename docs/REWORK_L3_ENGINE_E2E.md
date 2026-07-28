# REWORK_L3_ENGINE_E2E — e2e 测试台 duo B 打回（4 成立 + 1 半成立）

> 2026-07-28 Kimi 仲裁后出单。duo B 事后审查 2 严重 + 3 中等，
> 我逐条复核代码后的裁决：

## Kimi 仲裁（已验证）

| B 的指控 | 裁决 | 证据 |
|---|---|---|
| ① 场景 d 绕过中断机制 | **成立（严重）** | 手动 append 孤儿，没测 _pending_tool_calls 残留和恢复路径 |
| ② STATE_ERROR 死状态 | **半成立** | engine.py:554 设了 ERROR，但 THINKING 分支 content 非空 → 走 RESPONDING 覆盖——**死赋值成立**；但"行为 bug"不成立：错误文本作为 assistant 消息送达用户恰是当前合理 UX（用户看到的"HTTP 400"消息就是这条路径）。修法是消歧义，不是改行为 |
| ③ usage 字段不全 | 成立 | prompt_tokens 缺失，token 阈值分支永远测不到 |
| ④ 场景 a 断言过弱 | 成立 | `in` 断言容忍错误序列 |
| ⑤ 7 条转换未覆盖 | 成立 | 冲突检测/空响应重试/MAX_STEPS 等 |

## 打回文本（粘贴给 bobo）

```
打回：e2e 测试台 duo B 审查 4 项成立（feat/engine-e2e-harness 继续）

工作目录：/Users/niuqingwei/Desktop/BOBO_Project_Backup
duo B 审查 + Kimi 仲裁后的返工项，按优先级：

【必修 1】场景 d 改真中断（严重）
现在手动 append 孤儿是"布置尸体"，不是"制造事故"。改为：
让 FakeToolExecutor 在执行第二个工具时抛异常/模拟中断，
断言三件事：a. engine 留下脏状态（_pending_tool_calls 有残留、
state 非 DONE）b. 清洗后历史合法 c. 下一轮 run() 能正常恢复。
注意：如果 b/c 断言失败——那不是测试错，是发现了引擎恢复能力
的真实缺口。此时停下上报，**不许顺手改 engine**（L4 边界，
恢复机制要单独评审）。把调研结果写进汇报。

【必修 2】STATE_ERROR 死赋值消歧义（严重，小改）
engine.py:554 _call_llm 设 STATE_ERROR 后 5 行内被覆盖。
二选一，commit 说明理由：
a. _call_llm 不再设 ERROR（承认"错误文本即回复"的现语义）
b. THINKING 分支尊重 ERROR（设了就不再覆盖）
注意 b 会改变用户看到的错误呈现方式，选 b 要附行为对比说明。

【必修 3】测试强度三项（中等）
- FakeLLMCaller 的 usage 补 prompt_tokens/completion_tokens
- 场景 a/b 的状态断言从 in 改为完整序列比对（顺序敏感）
- 补 5 条未覆盖转换中至少 3 条：EXECUTING→THINKING 冲突检测、
  THINKING→THINKING 空响应重试、MAX_STEPS→RESPONDING

要求：同分支 commit，五查汇报（表格），然后停。
汇报里必须包含必修 1 的调研结论（引擎恢复能力现状）。

验收标准：
① 场景 d 三个断言全过；若不过，引擎缺口调研结论完整
② STATE_ERROR 消歧义方向明确 + 理由
③ 序列断言顺序敏感 + usage 字段完整
④ pytest 全绿 + 零真实依赖保持
```

## 后续

- 必修 1 若暴露引擎恢复缺口 → 单独 L4 票评审（可能就是
  崩溃案凶手隔壁的房间）
- 返工交付后我复审 + duo B 二审（这次顺序不能省）
