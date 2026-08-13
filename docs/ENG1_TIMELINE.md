# ENG-1a 时序取证：message.complete 之后的引擎活动

日期：2026-08-13。分支：feat/ticket-eng1（自 main 882ddff 切出）。
取证范围：core/、bobo_tui_gateway/、ui-tui/ 代码时序 + data/logs/events.jsonl + data/logs/bobo.log 实测数据。
目标：还原"回复发出后引擎仍有拖尾活动"的真实时间线，区分引擎层拖尾 vs 显示层未回 ready。

---

## 1. 结论速览（先讲结论）

| # | 定性 | 证据强度 | 说明 |
|---|------|---------|------|
| 1 | **引擎层拖尾（真）**：message.complete 之后 adapter 仍 emit `status.update`（turn_exit/turn_summary） | 代码实锤 | 违反 owner 裁决"message.complete 后零用户可见事件"；TUI 追加消息流 + 覆盖 ready 状态栏且保留至下一回合 |
| 2 | **引擎层拖尾（理论窗口）**：心跳 daemon 停止晚于 message.complete | 代码实锤（窗口毫秒级） | `_hb_stop.set()` 在 message.complete 之后执行，tick 窗口存在但概率低 |
| 3 | **体感大头（回复"前"拖尾）**：takeaway 提取（LLM 调用，实测 55.7s）在回复文本流式显示完整之后、message.complete 之前执行 | bobo.log 实测 | 用户看到回复已完整但界面 busy → "答完不收工"体感来源；且该调用**不写 llm.call 事件**（观测盲区） |
| 4 | **显示层（排除）**：TUI 收到 message.complete 立即 setStatus('ready') | 代码实锤 | 显示层回 ready 无延迟；但 ready 会被 #1 的 turn_summary 覆盖 |

**一句话**：回复文本完整显示 ≠ 回合结束。message.complete 是回合真正的结束信号，而它发出之后仍有 turn_summary 事件；它发出之前，引擎还在跑 55.7 秒的 takeaway 提取。两头都在"答完不收工"。

---

## 2. 代码时序链（静态取证）

### 2.1 engine_adapter.py：message.complete 之后仍有 emit

`core/engine_adapter.py` run_engine 收尾段（318-358 行）：

```
318  emit("message.complete", sid, {session_id, final_text, usage})   ← 回合结束信号（TUI 回 ready）
...
324  _hb_stop.set()                          ← 心跳停止【在 complete 之后】
325  _elapsed = time.time() - _turn_start[0]
326-343  构建回合小结文案（工具调用 N 次 / 台账 X/Y done / 耗时）
344  emit("status.update", {kind: "turn_exit",   text: "引擎退出: ..."})    ← 异常/中断路径
352  emit("status.update", {kind: "turn_summary", text: "回合完成 · ..."})  ← 正常路径【在 complete 之后】
```

- `message.complete`（318 行）→ TUI 立即 `setStatus('ready')`（见 2.3）
- 但随后 344/352 行的 `status.update` 是**用户可见事件**：TUI 会 `sys()` 追加到消息流、`setStatus` 覆盖状态栏、statusKind 置为 'turn_summary'/'turn_exit' 且**不走 restoreStatusAfter 快闪重置，状态栏保留至下一回合**（ui-tui/src/app/createGatewayEventHandler.ts:530-534）。
- 结果：用户看到"回复完成后又冒出一行『回合完成 · 耗时 XXs · 工具调用 N 次』"，且状态栏从 ready 变成该文案。体感 = 回复发完了还在动。

### 2.2 engine.py：回复文本完整显示后仍有 LLM 调用

THINKING 分支（engine.py _step，约 1345-1440 行）：

```
_call_llm() 流式推送 thinking.delta → adapter 转 message.delta → TUI 逐字显示回复文本
  ↓ 文本已完整显示（用户看到回复）
verifier.check_and_inject(...)                 ← 验证器（可能额外 LLM 调用）
_extract_takeaways(fallback_content=...)       ← ★ LLM 调用，实测 55.7s（见 §3.2）
  → v5_memory add_entry（草稿记忆写盘）
  → living_notes write_living_notes（笔记写盘，notes.updated 事件）
  → 四个收工闸（goal_gate / 字段闸 / 补账闸 / 承诺闸）
  ↓ 闸全过
RESPONDING 分支：_notify("complete") → engine.run() 返回 → adapter 回写 session → emit message.complete
```

