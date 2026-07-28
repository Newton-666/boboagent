# 票 K v2 · 任务台账（Task Ledger）— 半路停治本 + auto 不停机地基

> 立案：2026-07-28 半路停根因鉴定（bobo.log 尸检：15:34:19 RESPONDING emit len=28 → done，零错误零异常——LLM 说"等 30 秒再拉取"然后回合自然死亡，引擎无"任务未完成"概念、无自我唤醒、无遗言规矩）。
> 定位：中型战役。auto 模式四难关中 Harness 约束 / 监控 / 不停机三关的共同地基。优先级高于全部小票。
> 纪律：票 ≠ 开工令。本票由 Kimi 终审立项，bobo 领票后开工。

## 一、病因（禁止跳过的背景）

`core/engine.py` 的回合终止条件只看 LLM 是否返回不带 tool_calls 的文本。模型随时可以用一句"我待会儿继续"结束回合——引擎把它当收工。已实测三次复发（10:30 len=216、15:34 len=28、上午 36 分钟绕行）。**修复目标：引擎收工与否由账本决定，不由模型嘴决定。**

## 二、四个子系统（按依赖顺序实施）

### ① 台账本体（core/engine.py）

- Engine 新增 `self.task_ledger: list[dict]`，结构 `[{"id": str, "title": str, "status": "pending"|"in_progress"|"done"}]`
- 上限 20 项，防失控
- 随会话持久化（session 保存/加载时带上台账字段；旧会话无此字段 → 空台账，不报错）
- 新回合开始（用户新输入）时**不清空**——台账生命周期跨回合，直到全部 done 或用户明确要求废弃

### ② 读写工具（LLM 的手）

- 新工具 `task_ledger`，actions：`create`（建账，整本替换）、`update`（按 id 改 status）、`list`（查账）
- 注册进工具体系，system prompt / skill-standards 加一条规矩：**多步任务开工先建账，完成一项立即销账**
- 台账变更必须写事件：`task.check` → events.jsonl（含 action、item_id、title、status）

### ③ 收工闸（引擎执法，票 K 的核心）

- RESPONDING 收到终稿（无 tool_calls 的文本）时查账：
  - 台账存在未 done 项 → **不进入 done**：回注一条 user 角色消息（固定文案："任务台账还有 N 项未完成：{标题列表}。请继续执行，不要说明、不要道歉，直接继续。"）→ 回 THINKING
  - 连续回注 **2 次** 台账仍无进展（未 done 项集合不变）→ 放行 done，但终稿前必须自动附加黄灯遗言：`⚠️ 台账 {N} 项未销账，引擎放行：{标题列表}`
  - 台账为空（LLM 没建账）→ 直接放行（v2 不强制建账，只统计：写一条 `task.no_ledger` 事件，供后续观察无账任务比例）

### ④ 透明化

- TUI 常驻台账面板：显示各项 status 图标（⬜/🔄/✅），随 `task.check` 事件刷新
- 若 TUI 面板工作量过大，允许降级为：RESPONDING 终稿尾部自动附台账摘要行（`📋 台账: 3/5 done`）。**降级需 Kimi 批准，默认做面板**

## 三、验收金标准（逐条物理验证）

1. **续跑复活（核心）**：e2e 测试——FakeLLMCaller 第一轮返回"我先等 30 秒再拉取结果"（无 tool_calls，台账有 pending 项）→ 引擎必须回注并再调 LLM，第二轮返回正常收工 → 全程未 done 中断
2. **两次熔断**：FakeLLMCaller 连续 3 轮都返回文本且不销账 → 第 2 次回注后放行，终稿含 `⚠️ 台账` 遗言
3. **干净收工零误伤**：台账全 done → 正常 done，无回注、无遗言
4. **无账放行**：台账为空 → 直接 done + `task.no_ledger` 事件落盘
5. **持久化**：建账后 save/load 会话 → 台账原样恢复
6. **事件流**：create/update 各触发 `task.check`，events.jsonl 可回放（json.loads 逐行通过）
7. pytest 全绿（基线 892）+ 活体冒烟 6/6
8. 五查汇报含第 6 项「是否需重启」+ 附 `git status` 原文

## 四、边界与禁止项

- 禁止用正则匹配终稿文本判断"是否要继续"（那是票 K v1 的废弃方案）
- 禁止引擎替 LLM 销账（打勾只能来自 task_ledger 工具调用）
- 禁止回注超过 2 次（防死循环，这是硬熔断）
- 分支 `feat/task-ledger`，本地 merge 需 Kimi 终审通过，**禁止 push**
- 改动 core/ 必须重启 bobo 生效，汇报时明确提醒
