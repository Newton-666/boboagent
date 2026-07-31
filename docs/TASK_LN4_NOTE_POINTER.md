# 票 LN-4：笔记指针注入 + injector 分层保底 + 上下文预算监控

## 背景与病灶

三个问题一张票解决，因为它们共享同一处代码（injector 系统提示组装）：

1. **LN-4 定稿设计（用户拍板）**：笔记**不整篇注入**系统提示。笔记会变大、历史会变多，
   整篇注入不可扩展。正确模式 = **轻指针 + 按需翻阅**（同 load_results 范式）：
   系统提示只带一行指针，bobo 深入讨论时用 read_local_file 自己翻全文。
   映射是多对多：一篇笔记 ←→ 多个会话（frontmatter source_sessions 维系）。
2. **injector 缺陷（已实锤）**：系统提示 5000 字符共享池先到先得，记忆块（4953/5000）
   挤掉 skill 注入段，导致 test_injector 测试随用户记忆增长而失败——
   测试依赖真实记忆库状态，且注入层无分段保底。
3. **预算黑箱**：系统提示每段实际占多少、何时截断、指针带没带，目前零观测。
   后续压缩实验和注入调整需要数据说话（用户明确要求"监控能看到上下文情况"）。

## 目标

### A. 笔记指针注入（核心）

injector 组装系统提示时新增"关联笔记指针"段：

- **关联判定两条路径**：
  1. 当前 session id 命中笔记 frontmatter `source_sessions` → 必带
  2. 当前用户消息命中主题词（library/index.md 扫描，主题名是用户消息子串
     或用户消息是主题名子串，去重取前 3）→ 临时带
- **指针格式**（每条一行，总计 ≤3 条）：
  `📚 关联笔记：<domain>/<topic>.md（v{N} · {last_touched} 更新 · 深入讨论请先用 read_local_file 读全文再答）`
- 指针段总预算 **300 字符**（独立保底，不被记忆/skill 挤占）
- library 不存在 / 无关联 → 该段整体省略，零动作
- 扫描失败静默降级（WARNING + notes.error），绝不阻塞注入

### B. injector 分段保底（修缺陷）

系统提示共享池改为分段保底（只动预算分配逻辑，不动各段内容生成）：

| 段 | 保底（地板） | 天花板 | 超额处理 |
|---|---|---|---|
| 身份 | 全量 | 全量 | 不动 |
| skill 注入 | 800 字符 | 1500 | 按原相关度逻辑截断 |
| 记忆块 | 1000 | 2500 | 按信号强度淘汰（v5_memory 信号分已有） |
| 笔记指针 | 300 | 300 | 取相关度前 3 条 |

- 各段保底之和 ≤ 总池；总池仍 5000（比例化改造留给后续票，本票不扩 scope）
- 修 `test_injector` 环境污染：测试改为注入隔离的临时记忆库，
  不再依赖用户真实 knowledge_base.json 状态

### C. 上下文预算监控（数据地基）

每轮系统提示组装完成时写 **1 条** `prompt.budget` 事件进 events.jsonl：

```json
{
  "sid": "...",
  "total_chars": 4873,
  "sections": {
    "identity": 42,
    "memory": {"chars": 2451, "entries": 58, "total_entries": 173, "evicted": 12},
    "skills": {"chars": 800, "truncated": false},
    "note_pointers": {"chars": 187, "count": 2, "topics": ["矩阵B构造与训练"]}
  }
}
```

- 截断/淘汰发生时各段自己补 `truncated`/`evicted` 字段
- 这是后续所有上下文评估的数据源（context_lab 后续票再加分析模式，本票只埋点）

## 边界（不碰）

- 笔记内容生成（living_notes.py）不动；MEMORY.md 镜像不动
- 总池 5000 → 模型比例化 留给后续票
- context_lab 分析模式扩展 留给后续票
- 历史层压缩（context.budget=60）不动

## 验收（tmpdir/隔离环境物理检查）

1. 指针注入：构造 library + source_sessions 含当前 sid → 系统提示含指针行，格式含 v{N} 和"读全文再答"
2. 主题词命中：sid 不关联但用户消息含主题名 → 指针出现；无关联 → 指针段整体缺席
3. 指针预算：构造 10 篇关联笔记 → 只取前 3 条，段长 ≤300 字符
4. **保底金标准**：构造记忆块可吃满 5000 的场景 → skill 段仍 ≥800 字符、指针段仍在（回归灭掉今天的缺陷）
5. 记忆淘汰：超额时低信号条目先淘汰（断言传信号分最低的条目不在注入中）
6. 测试环境隔离：test_injector 相关测试在真实 knowledge_base.json 任意状态下都稳定通过
   （连续跑 3 次全量验证）
7. 监控事件：组装后 events.jsonl 有 prompt.budget 事件，sections 四段齐全、字符数与实测一致
8. 无 library / library 只读 → 注入正常、有降级事件、不炸
9. 全量测试零回归（基线 1396 passed / 2 skipped；修复后 test_injector 全绿）

## 纪律

- 从最新 main 切 `feat/note-pointer`，开工前 `git branch --show-current` 确认
- 若改 core/（injector 所在文件）→ 五查第 6 项填"是，需重启"
- 五查汇报含 git status 原文 + git branch --show-current 原文
- ⛔ 禁止 merge、禁止 push，等 Kimi 终审
