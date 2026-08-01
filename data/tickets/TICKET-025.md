# 票 TICKET-025：工作锚点两个瑕疵补丁（pi 核查发现）

## 背景

pi agent 交叉核查已合并的 TICKET-020 时发现两个小瑕疵（不影响当前功能，
但会在特定场景削弱锚点）：

1. **路径截断**：`_build_work_anchor` 从 `tracker._change_log` 的 desc 按
   `:` / `（` 分割提取文件路径——若文件名本身含冒号（如时间戳文件名
   `report_10:30.md`）会被截断成错误路径。
2. **历史塌缩丢失**：`compress_changelog` 会把早期 change_log 条目压成
   `[历史改动]` 一条，锚点随之丢失更早的文件记录——会话越长，锚点文件
   清单越短，与"锚点防失忆"的目标背道而驰。

## 目标

1. 路径提取改稳健方案：优先用 change_log 条目的结构化字段（若有 path/file
   字段直接用；没有则施工时给 tracker 写入处补结构化字段，不再从 desc 文本
   解析）。确实无法结构化时，用右分割（rsplit）+ 路径存在性校验兜底。
2. 锚点文件清单的数据源改为"会话级累计集合"：引擎维护
   `self._session_written_files: set`（tracker 每次记录 change_log 时同步
   加入），塌缩不影响该集合；锚点从集合取，不从 change_log 取。
   集合只增不删，会话结束随引擎销毁。

## 验收

1. 含冒号文件名（`report_10:30.md`）写入后锚点含完整路径
2. 触发 compress_changelog 塌缩后，锚点仍含塌缩前写入的早期文件
3. test_work_anchor 原 9 条金标准零回归
4. 全量 pytest 零回归（基线以合并时 main 为准）
5. 改 core/ → 五查第 6 项填"是，需重启"

## 纪律

- 小票，从最新 main 切 `fix/ticket-025-anchor-robust`，可插队施工
- ⛔ 禁止 merge、禁止 push 到 main，完成后 `git checkout main` 归位，等 Kimi 终审
- 五查汇报含 git status 原文 + git branch --show-current 原文
