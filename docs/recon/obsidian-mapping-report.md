# Obsidian 映射机制人口普查报告（TICKET-R1 · 纯侦察）

- 票号：TICKET-R1
- 分支：`recon/ticket-r1-obsidian-mapping`（基于 origin/main 2a61235 切出）
- 日期：2026-08-08
- 性质：纯侦察，未改动任何生产代码；本报告是唯一新增文件
- 结论先行：**Obsidian 侧 `library/` 是化石；主库与 Obsidian 之间从未有过双向同步，只有过一次"写入出口切换"**

---

## 一、A 通路普查：谁可能往 Obsidian 写？

### A1. 全项目 grep `OBSIDIAN_VAULT`（写入方）

```bash
grep -rn "OBSIDIAN_VAULT" --include="*.py" .
```

命中 22 处，全部是 **Obsidian 笔记工具族**，写入口统一在 `file_writer.write_obsidian / append_obsidian`（通过 `_normalize_path` 解析落点）：

| 文件:行号 | 说明 |
|---|---|
| `tools/file_writer.py:12,33,162` | 核心写入器；备份到 `OBSIDIAN_VAULT/Bobo数据库/.backups` |
| `tools/write_obsidian.py:57` | 工具层，委托 file_writer，写前读旧内容做 inline diff |
| `tools/append_obsidian.py:43` | 追加工具 |
| `tools/obsidian_tools.py:10,24,81,85,88,94,98,108,122` | 路径规范化 `_normalize_path` + 搜索 |
| `tools/read_obsidian.py:28` / `search_obsidian.py` / `delete_note.py:20` / `rename_note.py:20` / `move_note.py:20` / `move_to_folder.py:20` / `create_folder.py:19` / `delete_folder.py:20` / `batch_delete_notes.py:31` / `batch_move_notes.py:43` / `classify_note.py:91` / `read_recent.py:20` / `code_to_obsidian.py:36,38` / `wiki_rebuild.py:11,13` | 读/改/删/分类/重建工具族（读为主，写为辅） |
| `bobo_tui_gateway/entry.py:271` | TUI 网关读环境变量（展示层） |

**落点规则（`obsidian_tools.py:81-133` `_normalize_path_inner`）**：
1. 含 `/` 的路径 → 直接拼 `OBSIDIAN_VAULT/<路径>`
2. 无分隔符：先查 vault 根 → 再查 `Bobo数据库/` → 全 vault 模糊搜索（去空格、大小写不敏感）
3. 都不存在 → **默认返回 `OBSIDIAN_VAULT/Bobo数据库/<文件名>`**

环境实测：`OBSIDIAN_VAULT=/Users/niuqingwei/Desktop/Obsidian note`（.env 与 shell 均一致）。

### A2. `memory.mirror_write` 是什么？—— 与 Obsidian 无关（票中线索是误导）

- 定义：`tools/memory_mirror.py:282`，`sync_mirror()` 成功写镜像后 emit
- 作用：`data/knowledge_base.json`（真源）↔ `<项目根>/library/MEMORY.md`（活人可读镜像）**双向镜像**
- 写去哪：`memory_mirror.py:33-34` `MIRROR_PATH = _REPO_ROOT / "library" / "MEMORY.md"` —— **项目主库，不是 Obsidian**
- 触发点：`tools/v5_memory.py:50-51`（记忆增删改后调用 `sync_mirror()`）；`core/engine_adapter.py:203`（启动时 `import_from_md` 反向导入）
- 活跃度：events.jsonl 中 `memory.mirror_write` 事件 **455 条**（最新 entry_count=154），机制活着且高频

**结论：`memory.mirror_write` 是主库内部机制，与 Obsidian 通路零交集。** 票中把它列为"可能往 Obsidian 写"的线索不成立（验证通过：未凭线索下结论）。

### A3. living_notes 管道有无 Obsidian 侧出口？—— 无

- `grep -n -i "obsidian" tools/living_notes.py` → **0 匹配**
- living_notes 只写主库：`library/<领域>/<主题>.md`（LN-2 主题笔记）、`index.md` 自动索引（文件头注明"AUTO-GENERATED: 由 tools/living_notes.py 维护"）
- 上线时间：`git show 0d4296b` = **2026-07-31 12:44:46** "feat: 票 LN-2 主题笔记 MVP"
- 主库最早笔记 `2026-07-30.md` mtime 2026-07-31 23:55 —— 与管道上线时间吻合

### A4. 定时任务侧

