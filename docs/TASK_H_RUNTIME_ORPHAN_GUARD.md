# 票 H：运行时孤儿防线（HTTP 400 完全体修复） ✅ 已完成（merge 05f6d01，2026-07-28）

> 级别：L3（duo B 验收 + Kimi 终审）— 均已通过
> 分支：feat/runtime-orphan-guard（已合并 main → 已删除本地分支）
> 关联案：HTTP 400 崩溃案（2026-07-27 磁盘中毒版已打疫苗；2026-07-28 13:43 内存中毒版实锤复发）

## 背景

既有疫苗（`core/context.py clean_orphan_tool_calls` + session_manager 加载清洗）只覆盖**磁盘加载路径**。2026-07-28 13:43 实证：活着的会话在运行中产生孤儿 tool_call（某工具结果丢失）后，**每一次后续 API 调用都 400**，会话永久哑掉——只能靠重启丢弃。防线缺"运行时"这一半。

## 任务（双层防线）

### 第一层：发送前清洗（主防线）

- 在 engine 每次调用 LLM 前（`_call_llm` 或等效入口），对将要发送的 messages 跑 `clean_orphan_tool_calls`
- 清洗发生在**发送副本上**：不篡改 engine.history 本体（历史保持原样可审计），只保证发出的请求合法
- 若发生清洗，记 WARNING 日志（orphan 数量、tool_call_id 列表）——这是重要的事故信号，不许静默
- 性能：O(n) 纯 CPU 扫描，history 几百条级别开销可忽略；如担心可只在"自上次清洗后有新 tool 消息"时跑（可选优化，非必须）

### 第二层：400 捕获重试（兜底）

- 捕获 LLM 调用返回的 HTTP 400，且错误体含 tool_call 配对类关键词（如 "tool_call_id"、"messages with role 'tool' must be a response to a preceding message" 等，按 DeepSeek/OpenAI 实际错误文本）
- 命中时：对 messages 做清洗 → **原样重试一次** → 成功则记 WARNING 继续；仍 400 则按现有错误路径上抛
- 非配对类 400（如参数错误）不重试，直接上抛

## 禁止项

- 不许修改 API 错误的上抛语义（除第二层定义的重试外）
- 不许在清洗时丢弃 assistant 消息本体（占位补法，与磁盘疫苗同策略）
- 不许静默清洗——必须留 WARNING 日志

## 验收

1. 新增测试：①构造运行中带孤儿的 history → 调用 _call_llm（mock caller 断言收到的 messages 已配对）②engine.history 本体未被篡改 ③mock caller 第一次抛配对类 400 → 清洗重试成功 ④非配对 400 不重试 ⑤清洗时 WARNING 日志已记录
2. e2e 测试台既有 25 测试不回归
3. pytest 全量绿
4. 五查汇报 + 等 Kimi 终审，禁止 merge
