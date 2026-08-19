# 票 P0-1：记忆分类 + Memory 模块 UI（自进化系统第一票，snapshot/pre-self-evolving-20260818 后）

分支 `feat/ticket-p0-1-memory-class`，自最新 main（`25cc26af`，快照后）切出。
回滚标签 `rollback/pre-p0-1` 先打再动工。
六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等终审。

---

## 背景（docs/SELF-EVOLVING-PLAN.md P0-1；21 节讨论沉淀）

自进化系统施工开始（快照 snapshot/pre-self-evolving-20260818 已打）。第一票 =
记忆五类分类落地 + Memory 模块 UI。**独立价值**（Hermes 终评：解决现有 656 条
失控 + 空分类，不依赖自进化）。

**现状取证**（开票前已完成）：
- `data/knowledge_base.json` 656 条，条目结构 `{id, text, type, tags, folder,
  timestamp, signal_score, last_time_decay}`——**type 字段存在但大量为默认
  "knowledge"（空分类）**；
- v5_memory 有 entry_type 参数（压缩沉淀用 KEY_DECISION/USER_PREF/FACT，
  core/context.py:662-674），但未规范化为分类体系；
- `source_sessions` 验证通过（living_notes frontmatter "由系统维护"，tools/
  living_notes.py:70/86/116）——记忆反查来源会话可行。

**D1 决策（定案）**：**含用户目标类（GOAL）**——采纳 Hermes 21.2 论证
（目标≠画像（时变 vs 恒定）、≠事实（未来 vs 过去）；没有目标类的用户模型是
"没有方向感的画像"）。

## 施工项

### 1. 记忆六类分类（v5_memory 规范化）

- entry_type 枚举规范化为六类（替代现状默认 "knowledge"）：
  - `USER_PREF` 用户画像（偏好/习惯/沟通方式）
  - `RULES` 行为约束（要求 + 不让做）——**最高权重，不轻易淘汰**
  - `FACT` 事实/决策（含 KEY_DECISION 并入）
  - `ACHIEVEMENT` 成果（做过什么，存指针）
  - `LESSON` 经验/教训（成败模式）
  - `GOAL` 用户目标/优先级（用户当前在追求什么）
- `add_entry` 校验 entry_type ∈ 六类（未知 type 落 USER_PREF 或拒绝——以现有
  调用点兼容为准）；压缩沉淀（core/context.py:662）映射到新枚举。

### 2. 656 条历史迁移

- **确定性启发式归类**（代码规则，不用 LLM）：按文本关键词/现有 type/tags
  映射到六类（如含"要求/必须/不要/禁止" → RULES；含"偏好/喜欢/习惯" → USER_PREF；
  含"完成/实现/交付" → ACHIEVEMENT；含"教训/坑/原因" → LESSON；现有
  KEY_DECISION/FACT → FACT）；
- **人工抽查 10%**（终审执行：抽 66 条核对归类合理性）；
- 迁移不改条目内容（只改 type 字段），signal_score/时间戳保留。

### 3. 指针可达性校验机制

- 记忆条目引用 library/Obsidian 的指针（如 ACHIEVEMENT → library 笔记路径）：
  新增校验（定期或触发时检查路径存在），**失效 → 降权/标记**（对齐 Hermes
  21.4-②"引用指针悬空"）；本票先实现校验机制 + 现有含路径的条目跑一次。

### 4. Memory 模块 UI（侧栏，diff 增删 + token 统计 + 手动编辑）

- 侧栏结构：`[New chat][Search][Messages][Memory]`（纵向，Messages 下加
  Memory——22 节设计）；
- Memory 界面：
  - 记忆列表按六类分组展示（text 截断 + type 标签 + signal_score 弱字）；
  - **diff 显示增删**：新增绿 / 移除红（复用现有 diffBlock 组件，owner 对
    diff 情有独钟）；
  - **总 token 统计**：记忆库当前用量 / 预算上限（估算，tiktoken 或字符折算）；
  - **手动编辑**：用户可删除条目（→ 走负面淘汰通道降权信号源，P0-5 衔接）
    / 改 type（分类迁移的用户手动入口）；
- 数据源：新增只读 RPC `memory.list`（返回六类分组 + 统计），删除走
  `memory.delete`（本票唯一授权的新 RPC，对齐 session.set_request 先例）。

## 禁止项

- 不改记忆注入逻辑（format_memory_by_signal 语义不变，只加分类维度）；
- 不改 signal_score/decay 算法（P0-5 另票）；
- 不动 library/Obsidian 内容（只读引用）；
- 后端除 memory.list/memory.delete 两个 RPC + v5_memory 枚举外零改动；
- 桌面端 CSS 零新增色值（复用现有 diff/列表视觉）。

## 施工阻塞记录：DeepSeek thinking 模式 400（2026-08-19 17:23 排查定案）