- `bobo_schedule list`：`Daily Obsidian Scan & Organization Plan — daily 08:00`，任务内容是"扫描 vault 分析内容、给整理建议"——**只读整理建议，非同步**
- `crontab -l`：仅 `ai_business_collector.py`（每周一 10:00），与 Obsidian 无关
- `grep -rn "sync.*obsidian\|rsync\|mirror.*vault" tools/` → 0 匹配：**全项目无任何主库↔Obsidian 同步代码**

---

## 二、B 化石鉴定：Obsidian 侧 library 是什么来头？

### B1. Obsidian 侧 `library/` 完整清单（7 篇，全部 .md）

```
/Users/niuqingwei/Desktop/Obsidian note/library/agent开发/
  AI Agent 的演进：从工具调用到自主协作.md   2026-06-18 16:41   3.1 KB
  bobo-desktop Bug 扫描报告.md               2026-06-18 20:16   4.8 KB
  Bobo 的技术内核：Spawn Worker 与 Loop 机制解析.md 2026-07-23 15:18  12 KB
  bobo_chat_room.md                          2026-07-26 15:49   3.4 KB
  Agent 开发手册.md                          2026-07-27 10:46 100 KB
  TICKET-022-C 修复记录.md                   2026-08-01 15:19   0.5 KB
  压缩体系战役复盘.md                        2026-08-01 20:36  13 KB
```
（vault 根无 .git；`library/` 目录 8-01 20:36 创建，`agent开发/` 8-05 18:36 更新——仅目录元数据）

### B2. 与主库逐篇对比：**零重叠，7 篇全是孤儿**

| 对比维度 | 主库 `boboagent_main/library/` | Obsidian `…/Obsidian note/library/` |
|---|---|---|
| 篇数 | 27 篇 .md（另有 .history/、index.md、MEMORY.md） | 7 篇 |
| 时间跨度 | 2026-07-31 23:55 ~ 2026-08-08 10:07（活跃） | 2026-06-18 ~ 2026-08-01 20:36（停更） |
| 同名匹配 | — | **7 篇在主库全库（含全部子目录）0 匹配** |
| git 状态 | 被 .gitignore:50 忽略（`library/`），git 内 0 文件 | 无 .git，纯文件系统 |

主库 `agent开发/` 现有 6 篇（创建技能、工具加载优化、TICKET-024修复完成、TICKET-025重复emit修复、票据授权增补、技能与记忆机制），与 Obsidian 侧 7 篇**文件名无一篇相同**——两侧是两套互不重叠的笔记集合。

### B3. 内容来源判定（读文件头确认）

Obsidian 侧 7 篇内容为 **Bobo 工作产物风格**：TICKET 修复记录、战役复盘（时间跨度 2026-07-29~08-01、涉及 TICKET-016~024）、双 Bobo 实例对话记录。其中 2 篇有 events.jsonl 直接证据（见 C1）。

### B4. 时间线推断：一次性出口切换，非持续同步

| 时间 | 事件 | 证据 |
|---|---|---|
| 06-18 ~ 07-27 | Bobo 笔记写 Obsidian（5 篇） | 文件 mtime |
| 07-31 12:44 | **living_notes 主库管道上线**（LN-2 commit 0d4296b） | `git show` |
| 07-31 23:55 | 主库最早笔记 | 文件 mtime |
| 08-01 15:19 | Obsidian 侧最后一篇 TICKET-022-C 修复记录 | events `write_obsidian` 调用 + 文件 mtime 双证 |
| 08-01 20:36 | **Obsidian 侧最后一次写入**（压缩体系战役复盘） | events `write_obsidian` 调用 + 文件 mtime 双证 |
| 08-01 ~ 08-07 | 主库持续产出（TICKET-024/025、技能与记忆机制等） | 文件 mtime |
| 08-05 18:42 | 会话确立"Obsidian 作为唯一协作基础"规则（写于 vault `工作方式/`），但**实际写入仍走主库** | events + vault 文件 |
| 08-06 11:27 | `.backups` 最后一次活动（备份真人 `01_Projects/Applied spectroscopy/` 笔记） | .backups 文件名+时间 |
| 08-07 20:17 | 本会话笔记（命令行倒计时器）落主库 `library/开发/` | 文件 mtime |

**Bobo 数据库 `.backups`（85 项）**：备份的是 `01_Projects/Applied spectroscopy/Modelling and Engineering Framework.md` 等**真人 Obsidian 研究笔记**（write_obsidian 覆盖前自动备份），最后活动 08-06 11:27，与"library 同步"无关，是单篇协作编辑痕迹。

