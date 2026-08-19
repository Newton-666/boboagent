# 票 COST-7：HTTP 400 "reasoning_content must be passed back" 系统性根治（多因素组合，非打补丁）

分支 `feat/ticket-cost-7-reasoning-root`，自最新 main 切出。
回滚标签 `rollback/pre-cost-7` 先打再动工。
六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等终审。

---

## 背景（owner 2026-08-19 深夜定调：这是最后一张信任票，必须根治）

**现象**：HTTP 400 "reasoning_content must be passed back" 反复出现。
REASONING-ECHO（修回传）、COST-6（修动态块）后**仍复现**——证明前两票都是
**打补丁**，没碰根因。owner 定调：**不允许无限次补丁式修复**；若 COST-7
后仍连锁出问题（折叠/渲染/diff/400），**回溯到自进化前基底**
（snapshot/pre-self-evolving-20260818，已验证存在，双备份）。

**核心认知（owner 教导）**：问题不是"一个原因 → 一个结果"的一一对应，
而是**多因素组合**——几个没有强连接的因素叠加才显现为 400。必须把**所有
因素**列全、逐个处理，缺一不可。

## 400 的完整因素组合（Kimi 排查，全部核实）

400 触发 = 以下因素**同时成立**：

| # | 因素 | 现状 | 状态 |
|---|---|---|---|
| F1 | **模型是 thinking 模式**（deepseek-v4-flash）：服务端记忆每个 assistant 的 reasoning_content **原值**，后续请求必须**逐字节一致回传** | 当前配置 deepseek-v4-flash | 固定因素（不改模型）|
| F2 | **messages 出现"双 user 夹工具轮"**：两个 user 消息之间夹工具轮 → 触发规则 | **COST-2 动态块已修（COST-6）；但引擎还有 5 处 user 注入没修** | ❌ 未修 |
| F3 | **压缩路径丢 thinking**：core/context.py:92 归档字段过滤只留 role/content/tool_calls/tool_call_id/name → **压缩后工具轮 assistant 无 thinking** → echo 补空串 `""` | 空串 vs 服务端记忆原值 = **mismatch？从未验证** | ❌ 未查 |
| F4 | **孤儿清洗补占位**：core/context.py:789 孤儿 assistant tool_calls 补占位 tool；若 assistant 无 thinking → echo 补空串 → 同上 mismatch | 同上 | ❌ 未查 |
| F5 | **工具轮 assistant 的 thinking 采集完整性**：llm_caller 流式收集 reasoning_buf，但**重试/非流式路径**（engine.py:1662）可能拿到空 → thinking 缺失 → echo 补空串 | 需核实 | ❌ 未查 |
| F6 | **触发时机**：长会话 + 多工具轮 + 高频施工同时发生（之前没人连续施工 100+ 轮）| 客观条件 | 触发因素 |

**前两票只修了 F2 的一个分支（动态块），F2 剩 5 处 + F3/F4/F5 完全没碰**。

## 施工项（按因素，全部处理）

### 1. F2：引擎内部 user 注入统一改 system（5 处）

`_append_to_history("user")` 中，**引擎内部提示**全部改 `"role": "system"`：

| 行号 | 内容 | 本质 |
|---|---|---|
| 933 | "轮次过半（N/M）：请合并工具调用..." | 系统进度提醒 |
| 962 | 压缩摘要（_summary）| 系统上下文整理 |
| 1871 | "检测到未完成的承诺，请继续执行..." | 引擎承诺检测 |
| 1923 | 质量回注（_rej）| 引擎质量提示 |
| 1955 / 2022 | "任务台账还有 N 项未完成..." | 引擎台账回注 |

**1746 不动**（用户真实输入 current_user_input）。
改后 messages 从头到尾**只有 1 个真 user** → 双 user 结构不再成立。
同步改测试：tests/test_goal_gate.py:74、test_task_ledger.py:242、
test_ticket_core_r1.py:71-96（断言 user → 查 system 或按 role 判断）。

### 2. F3：压缩路径保留 thinking（关键，前票漏掉的组合）

core/context.py:92 归档字段过滤**加入 thinking 保留**：
```python
{k: v for k, v in m.items() if k in ("role", "content", "tool_calls",
                                      "tool_call_id", "name", "thinking")}
```
使压缩后的工具轮 assistant **仍带 thinking** → echo 补**原值**而非空串。
需确认：压缩后重建的消息（L1/L2 摘要）若是**新构造的 assistant**（无原始
thinking），则**无法回传原值**——此类情况如何处理（见施工项 5 的验证）。

### 3. F4：孤儿清洗占位不产生"无 thinking 的工具轮 assistant"