- **回复文本在 _call_llm 流式结束时已完整显示**（message.delta 推完），但回合状态仍 busy（thinking/executing）。
- 之后 takeaway 提取（一次真实 LLM 调用）、living notes 写盘、四个闸检查全部跑完，才到 message.complete → ready。
- 体感：回复文字已经齐了，界面还在"Working / 仍在工作"转圈。这正是 owner 描述"回复已经完整发出，但引擎仍在活动"的**最直接来源**（虽然严格在 message.complete 之前，但按用户体感"回复完"即答完）。

### 2.3 TUI 侧：显示层回 ready 是即时的（排除嫌疑）

`ui-tui/src/app/createGatewayEventHandler.ts:924-943`：

```
case 'message.complete':
  turnController.recordMessageComplete(...)
  appendMessage(finalMessages)          ← 回复落屏
  setStatus('ready')                    ← 立即回 ready
  patchUiState({ statusKind: '' })      ← 清状态
  return
```

- TUI 对 message.complete 的处理**无延迟、无异步**，显示层不存在"未回 ready"问题。
- 但注意：后续收到的 status.update（§2.1 的 turn_summary）会覆盖这个 ready。所以"ready 一闪而过，随即变成回合完成文案"。

### 2.4 心跳 daemon：停止晚于 complete（理论窗口）

`core/engine_adapter.py:264-275`：

```
def _hb_loop():
    while not _hb_stop.wait(_hb_sec):          # 每 15s
        _idle = time.time() - _last_event_ts[0]
        if _idle >= _hb_sec and _turn_start[0] > 0:
            emit("status.update", {kind: "heartbeat", text: "仍在工作 · 已运行 Xs"})
_hb_thread = Thread(target=_hb_loop, daemon=True); _hb_thread.start()
```

- 心跳每 15 秒检查一次；`_hb_stop.set()` 在 message.complete 之后（324 行）才调用。
- 若回合结束瞬间恰好 idle ≥ 15s，存在 message.complete 之后、_hb_stop 之前再 emit 一次 heartbeat 的窗口（毫秒级，概率低但顺序确实反了）。
- 正常路径下 heartbeat 在回合进行中 emit（"仍在工作 · 已运行 Xs"）——这也是"回复文本已完整但界面还在转"的可见表现之一。

---

## 3. 实测数据（bobo.log + events.jsonl 对齐）

### 3.1 全局账本统计：125 个回合，DONE 后零事件

对 data/logs/events.jsonl 全量（25905 行）按 sid 切分回合（thread.start → thread.exit）：

```
回合总数: 125
responding->done 之后、thread.exit 之前仍有 llm.call/tool.exec 的回合: 0
```

- **events.jsonl 视角：引擎状态机 DONE 后零 LLM/工具调用**。状态机本身没有拖尾。
- thread.exit 之后的事件全部是下一回合的 engine.thread.start（正常新回合），非拖尾。

### 3.2 盲区实证：takeaway 提取的 LLM 调用不写 llm.call 事件

bobo.log（会话 20260812_221207_50afc0）：

```
22:47:00,961 [DEBUG] core.engine:1382 extract_takeaways start (pre-gate)
22:47:56,665 [DEBUG] core.engine:1439 extract_takeaways done (pre-gate): 1 items   ← 耗时 55.7 秒！
22:47:56,666 [DEBUG] core.engine:1797 RESPONDING maybe_propose_skill start
22:47:56,710 [DEBUG] core.engine:1827 RESPONDING emit complete start: len=277
```

- 提取是一次真实的 LLM 调用（self.llm_caller(prompt, use_tools=False)，engine.py:1000），**实测 55.7 秒**。
- 但 events.jsonl 中该会话对应区间**没有对应的 llm.call 事件**——因为 llm.call 事件写在 `_call_llm` 路径（engine.py:1206/1242/1265），`_extract_takeaways` 直接调 `self.llm_caller`，绕过了事件写入点。
- **结论：events.jsonl 尾部静默 ≠ 引擎静默。** 票面验收标准"events.jsonl 尾部静默"存在观测盲区，须补 bobo.log/takeaway 事件交叉验证。

