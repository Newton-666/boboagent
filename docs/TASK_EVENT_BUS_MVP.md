# TASK：事件总线 MVP（Event Bus Phase 1）

> 级别：L3（duo B 验收 + Kimi 终审）
> 分支：feat/event-bus-mvp（从 main 新建）
> 来源：开发手册第十二章观测哲学 Phase 1；2026-07-28 13:43 HTTP 400 复发时"哪个工具下的毒抓不到"的破案盲区实锤开工令
> 定位：**bobo 的第二双眼睛。只读观测，零行为变更——agent 不知道自己被看。**

## 目标

新建 `core/event_bus.py`：engine 关键动作以**结构化事件**追加写入 JSONL 账本。本票只做"产生事件 + 落盘"，不做消费（无 /audit、无仪表、无闸联动——那是 Phase 2-4，另行立票）。

## 三类事件（MVP 范围，不得多报）

| 事件 | 触发点 | 字段（摘要默认，全文按需） |
|---|---|---|
| `llm.call` | _call_llm 调用前后 | ts、session_id、messages 条数、是否有 tool_calls、模型、耗时 ms、usage token 三字段、error_type（如有）、**孤儿清洗标记**（票 H WARNING 联动：inserted/removed 数） |
| `tool.exec` | tool_runner 每次工具执行 | ts、session_id、tool_call_id、工具名、参数摘要（≤200 字符，超长截断）、结果摘要（≤200 字符）、耗时 ms、是否硬拒绝/取消、副作用路径（写文件类工具的目标路径） |
| `state.change` | engine 状态机每次转换 | ts、session_id、from_state、to_state、触发原因（如有） |

**摘要默认、全文按需**：不记录 messages 全文、工具参数/结果全文——只记摘要和指针（session 文件路径可事后取全文）。单条事件 ≤ 500 字符。

## 硬性设计要求

1. **静默降级铁律**：事件写入失败（磁盘满/权限/路径错）时**绝不允许**抛出异常影响主流程——catch 一切，记一次 logger.debug 后放弃该条。摄像头坏了绝不能让 agent 失明
2. **追加写 JSONL**：`data/logs/events.jsonl`，一行一事件，无锁单写者（engine 单线程写入；多线程场景用 threading.Lock 保底）
3. **零行为变更**：不修改任何返回值、状态转换、工具执行结果；接入点只允许"读取现场数据"，不允许"改变现场数据"
4. **体积控制**：文件超过 10MB 自动轮转（沿用 bobo.log 的 TimedRotating 思路或简单 size 轮转，保留 3 代）
5. **会话标识**：session_id 从 engine 现有上下文取，保证事后能按会话检索

## 边界（禁止项）

- 禁止消费事件（不做查询命令/仪表/闸联动）
- 禁止记录 LLM 请求/响应全文、工具参数全文（摘要 + 指针原则）
- 禁止新增第三方依赖
- 禁止在事件里写 API Key、文件内容等敏感数据
- 禁止修改 engine/tool_runner 既有逻辑行为（纯增量接入）

## 验收标准

1. **铁证测试**：构造 engine 跑一轮含工具调用的对话（可用 e2e 台 FakeLLMCaller）→ events.jsonl 中存在 llm.call / tool.exec / state.change 三类事件，字段齐全
2. **静默降级测试**：把 events.jsonl 路径指向只读目录/不存在盘符 → engine 正常运行，pytest 不炸，无异常上抛
3. **零行为变更测试**：e2e 测试台 25 条 + pytest 全量不修改即全绿（行为变更必然打破既有测试）
4. **体积测试**：单条事件 ≤ 500 字符；轮转逻辑有单测
5. **孤儿联动**：票 H 投毒场景复现（发送副本清洗触发）→ llm.call 事件中含 orphan 清洗标记
6. pytest 全绿 + 五查汇报 + feat 分支 + 禁止 merge（等 Kimi 终审）

## 离场标准（手册第十二章纪律）

上线后：bobo 行为零变化 + pytest 全绿 + 活体冒烟五联征照过。
