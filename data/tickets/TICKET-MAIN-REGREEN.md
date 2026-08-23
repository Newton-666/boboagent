# TICKET-MAIN-REGREEN

> 类型：测试体系偿还（main 修绿）
> 开票：2026-08-23 · 施工：ZCode（owner 授权，可快修即修，卡住测试先放）
> 现状：main 全量 2813 过 / 61 败 / 2 跳过 / 1 xpassed（3 分 18 秒）
> 依据：D1 验收时的 stash 对照证明 61 败全部为 main 存量（与 TICKET-DEMOLISH-OFFICE-DUO 无关）
> 红线：**红色 main = 回归信号失效**（红了等于没红）——修绿后新失败必须能显形

---

## 1. 失败分拣（61 项 → 类别）

| 类 | 代表性文件 | 错误特征 | 处置 |
|---|---|---|---|
| A. FakeCtx 缺属性（机械，快修） | goal_gate、gui_f6/f7/f8/f9/f11/f24、desk_v2a/v2b/v2b3/v4/v4b/p1/tel | `FakeCtx has no attribute computer_use_mode` 等——老测试的假上下文没跟上新会话字段 | **本票修** |
| B. 行为断言过时（需判研） | eng1_reply_finality、scan_l3c/l3b/l3_connect、skill_audit、e4a、perf_1、core_int2、note_pointer、cost1b、computer_use_core | 事件链/注入行为与当前实现不一致（如 takeaway.skipped vs extracted） | **本票逐个判研**（改动侧已确认非 D1 所致） |
| C. 数值/校准漂移 | tool_park_1（schema 税 4286 vs 3997±5%）、cost1a_sandbox | 工具集变化后校准值过时 | **本票重校**（确认 pre-D1 也败，属存量） |
| D. 环境敏感（live/socket，卡住风险） | headers_watchdog、headers_watchdog_live | 真开 socket、时序依赖 | **暂缓**（owner 2026-08-23：先放，修完他类再议） |

## 2. 验收

- 本票目标：A/B/C 类全修，main 从 61 败降到只剩 D 类（watchdog 家族）；
- 每类修改跑对应文件回归 + 全量一次（3 分钟）确认总数下降；
- D 类处置单独向 owner 汇报后再定（隔离/标记/重写）。

## 3. 施工纪律

- 不引入新行为：测试修复 = 让测试反映当前实现，不改实现迁就测试（除非判研确认实现有 bug）；
- 每处修改标注票号；分批提交，各配回滚；
- 卡住测试不硬等：单类超时即停手汇报（owner 明确：不在本任务花数小时）。

---

## 4. A 批施工汇总（2026-08-23，提交 24c855c5）

**已修**：A 类 FakeCtx 补属性（9 文件，~30 测试转绿）；治理守卫登记 TICKET-DEMOLISH-OFFICE-DUO
授权（v4/v4b/tel_8/p1，守卫未削弱）；v2b3_5 移除 /duo 断言；stash 遗留（duo_orchestrator 删除
入索引）。
**验证**：14 相关文件 152 过 / 5 败（5 败均为 main 存量：v4b0_2/v2b3_1/css×2/goal_gate）。
**未做**：B 类行为断言 ~15；C 类校准 ~4；前端存量 ~8（需前端票）；D 类 watchdog ~10（暂缓，
处置待议）；修绿后全量复跑（待确认）。
**修正记录**：早期"61 全为存量"结论错误——全量分拣后确认其中 6 个为 D1 合法改动触发守卫
（属授权登记问题，非行为变坏）；行为基线 diff=0 证明 D1 无行为回归。