**现象**：bobo 施工中途一次 LLM 调用返回
`HTTP 400 {"error":{"message":"The reasoning_content in the thinking mode must be passed back to the API."}}`，
引擎走 error→responding→done 收尾（该轮未完成）。

**根因链（Kimi 独立排查 + Hermes 结论交叉确认）**：
1. **收集侧 ✅**：`core/llm_caller.py:552` 从流式 delta 提取 `reasoning_content`
   存 `result["reasoning"]`（票 P）；
2. **落盘侧 ❌**：`core/engine.py:1646` 存成 `msg["thinking"] = thinking`
   （为 GUI-F8 折叠框设计，字段名不是 DeepSeek 认识的 `reasoning_content`）；
3. **回传侧 ❌**：`core/injector.py:399` `messages = [system] + engine.history`
   原样发送——**全代码库发送侧 0 处把 thinking 转回 reasoning_content**。

**触发条件（官方规则，非"任何多轮都触发"）**：
DeepSeek [Thinking Mode 文档](https://api-docs.deepseek.com/guides/thinking_mode/)：
**两个 user 消息之间**若模型执行过工具调用，中间 assistant 的 `reasoning_content`
必须参与上下文拼接并在后续所有轮次回传，否则 400。
- bobo 平时 history 只有开头一个 user 消息，工具轮全在其后 → 不构成
  "user…工具轮…user" 结构 → 一直正常（间歇性原因）；
- 本次 messages 出现第二个 user 消息（GATE ledger re-injection / 承诺检测回注 /
  COST-2 动态块写回 history——injector.py:760 注释明确"messages 内 user dict 与
  engine.history 共享引用 → 附加同时写回 history"）→ 触发结构成立 → 400。

**事件链取证（events.jsonl 17:23:45）**：205 条消息成功调用（13.97s，返回工具
调用）→ 编辑冲突检测（"retry after verification"）→ 重试调用 msg_count=108
（压缩/截断后 history 104 条 + 4 注入）→ 400 bad_request（226ms）→
error→responding→done。msg_count 205→108 骤降 = 重试前 `_truncate_history`/
压缩改变了消息结构。

**修复方向（未实施，等 owner 拍板）**：
- 方案 B（推荐）：`injector.build_messages` 返回前，对发送副本中 assistant 消息
  把 `thinking` 复制/改名为 `reasoning_content`（不动 history/存档，GUI-F8 不受影响）；
  需覆盖压缩后路径（压缩摘要消息可能带 tool_calls 结构）；
- 方案 A（2 行）：engine.py:1646 落盘时同时写 `msg["reasoning_content"]=thinking`；
  代价：存档 history 落盘新字段，压缩路径摘要消息无 thinking → 覆盖不全；
- 需补回归测试：构造"两个 user 之间夹工具轮"的 history，断言发送副本带
  `reasoning_content`。

**影响面**：仅 thinking 模式 + 多轮工具调用场景；单轮问答不触发。P0-1 施工
被卡一轮后 bobo 重试继续完成（未 commit），本记录留存排查链路供修复票使用。

---

## 验收标准（终审逐条复跑）

1. 专项：
   - entry_type 六类枚举断言（add_entry 校验）；
   - 迁移启发式：656 条全部有 type（非默认），抽样断言规则正确性；
   - memory.list 返回六类分组 + token 统计；memory.delete 删除 + 负面通道
     触发（降权信号源——若 P0-5 未定义则先记审计日志）；
   - 指针校验：失效路径被标记；
   - UI：Memory 面板渲染、diff 增删显示（jsdom/既有先例）。
2. 全量 pytest 零失败（基线 2754 passed / 2 skipped / 1 xpassed）。
3. 实弹（owner 桌面端）：
   a. 侧栏出现 Memory 入口 → 点开看到六类分组记忆 + token 统计；
   b. 新增一条记忆（对话里说"以后用中文"）→ Memory 面板 diff 显示新增
      （绿色）；删除一条 → 红色移除；
   c. 手动删除一条记忆 → 生效（下次注入不含它）；
   d. 修改一条记忆 type → 重新分组。
4. 收工报告落 `library/agent开发/TICKET-P0-1完成报告.md`
   （md5/git 实况/测试原话/迁移抽样结果/实弹截图）。

## 风险自查点

- 迁移启发式**不许用 LLM**（Hermes 21.4-①：确定性过滤前置，LLM 只在过滤后
  归类）——纯代码规则；
- memory.delete 的"降权信号源"：P0-5 未定前**先记审计日志**（不实现降权，
  避免半成品），票内注明衔接；
- Memory UI 的 token 统计：先字符/tiktoken 估算即可（精确预算 P2-3 再定）；
- entry_type 兼容：检查所有 add_entry 调用点（save_memory/压缩沉淀/engine
  draft），未知 type 的处理不许破坏既有写入。
