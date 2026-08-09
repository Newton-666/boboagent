# TICKET-R2 — Obsidian 单向镜像：主库真源 → vault 展示层

- 分支：`feat/ticket-r2-obsidian-mirror`（从最新 main 切出）
- 类型：修复票（owner 已拍板方向：Obsidian 变镜像，不是主储存）
- 纪律：禁止 merge、禁止 push、禁止碰 main；完成后五查汇报等 Kimi 终审
- 依据：`docs/recon/obsidian-mapping-report.md`（R1 普查报告，先读）

## owner 裁决（2026-08-09）

**主库 `boboagent_main/library/` 是唯一真源；`~/Desktop/Obsidian note/library/` 降为单向镜像展示层。**

## 施工清单

### A. 化石安置（先做，防同步覆盖）
1. 把 Obsidian 侧 `library/agent开发/` 7 篇孤儿移至 `~/Desktop/Obsidian note/04_Archive/bobo-library-化石-20260809/`（目录不存在则创建；04_Archive 不存在则建于 vault 根）。移动前后各列一次文件清单进汇报。
2. 确认 Obsidian `library/` 清空后，**该目录此后由镜像全量托管**（见 B）。

### B. 单向同步机制
3. 新建 `tools/library_mirror.py`：
   - `sync_library_to_obsidian()`：把主库 `library/` **全量镜像**到 `OBSIDIAN_VAULT/library/`——主库有什么镜像有什么，主库没有的镜像侧删除（限定在 `OBSIDIAN_VAULT/library/` 目录内，**绝不许碰 vault 里任何其他目录**；`.history/` 快照目录也同步）。
   - 安全闸：目标路径必须 realpath 校验落在 `OBSIDIAN_VAULT/library/` 内；OBSIDIAN_VAULT 未配置时静默跳过。
   - 镜像侧生成的文件头部加一行 `<!-- MIRROR: 真源=boboagent_main/library/，请勿手改 -->`（index.md 除外，它已有 AUTO-GENERATED 头）。
   - 发射 `library.mirror_sync` 事件（files_synced/files_removed/sid）。
4. 挂钩：`tools/living_notes.py` 的 `write_living_notes` 成功写完笔记/重建索引后调用一次 sync（try/except 降级，失败记 notes.error 不阻塞——纪律同 E4a）。
5. 手动全量入口：sync 函数支持独立调用（供测试与首次灌库）。

### C. 规则改写（误导清除）
6. 找到 vault `工作方式/` 下"Obsidian 作为唯一协作基础"规则文件，改写为镜像规则：**真源=项目 library/，Obsidian library/ 为只读镜像展示层，协作笔记一律走主库管道**。改写前后内容 diff 进汇报。

### D. 首次灌库 + 验收
7. 跑首次全量 sync，验收：
   - vault `library/` 与主库逐文件一致（含 index.md、.history/）
   - 化石 7 篇在 04_Archive，不在镜像里
   - 写一篇测试笔记走 living_notes 管道 → 镜像侧自动出现 → 删除测试笔记 → 镜像侧自动消失
8. 测试：新增 tests（tmp_path 双目录模拟）：全量同步一致 / 增量新增 / 删除传播 / 安全闸（vault 外路径拒绝）/ 未配置 vault 静默跳过。全量 pytest 零回归（基线 1512）。

## 边界
- 不动 living_notes 的成文/judge/索引逻辑；不动 obsidian 工具族；不建双向同步。
- vault 内除 `library/`、`04_Archive/bobo-library-化石-20260809/`、规则文件外，一个字节不许碰。

## 五查汇报要求
1. 化石移动前后清单。2. sync 实现要点 + 安全闸代码位置。3. 规则文件 before/after。
4. D7 三项实测输出。5. 测试清单 + 全量输出 + 分支状态 + 是否需重启。
