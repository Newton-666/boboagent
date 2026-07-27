# TASK_L3_MEMORY_TIME_DECAY — L3 任务单①：记忆时间衰减 + 时效可见性

> 2026-07-27 Kimi 出单。L3 级（多文件、动注入链核心）——bobo 实现、
> duo B 验收、Kimi 终审。同时是崩溃复现的"诱饵任务"（长会话+密集工具，
> 日志已架好，崩了正好抓堆栈）。

## 现状摸底（我已读码确认，先核实再动手）

已有（今天 feat/memory-signal-score 上线）：
- `signal_score`：初始 100、引用 +10、忽略 -5、<20 永不注入、上限 200
- `decay_all(-5)`：**每次 LLM 调用后**对本轮未匹配的记忆扣分
- `last_matched` 字段：每次 bump 更新为当前时间
- `get_top_memories`：Top-N 注入 + 关键词/词重叠加权
- 草稿记忆：is_draft + signal_score 30 起步

缺口（duo roadmap B 的挑刺原话："过时偏好 vs 当前偏好分不开"）：
1. **衰减是轮次驱动不是时间驱动**——`decay_all` 按"本轮未匹配"扣 5 分。
   一条每天都被引用的事实（如"用户用 GPT-4o"），即使三个月没更新，
   分数依然 200——系统分不清"活跃"和"新鲜"
2. **注入时没有时效标注**——LLM 看到的记忆条目没有"年龄"信息，
   无法自己判断"这条可能过时了"
3. **草稿没有生命周期**——is_draft 30 分起步，但没有晋升/清退路径

## 任务文本（粘贴给 bobo）

```
任务：记忆系统时间衰减 + 时效可见性（feat/memory-time-decay 分支）

工作目录：/Users/niuqingwei/Desktop/BOBO_Project_Backup

背景：信号分系统已上线（signal_score/decay_all/Top-N 注入），
但衰减是轮次驱动的——一条每天被引用的旧事实永远高分。
需要加时间维度：知识会随墙钟时间过时。

现状（先读码核实，不许猜）：
- tools/v5_memory.py：add_entry/bump_signal/decay_all/get_top_memories
- core/proactive.py：decay_all 的调用点 + 注入文本拼装

要求：
1. git checkout -b feat/memory-time-decay，全程在该分支
2. 先读 v5_memory.py 的信号分区（约 338-390 行）和 proactive.py
   的注入段，理解现有衰减和注入流程
3. 实现时间衰减（与现有轮次衰减并存，不替换）：
   - 新增 time_decay()：以 last_matched（无则 timestamp）为基准，
     按墙钟年龄扣分。建议档位：≥7 天 -5/天龄段、≥30 天加速，
     具体曲线你定但要在 commit message 说明理由
   - 下限保护：分数不低于现有 <20 不注入的规则语义
   - 幂等：同一天重复调用不得重复扣分（记录 last_time_decay 字段）
   - 调用点：跟随 decay_all 的同一个位置（proactive.py）
4. 实现时效标注：get_top_memories 返回的条目注入文本时，
   年龄 ≥14 天的附加 "（N 天前，可能过时）" 标注，
   让 LLM 自己能判断新旧
5. 草稿生命周期（轻量）：is_draft 条目 7 天未被引用（bump）过
   且分数 ≤30 → time_decay 时自动归档（archived=True，不再注入），
   不删除（用户可回溯）
6. 补测试（构造伪造时间戳的条目）：
   - 8 天前的条目被时间衰减、今天的条目不受影响
   - 同日重复调用 time_decay 不重复扣分
   - ≥14 天条目注入文本带时效标注、新条目不带
   - 旧草稿自动归档、被引用过的草稿不归档
   - 现有信号分测试全部保持绿
7. ./.venv/bin/python3 -m pytest tests/ -q 全绿
8. 在 feat 分支上 commit，输出五查汇报（表格格式），然后停
   （v2 规矩：汇报后允许本地 merge，禁止 push）

验收标准（逐条可判定）：
① 时间衰减与轮次衰减并存且互不干扰——现有 decay_all 语义不变
② 幂等：同日重复调用不重复扣分（测试证明）
③ 时效标注 ≥14 天可见、新条目干净
④ 草稿归档只动"7 天未被引用且低分"的，有引用史的不动
⑤ 曲线设计理由写在 commit message（为什么 7 天/30 天档）
⑥ pytest 全绿 + 五查汇报表格 + 未 push
```

## 验收链路（L3 全流程）

1. bobo 交付 → 我（Kimi）初审：构造伪造时间戳直测 time_decay、
   检查幂等、检查与 decay_all 的相互干扰、全量 pytest
2. 初审过 → duo B 验收 diff（重点：曲线合理性、归档边界、
   注入文本变化对 LLM 行为的影响）
3. B 过 → 用户终审合并

## 备注

- 这是崩溃诱饵任务：干的过程中崩了，先看 data/logs/bobo.log
  拿临终堆栈再继续
- 范围红线：不改轮次衰减语义、不动 get_top_memories 的加权逻辑、
  不引入 embedding（roadmap 已拍板轻量路线）
