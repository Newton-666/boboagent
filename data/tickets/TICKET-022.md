# 票 TICKET-022：会话笔记台账——每轮对话知道自己有几篇笔记

## 病灶

用户原话："他每个会话必须要知道自己创建了几篇笔记，需要的时候去翻阅
特定几篇，而不是 library 变大后为了找个别信息把整个 library 都看一遍。"

现状（LN-4 指针）有两个结构性短板：

1. **无"产出"意识**：sid 命中 source_sessions 的笔记只是"必带指针"，
   与主题词临时命中的指针混排在一起（上限 3 条、300 字符），模型不知道
   "这些是我这个会话亲手写的"，数量被截断后更无完整概念。
2. **无翻阅索引**：笔记变多后，模型没有按 sid 的精确清单，只能泛翻
   library——上下文压力随 library 增长线性恶化。

数据基础已存在：events.jsonl 有 `notes.written` 事件（含 sid），
无需扫描 library 文件系统。

## 目标

### A. 会话笔记台账（injector 新增小段，笔记指针段内子区块）

从 `notes.written`/`notes.updated` 事件按当前 sid 过滤，生成本会话产出清单：

```
📝 本会话已产出笔记 3 篇（可按需 read_local_file 翻阅，勿全量读取）：
  ① skills/创建技能.md（v2 · 07-31 23:41）
  ② projects/boboagent/压缩优化.md（v1 · 07-31 23:55）
```

- 与 LN-4 主题词指针**分区展示**：产出清单在前（标注"你写的"），
  主题词命中在后（标注"相关"）
- 预算：笔记指针段总预算 6%（LN-5 比例制）内自行分配；
  产出清单优先于主题词指针，条目超预算时省略中间保留首尾 + "（共 N 篇）"
- 无事件/读取失败 → 该子区块静默省略，不阻塞注入
- prompt.budget 的 note_pointers 段补字段：`session_notes: N`

### B. 翻阅纪律（文案，身份段或笔记段尾部一行）

`翻阅纪律：笔记按需单篇读取（read_local_file），禁止无目标批量遍历 library。`

## 边界（不碰）

- LN-4 关联判定双路径、LN-5 比例池、living_notes 写入逻辑不动
- 不新增 library 文件系统扫描（只读 events.jsonl）

## 验收

1. 构造 3 条本会话 notes.written + 2 条其他 sid 事件 → 台账只列本会话 3 篇，
   含"共 3 篇"与版本/日期；他 sid 笔记不出现
2. 产出清单与主题词指针分区标注（"你写的"/"相关"字样断言）
3. 预算超限：构造 10 篇产出 → 段长 ≤ 笔记段预算，含"（共 10 篇）"，
   首尾保留中间省略
4. 零事件/events.jsonl 缺失 → 子区块省略，注入正常
5. prompt.budget 事件带 session_notes 字段且与实测一致
6. 全量 pytest 零回归（基线 1429 passed / 2 skipped，若 019/020/021 先合并则相应上调）
7. 改 core/ → 五查第 6 项填"是，需重启"

## 纪律

- 从最新 main 切 `fix/ticket-022-session-notes`，开工先 `git branch --show-current`
- 五查汇报含 git status 原文 + git branch --show-current 原文
- ⛔ 禁止 merge、禁止 push，完成后 `git checkout main` 归位，等 Kimi 终审
