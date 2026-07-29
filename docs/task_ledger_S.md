# 票 S 任务台账 — extract_takeaways 空转治理

**分支**: feat/takeaway-gate
**创建**: 2026-07-29
**状态**: ✅ 完成

## 检查清单

- [x] 建分支 feat/takeaway-gate
- [x] 建台账
- [x] 读 engine.py — `_extract_takeaways()` @ L467, RESPONDING 调用 @ L1001
- [x] 读 event_bus 事件写入模式 — `event_bus.write("event.type", data)`
- [x] 实现 `_takeaway_worthy()` 预筛函数 — 纯本地零 LLM 成本
- [x] 修改 `_extract_takeaways()` 入口 — 加预筛闸门
- [x] 可观测：`takeaway.skipped` / `takeaway.extracted` 事件
- [x] 总开关：`BOBO_TAKEAWAYS=off`
- [x] 写测试文件 — `tests/test_takeaway_gate.py` (9 tests)
- [x] 跑全量测试 — 1045 passed, 0 failed

## 修改文件

| 文件 | 改动 |
|------|------|
| `core/engine.py` | + 模块级正则 `_TAKEAWAY_VALUE_KEYWORDS`, `_TAKEAWAY_CONFIRM_PATTERN` |
| | + `Engine._takeaway_worthy()` 静态方法（放行信号优先，跳过条件其次） |
| | + `_extract_takeaways()` 入口预筛闸门 |
| | + `BOBO_TAKEAWAYS=off` 环境变量禁用 |
| | + `event_bus.write("takeaway.skipped")` / `"takeaway.extracted"` 事件 |
| `tests/test_takeaway_gate.py` | 新增测试文件，9 test cases |

## 验收金标准

| 场景 | 预期 call_count | 实际 |
|------|----------------|------|
| 闲聊"谢谢" | 1 | ✅ 1 |
| 确认"好的" | 1 | ✅ 1 |
| 短问答无价值 | 1 | ✅ 1 |
| 含"决定"关键词 | 2 | ✅ 2 |
| 含"记住"关键词 | 2 | ✅ 2 |
| 长内容(>100字) | 2 | ✅ 2 |
| BOBO_TAKEAWAYS=off | 1 | ✅ 1 |