### 3.3 真实回合尾部时间线（50afc0，第二个回合）

| 相对时间 | 事件 | 触发者 | 用户可见 |
|---------|------|--------|---------|
| +2075.5s | engine.thread.start | adapter | 否 |
| +2078.0s | llm.call msg=10 (tool=False, 1077ms) | engine._call_llm | 流式文字 |
| +2078.0s | state.change → executing | engine | 否 |
| +2080.9s | llm.call msg=12 (tool=True, 1593ms) | engine._call_llm | 流式文字 |
| +2082.5s | goal_gate.no_ledger_detected → thinking 回注 | engine 闸 | 否 |
| +2086.2s | llm.call msg=13 (tool=True, 2013ms) | engine._call_llm | 流式文字 |
| +2089.8s | llm.call msg=15 (tool=True, 1830ms) | engine._call_llm | 流式文字 |
| +2093.6s | llm.call msg=17 (tool=True, 2202ms) | engine._call_llm | 流式文字 |
| +2093.6s | **（盲区）takeaway 提取 LLM 调用 55.7s** | engine._extract_takeaways | 否（界面 busy） |
| +2149.1s | notes.updated / library.mirror_sync | living_notes | 否 |
| +2149.3s | state.change thinking→responding | engine | 否 |
| +2149.3s | state.change responding→done | engine | 否 |
| +2149.3s | engine.thread.exit (completed, 73843ms) | adapter finally | 否 |
| （不在 events.jsonl） | message.complete | adapter:318 | **是（TUI 回 ready）** |
| （不在 events.jsonl） | status.update turn_summary "回合完成 · ..." | adapter:352 | **是（覆盖 ready）** |

- 回合总耗时 73.8s，其中**最后 55.7 秒（75%）花在 takeaway 提取**上——回复文本早就显示完了。
- message.complete 与 turn_summary 都在 events.jsonl 之外（emit 直发 TUI，不落账本），这是第二个观测盲区：**账本尾部静默但 TUI 仍有事件**。

---

## 4. 定性结论

### 引擎层拖尾（确凿，违反 owner 裁决语义）

1. **message.complete 之后 emit status.update（turn_exit/turn_summary）**：adapter 318 行发出 complete 后，344/352 行仍发用户可见事件。TUI 追加消息流 + 覆盖 ready 状态栏（保留至下一回合）。→ 修复方向：这两条 status.update 移到 message.complete **之前**，或并入 message.complete 的 usage 段。
2. **心跳停止晚于 complete**：_hb_stop.set() 在 complete 之后。→ 修复方向：先 _hb_stop.set() 再 emit complete。
3. **回复文本显示后、complete 前仍有长耗时活动**（takeaway 提取 55.7s + 闸检查）：用户体感"答完不收工"。→ 修复方向（ENG-1b 讨论）：提取前移/降级/异步静默，确保"回复发出即回合结束"。

### 显示层（排除）

- TUI message.complete → setStatus('ready') 即时，无显示层缺陷。ready 被 turn_summary 覆盖属引擎层问题（#1），不是 TUI bug。

### 观测盲区（验收标准修订建议）

- events.jsonl 尾部静默不足以证明"引擎静默"：takeaway 提取调用与 message.complete/turn_summary 都不落账本。
- ENG-1c 回归测试断言"message.complete 后零事件"时，须同时断言：无 status.update（turn_* 类）、无 takeaway/notes 类事件、心跳已停止。

---

## 5. 待 ENG-1b 决策点（报 owner）

1. turn_summary/turn_exit 移前到 message.complete 之前（保语义：先收尾后发 complete）？还是并入 complete payload？
2. takeaway 提取 55.7s 如何处置：并行化/降级（BOBO_TAKEAWAYS=off 已有开关）/回合后异步静默（但 owner 裁决"message.complete 后零 LLM 调用"冲突）/仅在有沉淀价值时触发？
3. 心跳：message.complete 前强制 _hb_stop.set()（保底），并让 heartbeat 不在"回复文本已完整"后继续发声。
4. ENG-1c 测试基线：以"message.complete 后零用户可见事件 + 零 LLM 调用"为断言，白名单仅纯日志。
