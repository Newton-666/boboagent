# 票 TICKET-020：工作锚点——压缩免死金牌，根治"执行完就忘"

## 病灶（已实锤）

`core/context.py _compress_history`：60 条消息触发压缩，只保最近 30 条，
其余交给 LLM 写七段摘要。两个结构性漏洞：

1. **摘要质量无保障**：LLM 写漏了"当前任务/已写文件"，信息永久丢失。
   用户实测：执行 skill 两次后，bobo 忘记自己刚才干了什么。
2. **没有跨压缩存活的任务状态**：摘要本身在下一轮压缩时会被当普通内容
   再压缩一次（虽有保留逻辑，但任务状态不随工作进展更新）。

工具密集型会话（skill 创建一次烧 20+ 条消息）必然快速撞 60 条预算，
所以"干活越重，忘得越快"。

## 目标

### A. 工作锚点（核心）

新增 `_build_work_anchor()`（context.py 或 engine.py，选合适的家）：
压缩触发**前**，从可靠来源（不是 LLM 摘要）机械提取：

- 当前任务：最近一次用户指令原文（前 200 字符）
- 本会话已写/已改文件：从 events.jsonl 的 tool.exec 事件
  （write_file/edit_file/apply_patch 类）按 sid 过滤，取 path 去重，最多 10 条
- 台账状态：若 task_ledger 存在，取未完成项标题（最多 5 条）
- 待兑现承诺：若承诺闸有记录，取之（没有则略）

格式：

```
[工作锚点 · 压缩豁免 · 每轮更新]
🎯 当前任务：{用户最近指令}
📁 本会话已写文件：a.py, b.md, ...（共 N 个）
📋 台账未完成：①… ②…
```

- 作为 role=system 消息插入 history 头部，标记 `[工作锚点` 前缀
- **压缩豁免**：`_compress_history` 的 existing_summaries 保留逻辑
  扩展为同时保留 `[工作锚点` 前缀消息（旧锚点被新锚点替换，只留一份）
- **每轮压缩时重建**（不是保留旧的）：保证锚点反映最新状态

### B. 压缩金标准测试

构造 80 条消息的会话（含 3 次 write_file 到 x.py/y.py/z.md + 用户指令
"创建 skill"），触发压缩后断言：

1. history 中存在 `[工作锚点` 消息且含 x.py/y.py/z.md 与"创建 skill"
2. 锚点只有一份（重复压缩不堆积）
3. 二次压缩后锚点内容更新（模拟又写了 w.py → 锚点含 w.py）
4. 现有七段 LLM 摘要逻辑不受影响（mock LLM 仍被调用）

## 边界（不碰）

- 60 条预算值、keep_count=30 不动（是否调大留给 context_lab 数据说话）
- LLM 七段摘要格式不动（锚点是补充，不是替代）
- tool.exec 事件读取失败 → 锚点降级为只含当前任务一行，绝不阻塞压缩

## 验收

1. 上述金标准 4 条全过（tmpdir 隔离 events.jsonl）
2. 无 tool.exec 事件/无台账/无承诺时锚点正常生成（降级路径）
3. 全量 pytest 零回归（基线 1429 passed / 2 skipped，注意 TICKET-019 可能先合并）
4. 改 core/ → 五查第 6 项填"是，需重启"

## 纪律

- 从最新 main 切 `fix/ticket-020-work-anchor`，开工先 `git branch --show-current`
- 五查汇报含 git status 原文 + git branch --show-current 原文
- ⛔ 禁止 merge、禁止 push，完成后 `git checkout main` 归位，等 Kimi 终审
