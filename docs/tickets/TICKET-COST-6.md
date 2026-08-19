# 票 COST-6：COST-2 动态块写回 history → "双 user 夹工具轮"结构 → thinking 400（含缓存命中率实测验收）

分支 `feat/ticket-cost-6-dynblock-user`,自最新 main（`52d569d5`）切出。
回滚标签 `rollback/pre-cost-6` 先打再动工。
六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等终审。

---

## 背景（2026-08-19 20:33 实弹二次事故 + Kimi 根因定位）

**现象**：P0-5 施工中再次出现
`HTTP 400 "The reasoning_content in the thinking mode must be passed back to the API."`
（P0-1 时第一次，REASONING-ECHO 修了"回传"仍复现——说明根因不在回传侧）。

**根因（Kimi 定位，events.jsonl 取证）**：
- 该会话 messages 结构为 **user#0（COST-2 动态块）→ 103 条工具轮 → user#104（COST-2 动态块）**；
- 两个 user 之间夹大量 tool_calls 轮 → 满足 DeepSeek "两个 user 之间若发生
  工具调用，中间 assistant 的 reasoning_content 必须回传" 规则 → 400；
- **这两个 user 消息都是 COST-2 动态块**——injector.py:760 注释明确：
  "messages 内 user dict 与 engine.history 共享引用 → 附加同时写回 history"。
  build_messages 每轮把动态块（记忆/笔记/纪律/NOW）附加到**最后一个 user 消息**
  的 content 前部，因共享引用**写回 history** → history 里出现第二个 user 消息 →
  触发结构成立 → 400。
- **为什么间歇**：动态块只在 `_tail_blocks` 非空时注入（injector.py:769
  `if _tail_blocks:`）——有记忆/笔记/纪律/NOW 要注入时才产生第二个 user；
  纯空会话不触发。REASONING-ECHO 只修了"回传"，没修"为什么会形成触发结构"。

**与 COST-2 缓存战果的冲突（本票核心难点）**：
- COST-2 动态块写回 history 是**前缀缓存命中率 99.8%（e2e_cost2_probe 实测）/
  ≥85%（e2e_cost3_probe）**的核心机制——写回后该 user 消息成为跨轮逐字节
  稳定的前缀一部分；
- 若简单"不写回"（动态块只在发送副本）→ 每轮组装时动态块内容变化
  （记忆 touch/NOW 小时级）→ 前缀可能不再逐字节稳定 → 缓存命中率回落
  （COST-2 实测过头部注入仅 3.4%）；
- **修 400 不能赔缓存**——本票必须带"改前/改后缓存命中率实测对比"验收。

## 施工项

### 1. 消除"双 user 夹工具轮"触发结构（核心）

目标：**history 中不出现"两个 user 消息之间夹工具轮"**，同时**保持前缀稳定**。
候选方案（施工时选一，需实测验证）：

- **方案 A：动态块不写回 history**——build_messages 中动态块附加前先深拷贝
  user dict（`dict(_m)` 副本再附加），不 mutate engine.history 原 dict；
  → 副作用：动态块不再成为跨轮前缀 → 缓存命中率需实测，若塌则弃用；
- **方案 B：动态块注入为 system 角色/非 user**——避免产生第二个 user 消息；
  → 需验证 DeepSeek 对"尾部 system 消息"的接受度（API 兼容性），且保证
    前缀稳定语义不变；
- **方案 C：保持写回，但保证"每轮只有开头一个 user"**——动态块附加时
  若 history 已有第二个 user（历史轮次写回的动态块），先合并/去重；
  → 改动最小，但需确认去重逻辑不与 COST-2 前缀稳定冲突。

**施工要求**：方案必须通过 ② 缓存实测 + ③ 400 复现测试双验收才算定案，
不许只修一个收工（L14 纪律）。

### 2. 缓存命中率实测（改前/改后对比，复用 P0-3 探针）

- 改前基线：`scripts/e2e_cost2_probe.py`（R2→R3 ≥60% 目标，实测 99.8%）+
  `scripts/e2e_cost3_probe.py`（长会话 ≥85%）实跑留档；
- 改后对比：同一探针改后实跑，**命中率不得低于改前**（或偏差在可解释
  范围内并写明原因）；
- 数据落盘（P0-3 的 data/logs/cache_probe_p03.json 同款或独立文件）。

### 3. 400 复现测试（防回归）

- 新增测试：构造"动态块 user + 工具轮 + 第二 user"的 history → 断言
  build_messages 输出**不含双 user 夹工具轮结构**（方案 C 语义）或
  **history 不被污染**（方案 A 语义）；
- 若可行：真实 gateway 冒烟——长会话触发动态块注入后多轮工具调用不 400。

### 4. 回归保障

- 全量 pytest 零失败（基线 2791 passed / 2 skipped / 1 xpassed + 新用例；
  cost1b 分支名环境失败为既有已知项）；
- TEL-8 守卫：injector.py 改动需特批登记 COST-6 标记；
- GUI-F8 折叠框（读 thinking）不受影响——若方案 A 动 history 写回，
  存档/恢复路径复查。

## 验收标准（终审逐条复跑）

1. 构造"双 user 夹工具轮"history → build_messages 输出不再触发结构
   （具体断言随方案定：无双 user / 无污染 / 已合并）；
2. **缓存命中率实测**：改前（e2e_cost2/3 探针）vs 改后对比，命中率不塌
   （数据落盘，报告写清前后数字）；
3. 真实长会话多轮工具调用不再报 reasoning_content 400（实弹或冒烟）；
4. 全量 pytest 零失败；
5. 收工报告落 `library/agent开发/TICKET-COST-6完成报告.md`
   （md5/git 实况/测试原话/缓存对比数据/方案定案理由）。

## 风险自查点

- **缓存红线**（P0-3 已闭合的未闭合项 #1）：本票方案不得破坏 COST-2/3
  战果——实测对比是硬验收，命中率回落必须解释或弃用方案；
- **DeepSeek 规则边界**：方案 B（system 角色）需实测 API 接受度；方案 C
  （去重）需确认去重后前缀仍逐字节稳定；
- **REASONING-ECHO 不回退**：echo 补字段逻辑保留（它是兜底，双 user 消除
  后正常场景不再触发，但保留无副作用）；
- **存档/恢复**：方案 A 若改 history 写回，恢复路径（GUI-F8 thinking、
  压缩、注入）全面复查；
- **write_obsidian 陷阱**：报告落 `library/agent开发/`（已错 7 次的教训）。

## 已完成取证（Kimi 定位结论，施工不必重复）

- 根因：injector.py:760 注释（共享引用写回）+ 769-787（动态块附加到最后
  user）+ events.jsonl 20:33:47（user#0→103 工具轮→user#104 → 400）；
- 复现结构：双 user 夹工具轮（P0-1 时 205→108 条、本次 163→164 条同模式）；
- REASONING-ECHO 已修回传（保留）；P0-3 探针可复用（scripts/probe_p0_3_
  cache.py / e2e_cost2_probe.py / e2e_cost3_probe.py）；
- 基线 pytest：2791 passed / 2 skipped / 1 xpassed；真实库 659 条。
