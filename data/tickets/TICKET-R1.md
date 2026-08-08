# TICKET-R1 — Obsidian 映射机制人口普查（纯侦察，禁止修复）

- 分支：`recon/ticket-r1-obsidian-mapping`（从最新 main 切出；只允许放报告文件，代码一行不许动）
- 类型：侦察票（探雷）——**只调查，不修复**
- 纪律：禁止改任何生产代码、禁止 merge、禁止 push 代码改动；报告除外
- 交付物：`docs/recon/obsidian-mapping-report.md`（唯一允许新增的文件）

## 背景（既定事实）

- owner 裁决：`boboagent_main/library/` 是主库（唯一正统），Obsidian 侧只是展示层/映射。
- 实测：`~/Desktop/Obsidian note/library/` 存在，含 agent开发 7 篇；主库已 21+ 篇。**两侧数量悬殊，疑似同步早已断裂。**
- 代码线索（不许凭线索下结论，要验证）：`memory.mirror_write` 事件、`tools/write_obsidian.py`（写 OBSIDIAN_VAULT）、`tools/obsidian_tools.py`、`memory mirror` 相关模块。

## 调查清单（每问必须给证据：文件路径+行号/命令输出）

### A. 通路普查：谁可能往 Obsidian 写？
1. 全项目 grep：哪些代码会写入 `OBSIDIAN_VAULT`？逐个列出（文件:行号 + 一句话说明写入什么）。
2. `memory.mirror_write` 是什么？谁触发、写去哪、写什么内容？（找出发射点与消费点）
3. living_notes 管道有没有 Obsidian 侧的出口？（已确认主出口是项目 library/，核实有无第二出口）

### B. 化石鉴定：Obsidian 侧 library 是什么来头？
4. `~/Desktop/Obsidian note/library/` 完整文件清单（路径 + 修改时间）。
5. 与主库逐篇对比：哪些是主库也有的（内容一致吗？差几个版本？），哪些是主库没有的（孤儿？）。
6. 从文件时间和 git 历史推断：最后同步发生在什么时候？是一次性拷贝还是曾有自动机制？

### C. 活死判定
7. 结论三选一并给证据：①有自动同步且活着 ②曾有自动同步已断裂（断点在哪）③从未有自动同步，纯化石。

### D. 方案建议（只建议，不实施）
8. 基于 C 的结论给出 2-3 个处置方案（修好它 / 建同步 / 归档删除化石并明示），每个方案写清代价与风险。owner 拍板后才许开修复票。

## 汇报格式（五查变体）
1. A/B/C 三部分的证据链（命令输出原文）
2. 一张"通路地图"：主库、Obsidian、记忆库三者之间的所有写入通路（ASCII 图）
3. 活死判定结论
4. 处置方案对比表
5. 施工过程自报：本次侦察中你用到了哪些工具、有没有遇到工具异常（探雷数据）

## 特别强调
- 发现任何 bug 都**不许顺手修**——记进报告的"附带发现"章节。
- 这同时是一次行为观察：Kimi 会盯你的 events，看你探雷过程本身有没有暴露异常。
