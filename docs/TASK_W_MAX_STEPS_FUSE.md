# 票 W：步数熔断整改 — 保险丝不许伪装成正常收工

> 状态：待开工
> 分支：`feat/max-steps-gate`（从最新 main 新建）
> 来源：2026-07-29 22:42 实战，票 U 首回合 73 步撞 MAX_STEPS=70，
> 线程以 reason=completed 退出、零最终回复、台账 7/8 遗留

## 病灶（core/engine.py run()，约 1211 行）

```python
if self._step_count > self.MAX_STEPS:
    notify("步骤已用完，正在生成最终回复...")
    _emit_state_change(RESPONDING, "continuing")
    break   # 跳出循环：收工闸不执行、无最终回复、退出原因 completed
```

三宗罪：
1. **闸被绕过**：RESPONDING 分支的台账闸/承诺闸/无账闸整段跳过
2. **谎称 completed**：`engine.thread.exit reason=completed`，与正常收工无法区分；
   只有 state.change 的 `reason: continuing` 留痕
3. **零回复**："正在生成最终回复"是空话，break 后什么都不生成，
   用户只看到"回合完成"统计行，不知道任务没做完

## 处方

### 1. 熔断时生成真实的收尾消息（不再空 break）

`_step_count > MAX_STEPS` 时：
- 设置 `self._exit_reason = "max_steps"`（默认 `"completed"`，reset()/run() 入口复位）
- 合成收尾内容（**不调 LLM**，此时历史可能已很长，直接模板化）：
  ```
  ⚠️ 步数保险丝触发（已用 N/70 步），回合强制收尾。
  台账 M 项未完成：「标题1」「标题2」…
  发送"继续"即可接着干，进度在台账里。
  ```
  （无台账时去掉台账行。）
- 走 `_notify("complete", ...)` 把这条消息发给用户（复用现有通道），
  再 `_emit_state_change(self.STATE_DONE, "max_steps fuse")`，正常出循环
- 写事件 `engine.step_fuse`：session_id、step_count、pending_items、
  tool_round

### 2. 退出原因不再谎称 completed

`engine.thread.exit` 的 reason 使用 `self._exit_reason`
（engine_adapter 或 engine 退出处，找到 reason="completed" 的产生点，改为读该字段）。
TUI 回合统计行：reason=max_steps 时显示"⏱ 步数熔断"而非"回合完成"。
（若 TUI 是 minified bundle 改不动，至少在事件层区分 + 收尾消息本身可见，
TUI 文案列为可选项，做不到要在五查汇报里说明。）

### 3. MAX_STEPS 可配置

`MAX_STEPS = int(os.environ.get("BOBO_MAX_STEPS", 70))`，
类属性读取时走 env，默认值 70 不变。bobo_config 能查到即够，
不强制接入配置工具。

### 4. 与收工闸的关系（重要设计约束）

熔断收尾**不重跑**三道收工闸（此时回注已无意义——步数没了）。
收尾消息本身就是遗言，替代闸的 ⚠️ 功能。
`_ledger_reinject_count` 在 run() 入口复位逻辑不受影响。

## 验收金标准（tests/test_step_fuse.py 新建）

1. FakeLLM 无限循环调工具 → 第 71 步熔断，complete 消息含
   "步数保险丝触发"和未完成台账标题，状态 DONE。
2. `engine.thread.exit` 事件 reason="max_steps"（不是 completed）。
3. `engine.step_fuse` 事件落地，字段齐全。
4. 无台账时熔断：消息无台账行，行为正常。
5. BOBO_MAX_STEPS=5 时第 6 步熔断（env 覆盖生效）。
6. 正常回合（步数内完成）：_exit_reason="completed"，行为与现状零差异。
7. 全量 pytest 通过，零回归。

## 纪律

- 开工前 `git branch --show-current` 确认在 `feat/max-steps-gate`。
- 完成后五查汇报（含 git status 原文 + git branch --show-current 原文），
  ⛔️ 禁止 merge、禁止 push，等 Kimi 终审。
- 改了 core/ → 五查第 6 项填"是，需重启生效"。
- commit 被安全闸拦就用你已验证可行的方式提交，或把命令报给 Kimi 代执行。