---

## 三、C 活死判定

> **结论：② 曾有自动写入已断裂（严格说：从未有过"双向同步"，只有一次写入出口切换）。**

证据链：
1. 曾有：6/18~8/1 Bobo 通过 `write_obsidian` 工具（+ `_normalize_path` 落点解析）把笔记写进 Obsidian vault 的 `library/agent开发/`，events.jsonl 有 2 次显式调用记录（08-01 15:19 / 08-01 20:36），文件 mtime 与调用时间秒级吻合。
2. 断裂：07-31 living_notes 上线后，笔记出口切到主库 `library/`；Obsidian `library/` 最后写入停在 **08-01 20:36**，之后 7 天零更新；主库同期持续产出。
3. 无同步机制：全项目无 rsync/sync/mirror-vault 代码；`memory.mirror_write` 只镜像主库 MEMORY.md；Daily Obsidian Scan 是只读建议任务。
4. 规则与行为背离：08-05 用户在 vault `工作方式/` 立下"Obsidian 作为唯一协作基础"，但 08-07 实际笔记仍落主库——规则未落地，主库才是事实真源。

---

## 四、D 处置方案建议（待 owner 拍板，未实施）

| 方案 | 做法 | 代价 | 风险 | 适用前提 |
|---|---|---|---|---|
| **① 归档化石 + 明示**（推荐） | 将 Obsidian `library/agent开发/` 7 篇移至 vault `04_Archive/`（或主库 `library/归档/`），在 vault 与主库 index 各加一行"Obsidian library/ 已废弃，真源=主库 library/" | 低（一次文件移动+两行文档） | 低；仅损失"Obsidian 侧旧笔记的原地可读性"，内容不丢 | owner 认可主库唯一真源 |
| **② 建单向同步（主库→Obsidian）** | 写同步脚本/定时任务，把主库 `library/` 镜像到 Obsidian `library/`（保留两侧零重叠现状为全量拷贝） | 中（需维护脚本+处理命名冲突+防止循环写备份） | 中；与 08-05"Obsidian 唯一协作基础"规则方向相反，可能再次造成双真源 | owner 想重开 Obsidian 展示层 |
| **③ 维持现状 + 文档明示** | 化石不动，仅在主库 `library/index.md` 加注"Obsidian library/ 为 8-01 前遗留，不维护" | 极低（一行文档） | 低；但 Obsidian 侧会继续误导（看起来像活库） | owner 无暇处理 |

**附带发现（不修，仅记录）**：
1. **grep_code 工具异常**：对 `OBSIDIAN_VAULT`、`mirror` 等模式返回 0 匹配，与终端 grep 22 处/455 事件矛盾——grep_code 在本仓库存在漏检（路径/类型限制），后续排查类任务建议用终端 grep 交叉验证（探雷数据，见下）。
2. 平台 `write_obsidian`（本会话实测）写主库 `library/开发/命令行倒计时器.md`，而项目内 `tools/write_obsidian.py` 按 `_normalize_path` 应写 Obsidian vault——**两套实现并存**，存在行为分叉风险。
3. `data/Agent开发手册_备份_20260801.md`（211 KB）与 Obsidian 侧 `Agent 开发手册.md`（100 KB）大小差一倍，疑为不同版本，可人工核对去留。
4. `Bobo数据库/` 下非备份 .md 为 0，但 `.backups` 85 项——曾写入后被清空/移走的痕迹，建议人工确认是否误删。

---

## 五、施工过程自报（探雷数据）

- 用到的工具：read_local_file（票、write_obsidian.py、file_writer.py、obsidian_tools.py、index.md）、load_result、grep_code、execute_terminal（git fetch/checkout、grep -rn、git log、mkdir）、code_execution（逐篇对比/时间统计脚本）、bobo_schedule（list）、bobo_config（view）、task_ledger
- **工具异常 3 起**：
  1. `grep_code` 对 `OBSIDIAN_VAULT` / `mirror` 返回 0 匹配（误报），换 execute_terminal `grep -rn` 后 22 处命中——**grep_code 漏检**
  2. execute_terminal 复合命令（多段 `;` 拼接 + `stat -f` + for 循环）被安全黑名单拦截 2 次，拆分为单条简单命令后通过——**复杂 shell 被拦**
  3. `git log --follow -- library/` 空输出（因 library/ 被 gitignore，属预期，非异常）
- 全程 0 处代码改动；仅新增 `docs/recon/obsidian-mapping-report.md`（本文件）+ `docs/recon/` 目录
