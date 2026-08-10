---
ticket: TICKET-C
title: AUTO MODE 收官票——台账字段化 + 收工闸 auto 硬拦
branch: feat/ticket-c
status: 待施工
author: Kimi 开票（依据 bobo 只读核实报告 2026-08-10 + v0.5/v0.6 设计共识）
date: 2026-08-10
authorized_paths:
  - tools/task_ledger.py
  - core/engine.py
  - tests/
---

# TICKET-C 台账字段化 + 收工闸 auto 硬拦（AUTO MODE 收官票）

## 一、定位

AUTO MODE 最后一块拼图。前序票把"执行中"的弹窗消灭了；本票消灭"收工时"的注水——auto 下台账项必须带结构化字段，缺字段**永不放行**。

## 二、最高验收原则（同 O-1，凌驾一切）

**普通模式零影响**：非 auto 模式收工行为与施工前逐字节一致；每条验收配普通模式对照组。

## 三、两项 owner 裁决（已含，开票即生效）

1. **老格式台账（{id,title,status} 无新字段）在 auto 下**：视同缺字段，硬拦，不设迁移豁免。依据：bobo 实测全仓库 0 个存量台账（data/sessions 2 文件 0 台账、workspace 全 None），无历史包袱。
2. **C-1 熔断后放行**：auto 下缺字段硬拦**不适用** `_ledger_reinject_count < 2` 的熔断放行——缺字段是格式违规不是"做不完"，用独立的 deny 计数；deny 不限次数，agent 的唯一出路是补齐字段或 update 删除该项；用户的出路是 ESC（已有）。

## 四、施工内容

### C-1a 载体：schema 加可选字段（tools/task_ledger.py:179-220）

- TOOL_SCHEMA 的 items 新增两个**可选**字段：
  - `verify`（string）：这项怎么算做完、怎么验证（创建时填）
  - `evidence`（string）：完成证据（标 done 时填）
- 工具 execute 语义（create/update/list）逐字节不变；`_validate_item` 不新增必填校验（字段校验全部放收工闸，工具只做载体——设计共识）。
- 普通模式下 LLM 填不填都照常工作。

### C-1b 收工闸 auto 硬拦（core/engine.py 收工闸段 1443-1520）

- 在现有"pending 回注 / 熔断放行"判定**之前**插入 auto 分支（读取 `self._auto_mode_getter()`，同 _confirm 用法）：
  - auto **off** → 直接跳过本段，走原链路（物理隔离，普通模式连判定都不经过）。
  - auto **on** → 扫描台账，任一 item 命中以下任一条件即"缺字段"：
    1. 缺 `verify` 或为空
    2. `status == "done"` 且缺 `evidence` 或为空
  - 缺字段 → **deny 收工**：不回注提醒、不放行；向 history 追加严格指令（指明哪个 item 缺哪个字段，要求用 task_ledger update 补齐，或删除该项）；写审计事件 `goal_gate.deny`（含 sid、缺字段明细：item id + 缺哪些字段）。
  - deny 计数独立（`self._ledger_field_deny_count`），与 `_ledger_reinject_count` 互不干扰；缺字段 deny **无熔断放行**（裁决 2）。
  - 台账全合规 → 跳过本段，走原链路（原回注/熔断逻辑在 auto 下对"未完成项"照常有效）。
- 台账为空（无账回合）在 auto 下的行为**不变**（本票只管有账时的字段质量，不管建不建账——那是工作习惯问题，另行处理）。

### C-1c 测试（tests/test_ticket_c_ledger_gate.py）

对照组四组起步：

1. auto on + 全字段合规 → 收工放行，行为与原链路一致
2. auto on + 缺 verify → deny 收工 + 审计明细 + 连续 3 次 deny 仍不放行（无熔断）
3. auto on + done 缺 evidence → deny；补齐 evidence 后放行
4. auto off（普通模式）+ 缺字段 → 收工行为与施工前一致（对照组，零影响铁律）
5. 老格式台账（无新字段）在 auto 下 → 按缺字段硬拦（裁决 1）
6. 审计事件字段齐全（type/sid/item 明细）

## 五、验收清单

1. 上述 6 组测试全过
2. 工具 execute 语义零变化（既有 task_ledger 测试全过，一个断言不许改）
3. 全量 pytest 零回归（基线 1815 passed / 2 skipped）+ 新增全过
4. 真实库三文件 md5（data/knowledge_base.json / library/MEMORY.md / library/index.md）跑前跑后一致
5. 五查汇报附**测试原始输出文本**（新纪律：报数必须可复核，不接受孤证数字）

## 六、纪律

- 分支 `feat/ticket-c`（自最新 main 99094e0 切出）；未终审不 merge 不 push；commit 前 `git branch --show-current` 核对（本季度第三次落错分支将直接进首考错题）。
- 不做：task_ledger execute 语义、普通模式任何行为、前端、无账回合策略。
- 施工前先重读本票 + 自己的核实报告；与票有出入以票为准并在汇报中说明。
