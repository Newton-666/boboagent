# 任务：inline diff 返工 P2 — file_operation 覆盖 + 版面降噪

前置：`docs/TASK_DIFF_DISPLAY.md` 已完成并验收（edit_file 的 inline diff 已上线）。
本次两项都是纯后端小改，**不改 TUI、不改 engine_adapter**（提取逻辑原样复用）。

## A. file_operation 也生成 inline diff

### 现状问题

diff 目前只挂在 `edit_file` 上。但 bobo 写网页/写文档/建文件的主力工具是
`file_operation`（整文件写入、追加、新建），这类任务一次 diff 都不触发，
功能覆盖率很低（实测：用户让 bobo 改网页，3 次调用全是 file_operation，0 次 diff）。

### 方案（`tools/file_operation.py`）

写入前读取旧文件内容，写入后用 `difflib.unified_diff` 算 diff，
以与 edit_file 完全相同的 `<<<INLINE_DIFF>>>...<<<END_INLINE_DIFF>>>`
分隔块附加到返回文本尾部（`core/engine_adapter.py` 的提取逻辑无需任何改动）：

| 场景 | diff 内容 |
|---|---|
| 覆盖已有文件 | 旧内容 vs 新内容（正常红绿对照） |
| 追加 | 追加部分（纯 `+` 行，全绿） |
| 新建文件 | 对空 diff（纯 `+` 行，全绿） |

注意：
- 与 edit_file 相同的截断规则（>40 行保留首尾 hunk + 省略提示）。
- 旧内容读取失败（文件不存在以外的 IO 错误）时静默跳过 diff，不影响主流程。
- 二选一即可，不要给 file_operation 的**读取/列目录**等非写操作加 diff。

## B. diff 版面降噪（edit_file 与 file_operation 统一生效）

### 现状问题

当前 inline diff 是 git 原文风格，对比 Claude Code 的版面有三处噪音：

```
⎿  +1 −1
--- /Users/.../hello.txt        ← 碍眼，且会被渲染器误染成红色"删除行"
+++ /Users/.../hello.txt        ← 同上，误染成绿色"新增行"
@@ -1,3 +1,3 @@
 alpha
-BRAVO
+Bravo2
```

Claude 风格（目标观感）：

```
⎿  +1 −1
@@ -1,3 +1,3 @@
 alpha
-BRAVO
+Bravo2
```

### 方案

生成 diff 时**丢弃 `---`/`+++` 两行**（`difflib.unified_diff` 输出的前两行），
保留 `@@` hunk 头。

约束（已核实，必须遵守）：
- `ui-tui/src/components/markdown.tsx:772-776` 的 diff 渲染靠**行首字符**着色
  （`+`→绿、`-`→红、`@@`→muted、空格→dim）。所以：
  - 不要给行加行号前缀（会把 `+`/`-` 挤出行首，颜色全灭）；
  - `---`/`+++` 头必须删——它们以 `-`/`+` 开头，现在被错误染色。
- 想要 Claude 那种行号 gutter 属于前端改动，**本任务不做**。

## C. 高亮视觉对齐 Claude（前端，仅此一节动 TUI）

用户提供了 Claude Code 实测截图（2026-07-26），目标版面逐项拆解如下，
以截图为准：

1. **行号 gutter + 独立符号列**：最左列行号（300/301/302…），`+`/`-` 号在
   行号右侧单独一列，代码内容再往后。正负号**不在代码行首**——这解决了
   "行号前缀会挤掉行首 `+`/`-` 导致 startsWith 着色失效"的问题：本方案
   本来就要重写 diff 行的渲染结构，不再依赖行首字符。
2. **深绿/深红底，色带贯穿终端全宽**（不只到文字末尾）。
3. **diff 内保留语法高亮**：代码关键字/字符串/注释保持各自颜色，叠在
   深绿/深红底上（不是单色绿字/红字）。`markdown.tsx` 现成的
   `highlightLine(l, lang, t)` 可复用，lang 从被编辑文件扩展名推。
4. **空的新增行用更深一档的绿色**，有内容的行稍亮（截图中 310/320 行
   与相邻行的色差）。
5. 上下文行：无色、带行号、无符号。
6. 头部格式 Claude 为 `⏺ Update(path)` + `⎿ Added N lines`，bobo 保持
   现有 `● Edit File(...)` + `⎿ +N −N` 不变，只抄 diff 本体版面。

### 实现要点

- `ui-tui/src/components/markdown.tsx` 的 ```diff 渲染分支（约 750-790 行）
  重写为结构化渲染：先按 `@@ -a,b +c,d @@` 解析出行号游标，逐行分配
  （行号、符号、内容、类型），再按 gutter 布局渲染。
- 背景色挂在 `width="100%"` 的整行容器上（色带全宽）。
- 主题色 `theme.ts:294-297`：`diffAdded`/`diffRemoved` 改深绿/深红底，
  文字色改浅（具体取值以深色终端实际观感微调）；新增"空行深一档"的颜色
  变量或按透明度处理。
- 改色前 grep 确认这四个主题色没有其他组件占用。
- 行号位数对齐（最大行号宽度 pad），gutter 与代码列之间留单空格。

### 后端配套（小改）

`tools/edit_file.py` / `file_operation.py` 生成的 diff 保持标准 unified
格式（含 `@@` 行号信息，**不能丢**——行号 gutter 全靠它解析），
仅按 B 节要求去掉 `---`/`+++` 两行。

## 验收标准

1. 让 bobo 用 file_operation 修改/新建一个真实文件，对话流中出现红绿 diff 块。
2. 用 edit_file 修改文件，diff 块中**不再出现** `---`/`+++` 路径行，`@@` 行保留且为 muted 色。
3. 新建大文件（>40 行）时 diff 截断规则生效。
4. pty 自动化验收：让 bobo 改一个网页文件（覆盖 file_operation 场景），
   剥离 ANSI 后确认 diff 文本出现，且原始字节含红绿 SGR 颜色码。
5. 补充测试：断言 diff 块不含 `--- `/`+++ ` 行；file_operation 三种场景（覆盖/追加/新建）各有断言。
6. 高亮视觉（对照用户提供的 Claude 截图逐项核对）：行号 gutter + 独立
   +/- 符号列；深绿/深红底色带贯穿终端全宽；diff 内代码保持语法高亮；
   空新增行颜色深一档。
7. 完成后同步 `~/.bobo`（tools/ 目录 + ui-tui 重新 build + static 副本），并确认 `.venv` site-packages 是否也需要。
