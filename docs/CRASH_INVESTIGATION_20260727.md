# 崩溃根因调查报告 — 2026-07-27 22:33（同类第三次）

> Kimi 取证。结论先行：**证据链断在"最终回复生成后、complete 事件发出前"
> 的 30 行代码里，但因无持久日志无法定到具体行。第一优先不是修 bug，
> 是补可观测性——否则每次崩溃都是考古。**

## 三次崩溃的共同模式

| 时间 | 最后可见事件 | 之后 |
|---|---|---|
| 07-26 16:27 | append_obsidian 工具结果 | 线程死，重启 HTTP 400 |
| 07-27 ~10:34 | duo 讨论中 | 假死（ready 但实际在跑） |
| 07-27 22:33 | pytest 工具结果（13 passed） | 用户两条消息无回应 |

共同点：**都是工具结果渲染之后、最终 assistant 消息之前断裂**。
不是 LLM 调用中死（那会有超时错误），是 turn 收尾阶段死。

## 本案时间线（铁证：access_log + 文件 mtime）

```
22:32:06  execute_terminal pytest（309ms，成功）
22:32:24  edit_file command_safety.py（继续改）
22:32:40  edit_file command_safety.py
22:32:43  execute_terminal pytest（287ms，成功）← access_log 最后一条
22:33     knowledge_base.json 写入（mtime）← 关键！
22:33+    用户"怎么样了""1"——无回应
```

## 关键推断：引擎死在哪

`knowledge_base.json` 只由 `tools/v5_memory.py` 的 `_save()` 写。
引擎里唯一在 turn 收尾阶段写它的地方（`core/engine.py:745-767`，
STATE_RESPONDING 分支）：

```python
# self._pending_content 已生成（最终回复文本已存在！）
→ _extract_takeaways()          # 419-447，自带 try/except，不会挂
→ add_entry(entry_type="draft") # 写 knowledge_base.json ← 22:33 它执行了
→ tracker.maybe_propose_skill() # ← 嫌疑 1
→ _format_final_output()        # ← 嫌疑 2
→ _notify("complete")           # ← 嫌疑 3：emit 到 TUI 的通路
→ state = STATE_DONE            # 永远没到
```

**22:33 的写入证明：最终回复已经生成完毕、草稿记忆已经落盘，
线程死在距 complete 事件仅 3 步的地方。**

已排除：
- ❌ LLM 调用挂死——llm_caller 有超时（10s 连接 / 50s 读 × 3 次），
  且 _extract_takeaways 有兜底 try/except
- ❌ 工具执行崩溃——pytest 已成功返回
- ❌ 压缩循环——7-26 已修（compression-loop）

## 三个嫌疑（按可能性排序）

1. **`_notify("complete")` 的 emit 通路**：engine → gateway → Node TUI。
   如果 emit 抛异常或阻塞（连接断、buffer 满），线程死在最后一步。
   TUI 表现完全吻合：工具结果收到了（之前的 emit 是通的），
   complete 没收到。
2. **`tracker.maybe_propose_skill()`**：pattern_tracker.json mtime 22:24
   （9 分钟前），但如果 propose 里有 LLM 调用或交互等待，可能卡住。
   需要读这个方法确认有没有阻塞点。
3. **下一个用户回合的注入链**：如果 turn 其实完成了（TUI 没显示？），
   那"怎么样了"触发的新回合里，injector/proactive/skill 注入链
   某个裸 except 或锁可能卡死。7-27 白天修过一批裸 except
   （fragile-chain-silence），但注入链很长，可能有漏网。

## 重启后 HTTP 400（前次崩溃）——可能是独立第二 bug

崩溃后重启报 400 = 恢复的历史里存在 API 拒绝的结构
（孤儿 tool_calls / 空 content / 压缩残留）。C3 修过孤儿保护，
但那次崩溃发生在修复前的会话上。本次重启后是否 400 待用户确认。
**建议：作为独立 bug 追踪，不和线程死混为一谈。**

## 可观测性缺口（本次调查最大的发现）

**bobo 没有任何持久运行日志。** logging 全走 stdout，
TUI gateway 的 stdout 不接文件，线程异常走默认 excepthook 打印到
看不见的地方。每次崩溃能用的证据只有 access_log（只记工具）
和文件 mtime。这次能定位到 30 行区间已经是运气（knowledge_base
的 mtime 恰好暴露了执行位置）。

## 给 Cloud 的任务建议（两步走，先观测后修）

### Step 1（先做，小改动）：持久运行日志

1. gateway 启动时 `logging.basicConfig` 加 FileHandler
   （`data/logs/bobo_YYYYMMDD.log`，按天滚动，保留 7 天）
2. 装 `threading.excepthook` + `sys.excepthook`：任何线程异常
   完整堆栈写日志
3. `faulthandler.dump_traceback_later(120, repeat=True)` 可选：
   每 2 分钟 dump 一次所有线程堆栈到日志——下次"假死"直接看
   线程卡在哪个调用
4. engine `_step` 的 STATE_RESPONDING 分支：_notify 前后各打一条
   debug 日志（turn id + 阶段名）

### Step 2（日志到位后）：复现抓现行

复现路径已经很明确：长会话 + 多轮工具调用 + execute_terminal
跑 pytest 后继续对话。挂着日志跑，崩一次，堆栈会自己说话。

### 同步排查（不等日志，顺手做）

- 读 `tracker.maybe_propose_skill()`：有没有 LLM 调用/用户交互/
  锁等待——有就是头号嫌疑坐实
- 读 `_notify` → emit 的完整链路：有没有无超时的阻塞写
- 确认本次重启后是否再现 HTTP 400（用户配合）

## 给用户的配合项

1. 重启 bobo 时留意：是否又报 HTTP 400？（决定第二 bug 是否还活着）
2. 下次崩溃**先别重启**，叫 Kimi 或 Cloud——进程活着才能抓堆栈
   （`kill -QUIT` 或 faulthandler 都能 dump）

---

## 补：活进程取证（22:41，用户未重启，进程仍在）

- 两个候选后端（PID 11681 / 8351）主线程均阻塞在 `stdin readline`
  = gateway 主循环正常空闲（stdio RPC 等 TUI 指令），**进程健康**
- 关键缺失：进程只剩 2 线程（主线程 + 系统 workqueue），
  **引擎 worker 线程已消失**——堆栈随死线程一起消失，py-spy 无法考古
- 崩溃剧本坐实：引擎线程在 add_entry（22:33 落盘）与 _notify("complete")
  之间带未捕获异常死去 → complete 永远没发 → Node TUI 卡在等待态、
  后续用户消息不派发 → "bobo 不回复"，但进程和 TUI 都活着
- 三次崩溃同一剧本：线程死、主进程活、TUI 干等
- 结论强化：Step 1（threading.excepthook + 持久日志）是唯一能抓到
  死线程临终堆栈的手段，优先级最高
