# 票 LN-2：主题笔记 MVP（活体知识库主菜）

> 状态：待开工
> 前置：宪法第十七章 + docs/LIVING_NOTES_DESIGN.md（Q1/Q2 细则）+ LN-1 已入库
> 分支：`feat/living-notes`（从最新 main 新建）

## 目标

收工时（RESPONDING，takeaways 非空才触发）自动把本轮要点写进
`library/<领域>/<主题>.md` 主题笔记，并维护 `library/index.md` 目录。
**MVP 只做追加式记录，绝不改写旧内容**（改写是 LN-3 的活，配 diff 预览）。

## 触发与成本纪律

- 钩子：`core/engine.py` RESPONDING 收工流程，`_extract_takeaways` 之后。
  **takeaways 为空 → 本票零动作**（没值得记的就别建笔记）。
- 全程最多 **1 次额外 LLM 调用**（主题判定+成文合并为一次）。
  闲聊回合零成本（被 takeaway 预筛挡住）。
- 总开关：`BOBO_LIVING_NOTES=off` 环境变量可整体关闭。
- 所有失败静默降级记 WARNING + 事件，**绝不阻塞收工**。

## 新模块 `tools/living_notes.py`

### 1. 主题判定（LLM，一次调用）

输入：本轮 takeaways + 最近一条用户消息 + index.md 现有主题清单。
输出（要求 JSON）：`{"topic": "≤12字主题短语", "domain": "领域", "section": "markdown 正文（1-3条要点，每条≤80字）", "match": "已有主题名 或 null"}`

- 主题命名照 Q2 铁律：人话、≤12 字、禁日期/session 前缀。
- match 判定："这些要点属于已有主题 X 吗"——拿不准必须返回 null
  （误分 > 误并，体检能发现重复，错并毁笔记）。

### 2. 笔记落盘（非破坏性）

- 路径：`library/<domain>/<topic>.md`；文件名净化 `/\:*?"<>|` 及首尾空格。
- **新笔记**：frontmatter（topic/domain/created/last_touched/source_sessions）
  + 首个 `## YYYY-MM-DD 会话` 小节。
- **已有笔记**（match 命中或规范化主题名完全相同）：
  更新 frontmatter 的 last_touched + source_sessions 追加当前 sid，
  **在文末追加** `## YYYY-MM-DD 会话` 小节——旧内容一字不动。
- 每个小节内要点末尾带出处：`（源自会话 {sid}）`。

### 3. index.md 维护

每次落盘后重生成 `library/index.md`：按领域分组列出
`- [[主题]] — 最后更新 YYYY-MM-DD（N 篇会话）`。
幂等全量重写（照 LN-1 先例）。

### 4. 事件埋点

`notes.written`（path/topic/is_new）、`notes.error`（静默降级）。

## 验收金标准（tests/test_living_notes.py，全部 tmpdir 物理检查）

1. **新主题建笔记**：fake LLM 返回新主题 JSON → `library/agent开发/收工闸.md`
   存在，frontmatter 齐全，小节含出处 sid。
2. **同主题追加**：再跑一轮 match 命中 → 同一文件多出第二个日期小节，
   **第一个小节内容逐字节不变**；last_touched 更新。
3. **零价值不建**：takeaways 为空 → library 目录无新文件、零 LLM 调用。
4. **命名违规矫正**：LLM 返回带日期的主题名 → 落盘文件名已净化，
   不含 `/` `:` 等字符。
5. **误判保守**：LLM 返回 match=null → 建新笔记，不动任何已有笔记。
6. **index 正确**：两次落盘后 index.md 含两个主题条目，按领域分组。
7. **开关**：`BOBO_LIVING_NOTES=off` 时全流程零动作。
8. **降级**：library 目录只读 → 收工正常完成，仅 WARNING + notes.error。
9. 全量 pytest 通过，零回归。

## 边界

- **不做**：旧小节改写、diff 预览、蒸馏晋升、反向注入（LN-3/4）。
- 不改 takeaways 提取逻辑本身。
- engine.py 只加钩子调用（try/except 包裹），逻辑全在 living_notes.py。

## 纪律

- 开工前 `git branch --show-current` 确认在 `feat/living-notes`。
- 完成后五查汇报（含 git status 原文 + git branch --show-current 原文），
  ⛔️ 禁止 merge、禁止 push，等 Kimi 终审。
- 改了 core/engine.py → 五查第 6 项填"是，需重启生效"。
