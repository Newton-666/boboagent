# 票 LN-1：MEMORY.md 双向镜像

> 状态：待开工
> 前置：宪法第十七章 + docs/LIVING_NOTES_DESIGN.md（Q3 补 + 库址）
> 分支：`feat/memory-mirror`（从最新 main 新建）

## 目标

给 `~/.bobo_v2/knowledge_base.json` 配一个活人可读写的镜像
`<项目根>/library/MEMORY.md`，双向同步。JSON 仍是运行时真源，
md 是用户入口。bobo 记住的一切，用户翻开就能读、动手就能改。

## 库址（用户铁律）

`library/` 必须在项目根目录一级，禁止嵌套进 data/、docs/ 等子目录。
首次写镜像时自动创建 `library/`。

## 镜像格式

按 type 分小节，每条一行，锚点 = JSON 的 id：

```markdown
# MEMORY.md — bobo 的记忆（可手改，下次启动生效）
<!-- AUTO-SYNC: 本文件与 knowledge_base.json 双向同步 -->

## knowledge
- [#1] 用户要求修改代码时用 diff 格式 (2026-06-16 · 信号 100)
- [#42] CRMEB 试炼基线 v1 已存档 (2026-07-30 · 信号 100 · 草稿)

## preference
…
```

草稿条目行尾标 `· 草稿`；human_edited 条目标 `· 人手`。

## 同步规则（照抄设计文档，不得走样）

1. **JSON→md**：`add_entry` / 覆盖 / 删除 / 信号分变动后，
   幂等全量重生成镜像（禁增量 patch）。写失败静默降级记 WARNING，
   不得影响记忆主流程（参照 event_bus 降级先例）。
2. **md→JSON**：bobo 启动时（engine_adapter 初始化处）比对 mtime，
   md 比 JSON 新 → 解析回 JSON。导入前自动备份
   `knowledge_base.json.bak`（保留最近一次）。
3. **保守降级**：md 解析失败 → 跳过导入 + logger.warning +
   事件 `memory.mirror_import_failed`，JSON 原样不动。
4. **人手标记**：从 md 导入或 md 中新增的条目打 `human_edited: true`，
   镜像行尾标 `· 人手`；信号分自动衰减、草稿自动归档对这类条目豁免。
5. md 中用户新增的条目（无 #id 的行）→ 分配新 id 导入，
   行尾的时间/信号字段缺省给默认值（时间=导入时刻，信号=100）。

## 事件埋点（摄像头纪律）

`memory.mirror_write`（每次镜像重写，带条目数）、
`memory.mirror_import`（启动导入，带变更条目数）、
`memory.mirror_import_failed`（解析失败降级）。

## 验收金标准（全部物理检查，tests/test_memory_mirror.py）

1. **写镜像**：调 `add_entry("测试条目X")` → `library/MEMORY.md` 存在，
   含 `[#N] 测试条目X`，id 与 JSON 一致。
2. **覆盖同步**：修改某条目 text → 镜像对应行内容更新，其他行不变。
3. **删除同步**：删除条目 → 镜像对应行消失。
4. **手改导入**：关掉引擎，手改 md 某行 text，mtime 触新 → 重启初始化后
   JSON 对应条目 text 更新 + `human_edited: true` + .bak 备份存在。
5. **新增导入**：md 里加一行无 id 的 `- 我手写的记忆` → 重启后 JSON
   出现该条目（新 id、信号 100、human_edited）。
6. **解析失败降级**：md 改坏（乱格式）→ 启动后 JSON 与改前逐字节一致，
   事件 `memory.mirror_import_failed` 落地。
7. **幂等**：连续两次重生成，md 内容逐字节相同。
8. **降级不炸主流程**：把 `library/` 目录设为只读 → add_entry 正常返回，
   记忆照常工作，仅 WARNING 日志。
9. 全量 pytest 通过，现有 v5_memory 测试零回归。

## 边界

- 只做镜像层。主题笔记、index.md、蒸馏晋升**本票不做**（LN-2/3）。
- 不改 memory 注入 prompt 的现有逻辑。
- `library/` 加入 .gitignore 评估：知识库属用户数据，**不应进 git**——
  检查并追加 .gitignore。

## 纪律

- 开工前 `git branch --show-current` 确认在 `feat/memory-mirror`。
- 完成后五查汇报（含 git status 原文 + git branch --show-current 原文），
  ⛔️ 禁止 merge、禁止 push，等 Kimi 终审。
- 改了 core/ → 五查第 6 项填"是，需重启生效"。
