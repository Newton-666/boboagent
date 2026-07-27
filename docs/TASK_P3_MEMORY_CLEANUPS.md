# TASK_P3_MEMORY_CLEANUPS — 后续小票：记忆系统两处清扫

> 2026-07-27 Kimi 出单。P3 级（几行改动，L2 强度验收即可）。
> 来源：L3① duo B 验收报告 3 条非阻塞建议中的两条可代码化项。

## 任务文本（粘贴给 bobo，择日派发）

```
任务：记忆系统两处清扫（feat/memory-cleanups 分支）

工作目录：/Users/niuqingwei/Desktop/BOBO_Project_Backup
来源：L3① duo B 验收报告的非阻塞建议（报告原文见会话记录）

1. _age_days mutation 泄漏：
   get_top_memories 把 _age_days 以 in-place 方式写进条目 dict，
   注入后若有 _save 调用会把临时字段持久化到 knowledge_base.json。
   修法：返回前对条目 shallow copy（dict(e)），临时字段只活在拷贝上。
   补测试：调用 get_top_memories 后 _save，JSON 里不得出现 _age_days。

2. time_decay/decay_all 依赖 inject_context 生命周期：
   主动模式 mode=="off" 时两者都不执行——记忆衰减停摆。
   这是继承自 decay_all 的原有限制。修法：把衰减调用移到
   与注入模式无关的位置（引擎每轮收尾处），注意别重复调用。
   补测试：mode="off" 时衰减仍执行。

3. 顺手补 commit 说明（不用改代码）：
   L3① 附带修复了 proactive.py 读 mem['content']（应为 'text'）的
   预存 bug——旧代码注入是空壳。本次 commit message 提一句即可。

约束：
- pytest 全绿；feat 分支 commit；五查汇报；允许本地 merge 禁 push
- 不改衰减参数、不动注入加权逻辑
```

## 另记（不成票，入问题雷达）

- **spawn_worker 结果转播又晃了一次**（l3-review-B "Worker 结果未写回"，
  主 bobo 自己顶上审查）。上午修的提取器只解决"多轮拼接"，
  "结果未写回"是另一个症状——同名覆盖？5 分钟清理太短？
  写回路径的竞态？下次出现时抓 data/logs/bobo.log。
- **恢复的知识库分数分布异常**：113 条记忆 signal_score max 仅 5
  （初始 100）。decay_all 每 LLM 调用 -5 的高频环境下，
  全库被压到底部——轮次衰减可能过强，这正是 time_decay
  要解决的"分不清活跃和新鲜"的反面。观察 time_decay 上线后
  是否缓解，不缓解则需重新校准 decay_all 的 -5/轮。
