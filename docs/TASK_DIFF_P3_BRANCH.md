# 任务：diff 三件套 — 分支内化 + obsidian/notion 覆盖 + 命令快照 diff

前置：`docs/TASK_DIFF_DISPLAY.md`（P1）、`docs/TASK_DIFF_DISPLAY_P2.md`（P2）已完成验收。
inline diff 通道（`<<<INLINE_DIFF>>>` → `engine_adapter` → `tool.complete.inline_diff`）
与 Claude 风格渲染（gutter/全宽色带/深色）均已上线，本任务在其上扩展。

## ①【暂缓】diff 从独立段落移入工具调用分支（前端为主）

> 2026-07-26 决策：优先级降级，现有独立段落可用，暂缓。

### 现状

`turnController.ts:476 pushInlineDiffSegment` 把 diff 作为**独立 transcript 段落**
插入对话流。工具一多，游离的 diff 段落看不出归属。

### 目标（用户明确拍板的架构）

diff 住进工具调用分支的详细信息里，与 Result 并列：

```
▾ Tool calls (1)
  └─ ● Edit File("appLayout.tsx") (+2 −1) (0.3s)   ← 折叠态也带改动计数
     └─ Result: 已替换 ...
     └─ ⎿ diff（gutter + 全宽色带，复用 P2 渲染）
```

实现要点：
- `tool.complete.inline_diff` 的载荷改走 trail 的 DetailRow 通道
  （`thinking.tsx` 的工具分支详细信息机制），不再走 `pushInlineDiffSegment`。
- 分支标题行（工具名后）显示 `(+N −N)` 计数，从 diff 文本统计。
- diff 本体的渲染**必须复用** P2 的 Claude 风格渲染（gutter/符号列/全宽色带/
  深色/空行深档），不要另起炉灶——考虑把该渲染抽成共享组件。
- 折叠/展开行为遵守现有 `/details` 机制，不另搞一套。
- 连续重复 diff 的去重逻辑（turnController 现有）保留或等价实现。

## ② obsidian / notion 写工具接入 diff（纯后端，每工具十几行）

以下工具的**写操作**全部走 `<<<INLINE_DIFF>>>` 通道（与 file_operation 相同的
"写前读旧内容 → difflib → 分隔块"做法，可抽共享函数）：

- `append_obsidian`（追加 → 纯 + 行）
- `write_obsidian` / `create_obsidian`（覆盖/新建）
- `batch_copy_notes`、`batch_move_notes` 等批量写（逐文件 diff 或汇总，取实现方便者，
  但每个被修改的文件至少要出现在计数里）
- notion 写操作（`notion_append`、`notion_create_page`）：notion 是块结构，
  若无法对纯文本做行级 diff，则显示"新增 N 块"级别的摘要 diff，不要硬凑行 diff。

读操作（read/search/list）一律不加。

## ③【砍掉】code_execution / execute_terminal 快照 diff（后端，需仔细设计）

> 2026-07-26 决策：复杂度最高、覆盖场景低频、有误报风险，明确不做。

### 原理

工具自身不知道会改哪些文件 → 执行前从命令文本中提取文件路径，
对存在的文本文件做**内存快照**；执行后对比，有变化则生成 diff 进分支。

### 快照生命周期（用户拍板的硬性要求）

- 快照只存活于单次工具调用：执行前建立 → 执行后算 diff →
  `try/finally` 立即销毁（命令报错/异常也必须清理，禁止残留）。
- 只在内存，不落盘（与 edit_file 的 trash 恢复备份是两回事）。
- 护栏：只快照命令文本中出现、真实存在、可读的文本文件；
  单文件 >1MB 或二进制跳过；快照总量设上限（如 8MB）。

### 兜底

路径提取未命中但命令确实改了文件时（执行后工作目录有新 mtime 文件），
分支里至少显示一行变更清单：`⚠ 本次命令修改了 N 个文件: a.py, b.html ...`
（无逐行 diff）。扫描范围与耗时要设限（只扫命令 cwd，跳过 node_modules/.git 等）。

### 明确不做

- 不做全盘文件系统监控。
- 不保证 100% 捕获——快照 diff 是 best-effort，漏报可接受，误报不可接受。

## 验收标准

1. edit_file / file_operation 的 diff 出现在**工具分支内**（不再是对话流独立段落），
   折叠态分支标题带 `(+N −N)`。
2. append_obsidian 修改笔记后，分支内显示纯绿追加 diff。
3. execute_terminal 执行一条直接修改某文件的命令（如 `sed -i` 或 `python -c` 写文件），
   分支内显示该文件的 diff；执行一条不碰文件的命令，无 diff 无变更清单。
4. 快照清理测试：命令中途报错，断言快照被清理（测试层面证明 finally 生效）。
5. 渲染回归：分支内 diff 的 gutter/全宽色带/深色与 P2 截图验收一致。
6. pty 端到端：覆盖场景 1、2、3。
7. 完成后同步 `~/.bobo`（tools/ + core/ + static），并确认 `.venv` 是否需要。
