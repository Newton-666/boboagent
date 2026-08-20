# TICKET-LEDGER-400 — L1 自动销账注入破坏工具轮链（COST-7 F2/F3 分支落地）

> 开票：2026-08-20（bobo 施工 TICKET-PROFILE-1 时 14:38/14:55 两次触发 400）
> 分支：`fix/ledger-inject-400`
> 回滚标签：`rollback/pre-400-fix-20260820`

## 根因

engine.py:2143（票 L1 自动销账辅助）在"run_tests 全绿 + 台账有 pending"时：

```python
self.history.append({"role": "system", "content": "💡 检测到测试全绿强完成信号..."})
```

此时 history 尾部是刚 append 的 `tool` 结果，下一条会是 `assistant(tool_calls)`。
**system 消息硬插在工具轮链中间**（assistant(tool_calls)→tool→system→assistant），
DeepSeek thinking 模式要求该结构中间 assistant 带 reasoning_content，而 history
里没有 → HTTP 400。**施工越顺利（测试全绿）越容易触发**——bobo 施工期间反复崩。

## 修法（COST-6 动态块模式）

改为**追加到最后一个 user 消息 content**（用户消息 content 扩展不破坏结构，
模型仍可见建议；无 user 时兜底独立 system，理论不可达）：

- engine.py:2143 区块重写（_suggest_text + reversed(history) 找 user + 追加）
- diff 声明 COST-7 特批标记（engine.py 是受保护文件，授权机制要求）
- 测试授权名单加 COST-7（desk_v4/v4b/tel 三处）

## 测试

- 新增 tests/test_ticket_ledger_400.py（4 用例）：追加到 user / 无 system 插工具轮
  中间 / 无 user 兜底 / 非全绿不注入
- 更新 tests/test_ticket_ledger_1.py::test_green_tests_suggest_done（旧行为断言
  → 新行为：任意消息含建议 + 无独立 system）
- 全量：待最终确认（预期 2813 passed / 7 failed 基线同名含 library_git）

## 验证记录（Hermes 终审）

- 修复后 59/59（ledger_1 + desk 三件套 + 新测试）
- library_git 失败经 stash 对比确认为基线已有（非本次引入）