core/context.py clean_orphan_tool_calls：
- 孤儿 assistant tool_calls **若无 thinking**（中断丢失），补占位 tool 时
  **同时给 assistant 补 reasoning_content 占位**（值策略见施工项 5）；
- 目标：**发送出去的 assistant 消息，凡带 tool_calls 必有 reasoning_content
  字段**（值可为原值或空串，策略由验证定案）。

### 4. F5：thinking 采集完整性核实

- 核实重试/非流式路径（engine.py:1662）reasoning 是否可靠；
- 若某轮 thinking 为空但工具轮存在 → 日志留痕 + 发送时按施工项 5 策略兜底；
- 目标：**发送侧不出现"带 tool_calls 但无 reasoning_content"的 assistant**。

### 5. 核心验证实验：空串 vs 原值（定案策略，不能离线猜）

**关键未知**：DeepSeek 服务端对"reasoning_content 空串"vs"原值"是否严格校验。
REASONING-ECHO 报告"空串 ACCEPT"是**离线构造**（服务端无状态记忆），
**不能证明真实会话 OK**。

实验（必做，真实 API）：
- 构造真实长会话：让模型输出 thinking + 工具轮，**后续请求分别回传**
  a) 原值 b) 空串 c) 无字段——对比是否 400；
- 若原值才 OK → 策略 = **尽力保留原值**（F3 修压缩 + F4 修占位），
  空串/无字段场景降级处理（如压缩摘要轮跳过工具轮结构）；
- 若空串也 OK → 策略 = 统一补 reasoning_content（有值用值，无值空串）；
- **实验结论写进报告，策略随结论定案，不许拍脑袋**。

### 6. 回归保障

- 全量 pytest 0 失败（基线 2797 passed / 2 skipped / 1 xpassed；cost1b
  已知项除外）+ 新测试（F2 改 role 后 3 个测试同步 + F3/F4 断言）；
- **缓存命中率复测**：e2e_cost2_probe 改后实跑，≥ 改前（user→system 角色
  变化在 history 内，须确认前缀稳定不塌）；
- **真实长会话冒烟**：连续多轮工具施工（含压缩触发 + 孤儿清洗触发）不 400。

## 验收标准（终审逐条复跑）

1. F2：引擎 5 处 user 注入改 system，messages 无双 user 夹工具轮；
2. F3：压缩后工具轮 assistant 仍带 thinking（或按实验结论处理）；
3. F4：孤儿清洗后 assistant 带 tool_calls 必有 reasoning_content；
4. F5：thinking 采集完整（无"带 tool_calls 但无 thinking"的 assistant 出库）；
5. **实验结论**：空串 vs 原值策略定案（数据支撑，非猜测）；
6. 全量 pytest 0 失败 + 缓存命中率不塌 + 真实长会话不 400；
7. 报告落 `library/agent开发/TICKET-COST-7完成报告.md`
   （md5/git 实况/测试原话/实验数据/缓存对比/长会话冒烟记录）。

## 风险自查点

- **改 role 影响面**：user→system 改的是 history 内容——缓存前缀变化需复测
  （COST-6 已证尾部 system OK，但这是**历史中段**的 role 变化，必须单独复测）；
- **压缩摘要重建**：L1/L2 摘要是新构造消息，原 thinking 不可得——此路径
  按实验结论定案（可能需在摘要 prompt 中保留工具轮标记）；
- **孤儿清洗**：补占位不得引入新 400（占位 assistant 的 reasoning_content
  策略按实验定案）；
- **历史会话恢复**：旧存档中 user 注入已是 user 角色——恢复时是否迁移？
  （若旧注入在长会话恢复后仍触发双 user → 需处理）；
- **测试改动**：3 个测试断言 user → 同步改，不许绕过（L13 纪律）；
- **TEL-8 守卫**：engine.py / context.py 改动需特批登记 COST-7 标记；
- **write_obsidian 陷阱**：报告落 library/agent开发/（已错 10 次的教训）。

## 已完成取证（Kimi 排查结论，施工不必重复）

- F2 清单：grep 确认 5 处 `_append_to_history("user")`（933/962/1871/1923/1955/2022）+ 1746 不动；
- F3：core/context.py:92 字段过滤缺 thinking（已核实源码）；
- F4：core/context.py:789 孤儿清洗补占位（assistant 无 thinking 则 echo 空串）；
- F5：llm_caller 流式收集 reasoning_buf（llm_caller.py:552），重试路径
  engine.py:1662 需核实；
- REASONING-ECHO 报告"空串 ACCEPT"为离线构造，不可作为真实会话证据；
- COST-6 已修动态块（F2 分支 1/6），尾部 system 缓存 99.6% 不塌（22:18 实测）；
- 基线 pytest：2797 passed / 2 skipped / 1 xpassed；真实库 659 条。
