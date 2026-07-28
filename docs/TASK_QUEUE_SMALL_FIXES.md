# 排队小票合集（2026-07-28 验收后遗留）

> 来源：e2e 返工验收 + 日志巡检。三张票互相独立，可分别派发。
> 均建议走 L2 级（duo B 验收），不紧急。

---

## 票 A：FakeLLMCaller 加协议严格校验

**背景**：e2e 测试台 `tests/test_engine_e2e.py` 的 FakeLLMCaller 不校验传入 messages 的 tool_calls 配对。`test_real_interrupt_in_executing_phase` 中，tool 结果丢失后 engine 带孤儿 history 调了第二次 LLM——真实 API（OpenAI/Kimi/DeepSeek）在此刻会返回 HTTP 400，但 Fake 静默放行。这复刻了 2026-07-27 崩溃案现场（孤儿 tool_calls → 400），测试台却照不亮它。

**任务**：给 FakeLLMCaller 增加可选的严格模式（建议默认开启）：
- 每次被调用时扫描传入 messages，凡 assistant 消息含 tool_calls，必须存在对应 tool_call_id 的 tool 消息，否则抛异常（模拟 HTTP 400）
- 受此影响的既有测试若依赖"脏 history 继续跑"，显式标注并改走清洗后再调用

**验收**：
1. 新增测试：构造带孤儿 tool_calls 的 messages → Fake 抛 400 类异常
2. 既有 25 条 e2e 测试全绿（必要时调整）
3. pytest 全量绿

---

## 票 B：proactive.py 断链 import

**证据**（bobo.log 反复刷）：
```
core/proactive.py:54  from core.llm_caller import call_llm
ImportError: cannot import name 'call_llm'
```
`core/llm_caller.py` 中不存在 `call_llm`（与 7-27 `_skill_mgr` 断链同型：接口重构后调用点没跟上）。后果：主动建议的语义过滤功能静默失效。

**任务**：
1. 查清 llm_caller 当前真实接口（大概率是 `create_llm_caller` 工厂），改接
2. 给 `_semantic_filter` 加最小回归测试：mock caller，验证过滤路径可走通
3. 日志中该 ImportError 消失

**验收**：上述 3 条 + pytest 全绿。

---

## 票 C：proactive.py track_citation 类型混淆

**证据**：
```
core/proactive.py:202  mem.get("id", "")
AttributeError: 'str' object has no attribute 'get'
```
`track_citation` 遍历的记忆列表里混进了字符串（预期 dict）。疑似某条记忆的存储格式是裸字符串，或加载路径某处返回了 str 列表。

**任务**：
1. 定位混入口：打印/检查记忆列表中 str 元素的来源（存疑：knowledge_base 旧格式遗留 or 某写入路径未包装 dict）
2. 修复根因（推荐）或防御性跳过 + 记 warning（保底）
3. 加回归测试：列表混入 str 时不 crash

**验收**：日志中该 AttributeError 消失 + 回归测试 + pytest 全绿。

---

## 纪律备注（本次事件衍生）

e2e 返工时 bobo 在未收到派单指令的情况下，看到 docs/ 下出现 REWORK 任务单即自行开工。处理结论：
- 任务单文件 ≠ 开工令（默认模式须确认后动手）——已写入 self-hosting 标准
- 未来 auto 模式下此行为为预期能力，届时由显式开关启用
