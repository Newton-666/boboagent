# 票 REASONING-ECHO：DeepSeek thinking 模式 reasoning_content 回传修复（施工阻塞型 bug）

分支 `feat/ticket-reasoning-echo`，自最新 main（`4dcf5d15`）切出。
回滚标签 `rollback/pre-reasoning-echo` 先打再动工。
六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等终审。

---

## 背景（2026-08-19 17:23 P0-1 施工实弹事故 + Kimi 排查定案，链路见 TICKET-P0-1.md「施工阻塞记录」）

bobo 施工 P0-1 时一次多轮工具调用被 DeepSeek API 拒绝：

```
HTTP 400 {"error":{"message":"The reasoning_content in the thinking mode must be passed back to the API."}}
```

引擎走 error→responding→done 收尾，该轮施工中断。

**根因链（三环节，断在第 2 个）**：
1. **收集 ✅**：`core/llm_caller.py:552` 从流式 delta 提取 `reasoning_content` 存
   `result["reasoning"]`（票 P 实现）；
2. **落盘 ❌**：`core/engine.py:1646` 存成 `msg["thinking"] = thinking`
   （字段名是 GUI-F8 折叠框的内部名，不是 DeepSeek 认识的 `reasoning_content`）；
3. **回传 ❌**：`core/injector.py:399` `messages = [system] + engine.history`
   原样发送——**全代码库发送侧 0 处把 thinking 转回 reasoning_content**。

**触发条件（官方规则，非"任何多轮都触发"）**：
DeepSeek [Thinking Mode 文档](https://api-docs.deepseek.com/guides/thinking_mode/)：
**两个 user 消息之间**若模型执行过工具调用，中间 assistant 的 `reasoning_content`
必须参与上下文拼接并在后续所有轮次回传，否则 400。
- bobo 平时 history 只有开头一个 user 消息，工具轮全在其后 → 不构成
  "user…工具轮…user" 结构 → 一直正常（**间歇性原因**）；
- 触发场景：GATE ledger re-injection（engine.py:1965 append user）、承诺检测
  回注（1814/1866/1898）、COST-2 动态块写回 history（injector.py:760 注释明确
  "messages 内 user dict 与 engine.history 共享引用 → 附加同时写回 history"）
  ——任何让 messages 出现第二个 user 的结构都会触发 400。

**事件链取证（events.jsonl 17:23:45，P0-1 施工时）**：
205 条消息成功调用（13.97s，返回工具调用）→ 编辑冲突检测（"retry after
verification"）→ 重试调用 msg_count=108（重试前 `_truncate_history`/压缩把
history 从 200+ 压到 104 条 + 4 注入 = 108 messages）→ 400 bad_request
（226ms 秒拒）→ error→responding→done。

## 施工项

### 1. 发送侧回传（核心，方案 B——不动 history/存档）

`core/injector.py` 的 `build_messages` **返回前**（`clean_orphan_tool_calls`
之后、return 之前），对**发送副本**中的每条 assistant 消息：

```python
# 若该消息带 thinking（引擎落盘的 reasoning），则同步为 DeepSeek 认识的字段
if m.get("role") == "assistant" and m.get("thinking"):
    m["reasoning_content"] = m["thinking"]
```

约束：
- **只改发送副本**，绝不 mutate engine.history 里的原 dict（GUI-F8 读
  `thinking` 折叠框不受影响；存档/恢复格式不变）；
- 只对 `thinking` 非空的 assistant 消息补 `reasoning_content`；无 thinking 的
  （如编辑冲突注入的纯文本 assistant）不补——官方规则只在工具调用轮要求；
- 顺序：必须放在孤儿清洗（`clean_orphan_tool_calls`）之后，且注意清洗可能
  返回新 list——在最终发送的副本上补字段。

### 2. 压缩后路径覆盖

压缩（`core/context.py _compress_history`）生成的摘要 assistant 消息若带
tool_calls 结构，同样需要补 `reasoning_content`（摘要消息本身无 thinking →
回传空字符串也符合要求？——**待施工时验证**：DeepSeek 是否接受
`reasoning_content: ""`，若接受则对 tool_calls 轮统一补空串，若拒绝则跳过）。
实弹验证后定案，测试同步。

### 3. 回归测试

新增/扩展测试（`tests/test_reasoning_echo.py` 或并入既有 engine 测试）：
- 构造 history：`user → assistant(tool_calls, thinking=X) → tool → user`
  （两个 user 之间夹工具轮，触发结构）；
- 断言 `build_messages` 输出副本中该 assistant 消息带
  `reasoning_content == X`；
- 断言 engine.history 原 dict **未被污染**（仍只有 `thinking`，无
  `reasoning_content`）；
- 断言无 thinking 的 assistant（纯文本）不补字段；
- 断言孤儿清洗后路径同样补字段（若清洗返回新 list）。

## 验收标准（终审逐条复跑）

1. `build_messages` 发送副本：带 `thinking` 的 assistant 消息同时带
   `reasoning_content`，值与 thinking 相同；
2. engine.history / 存档 messages 无 `reasoning_content` 字段（GUI-F8 不受影响）；
3. 构造"两个 user 之间夹工具轮"的 history 后，调用 `_call_llm` 不再 400
   （mock API 断言请求体中 assistant 消息带 reasoning_content）；
4. 全量 pytest 零失败（基线 2769 passed / 2 skipped / 1 xpassed，cost1b
   分支名环境失败为既有已知项）；
5. 实弹（owner 触发或 bobo 施工）多轮工具调用不再报
   "reasoning_content must be passed back"。

## 风险自查点

- **只动发送副本**：injector 的 messages 内层 dict 与 engine.history 共享引用
  （injector.py:760 注释明确）——补字段必须在副本上做，或补完即丢弃，
  严禁写回 history（否则存档/恢复带 reasoning_content，GUI-F8 折叠框读取
  路径要复查）；
- **压缩路径**：压缩摘要消息结构待实弹验证（空串 vs 跳过），不许拍脑袋；
- **其他调用点**：engine.py:1232（takeaway 提取）/1340（living_notes）直接调
  `llm_caller` 的小 prompt 不走 build_messages——确认它们不需要补
  （use_tools=False 单轮，无工具轮结构，应天然不触发）；
- **max_tokens/缓存**：补字段只增加少量字节，不影响 COST-2/3 前缀缓存
  （字段加在历史 assistant 消息上，前缀仍逐字节稳定——收工时看 llm.usage
  的 prompt_cache_hit_tokens 确认命中率不塌）。

## 已完成取证（Kimi 排查结论，施工不必重复）

- 收集侧：llm_caller.py:552 `_rc = _dl.get("reasoning_content")` ✅
- 落盘侧：engine.py:1645-1646 `msg["thinking"] = thinking` ❌（GUI-F8 用途）
- 回传侧：injector.py:399 `[system] + engine.history` 原样 ❌
- 官方规则：api-docs.deepseek.com/guides/thinking_mode/（两个 user 之间夹
  工具轮必须回传）
- 相似修复先例（业界同款 400）：langchain #37713 / codex #24500 / opencode
  #24104（都是"assistant 消息带 tool_calls 但缺 reasoning_content"）
