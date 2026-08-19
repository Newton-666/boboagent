# 票 P0-2：信号日志化双通道（自进化第二票——只记录不动作，两周看质量）

分支 `feat/ticket-p0-2-signal-log`，自最新 main（`16a3a672`）切出。
回滚标签 `rollback/pre-p0-2` 先打再动工。
六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等终审。

---

## 背景（docs/SELF-EVOLVING-PLAN.md P0-2；DISCUSSION 8.5/18/21 节沉淀）

自进化系统 P0 系列第二票。P0-1（记忆六类 + Memory UI）已收编。P0-2 =
**信号日志化双通道**——把"用户偏好信号"与"library 主题频率信号"**只记录、
不动作**地落盘，两周后看信号密度与质量，再决定是否进入 P1 半自动建议流水线。

**为什么先做这个（Hermes 17/18 节论证）**：
- 8.5 的信号判据（guidance 四条）**全是主观推断**，无独立锚点，恰是自举崩溃
  最隐蔽的形态（奖励信号与策略同源 → "自信地学错"且不可察觉）；
- **成本最低的证伪实验**：先纯日志化收集，信号多为误报 → 前提重估；
  信号质量高 → 再做归因 schema。**本轮任何信号都不触发记忆写入/模型变化**。

**信号判据（guidance 四条，DISCUSSION 8.5，给 LLM 的收纳标准）**：
1. 用户说"以后/下次/从今往后" + 期望行为 → **工作流模式信号**；
2. 用户说"不要/别/别用" + 不喜欢行为 → **负强化信号**；
3. 用户重复要求同类事 ≥N 次 → **隐含偏好信号**；
4. 用户明确说"记住/以后都这样" → **强信号**；
   其余不算信号（普通对话不收纳）。

**双通道**：
- **通道 A：对话信号**（8.5 四条）——由 LLM 按 guidance 判定，对话中抽取；
- **通道 B：library 主题频率信号**——确定性代码统计（不靠 LLM）：
  library/ 下各主题笔记的写入频率/时间窗分布，识别高频主题。

## 施工项

### 1. 通道 A：对话信号日志（只记录）

- 在对话回合沉淀路径（living_notes / takeaway 附近）增加信号判定 hook：
  - 用户消息送入 LLM 按 guidance 四条判定（**复用既有 LLM 调用点或新增
    独立小调用，use_tools=False，小 max_tokens**，参考 ENG-1 takeaway 提取
    的既有先例）；
  - 命中信号 → 写结构化日志 `data/logs/signal_log.jsonl`：
    ```
    {"ts": "...", "session_id": "...", "signal_type": "workflow|negative|implicit|strong",
     "user_text": "...", "judgement": "LLM 判定原话", "source": "conversation"}
    ```
  - **零动作**：不写 knowledge_base、不改 memory、不注入任何提示；
  - 失败静默降级（LLM 调用超时/报错 → 跳过本回合，不阻塞对话）；
  - 频控：同一会话内同类信号去重（防一条偏好刷 10 条日志）。

### 2. 通道 B：library 主题频率信号（确定性，代码统计）

- 新脚本/工具 `tools/signal_library_stats.py`（或并入既有工具）：
  - 扫描 `library/` 下各主题 `.md`（**排除 agent开发/ 施工报告目录**——
    那是工程产物不是用户偏好）；
  - 按 frontmatter/文件名统计：主题、近 7/30 天写入次数、更新时间窗；
  - 输出 `data/logs/signal_library_stats.json`（或并入 signal_log.jsonl 的
    source="library" 记录）；
- 纯确定性代码，零 LLM；可手动/定时触发（**不接 cron，先手动**）。

### 3. 观测/展示（最小可用）

- `data/logs/signal_log.jsonl` 提供 `signal.list` RPC 或 CLI 查看命令，
  供两周后人工评估（owner/Hermes 看信号密度与质量）——**UI 面板不做**
  （P1 再定），CLI 够用。

### 4. 回归测试

- `tests/test_signal_log.py`：
  - 构造"以后都用 diff 展示"类用户消息 → 断言写入 signal_log.jsonl 且
    **knowledge_base.json 零变化**（md5 前后一致）；
  - 构造普通对话（无信号）→ 断言不写入；
  - 同类信号去重：同会话重复 → 只 1 条；
  - 通道 B：临时 library 结构 → 断言统计正确、排除 agent开发；
  - 频控/静默降级：mock LLM 失败 → 不阻塞、无日志残留异常。

## 验收标准（终审逐条复跑）

1. 对话中触发 guidance 信号 → signal_log.jsonl 新增结构化记录；
2. **knowledge_base.json / memory 零变化**（只记录不动作的铁律，md5 断言）；
3. 普通对话零误写；
4. 通道 B 统计正确（含 agent开发 排除）；
5. 全量 pytest 零失败（基线 2774 passed / 2 skipped / 1 xpassed + 新用例；
   cost1b 分支名环境失败为既有已知项）；
6. 收工报告落 `library/agent开发/TICKET-P0-2完成报告.md`
   （md5/git 实况/测试原话/信号样例 3 条/通道 B 统计样例）。

## 风险自查点

- **零动作铁律**：本票信号**绝不**触发记忆写入/模型变化/注入——写错一条
  就是自举崩溃入口（Hermes 17 节红线）。测试用 md5 锁死；
- **LLM 判定无独立锚点**（Hermes 18 节）——本票只做日志不做动作，锚点问题
  留给 P1 决策；日志里保留 `judgement` 原话供人工复核误报率；
- **信号去重/频控**：防单条偏好刷屏日志；
- **library 扫描排除**：agent开发/（施工报告）不是用户偏好信号源；
- **living_notes 路径陷阱**：沉淀调用点若用 write_obsidian 会写 Obsidian
  vault——本票日志固定落 `data/logs/`，与 Obsidian 无关（历史教训：报告
  写错路径已 6 次，本票不许踩）。

## 已完成取证（Kimi 开票前核实，施工不必重复）

- 信号判据四条定义：DISCUSSION-SELF-EVOLVING.md 8.5 节（119-126 行）；
- 只记录不动作决策：Hermes 17 节（210 行"先做信号采集纯日志化"）；
- 既有 LLM 小调用先例：ENG-1 takeaway 提取（engine.py:1226-1249，
  use_tools=False + max_tokens=512 + llm.call 事件补写）；
- library 结构：library/ 含多主题 md + agent开发/（施工报告，需排除）；
- 基线 pytest：2774 passed / 2 skipped / 1 xpassed（cost1b 已知项除外）。
