# Engine 职责分析与模块归属（Engine Responsibility）

> 依据：`core/engine.py` 实读（2026-08-23，2,208 行）+ 第一原则"模块纯粹性"（owner 2026-08-23 定调）。
> 用途：`_step()` 流水线圈、computer use 政策圈、循环检测圈、沉淀接口圈的共用设计依据。
> 基线注意：本分析随 engine 演化失效，改动 engine 结构后按 ARCHITECTURE-MAP 刷新纪律更新。

---

## 1. Engine 的不可缩内核（六项职责）

| # | 内核职责 | 对应代码 |
|---|---|---|
| 1 | 状态机迁移 + 回合循环 | `run()`（外层保险丝循环）+ `_step()`（四分支分派）+ `_check_guards()` |
| 2 | 上下文组装与维护 | `history`、`_append_to_history`、压缩编排（经 ContextMixin + injector） |
| 3 | LLM 调用编排 | `_call_llm()`：流式、重试、reasoning 消费、空响应处理 |
| 4 | 工具执行环驱动 | ToolRunnerMixin：确认门 → 并行 → 超时 → fallback |
| 5 | 安全决策链统一入口 | `_confirm()`：唯一执法点，所有工具过它 |
| 6 | 回合收尾控制流 | 放行/回注的调度权——谁收尾、何时回注、深度计数 |

**要点**：收尾闸的执法权属 engine（唯一调用者 + 放行决定），执法逻辑不属 engine（第一原则推论）。

## 2. 模块归属裁决（四档）

### A 档：内核（留）
上表六项。engine 保留的每一行都应只属于这六项之一。

### B 档：政策（拆）——engine 无它们也能运转，它们是挂在 engine 上的纪律
| 现行位置 | 内容 | 归属 | 计划圈 |
|---|---|---|---|
| `_step()` 收尾段 | 承诺/质量/补账/字段/台账 5 闸（约 200 行） | 独立 Stage（流水线） | 流水线圈（已定，见 DESIGN_STEP_PIPELINE） |
| `_cu_active`/`_degrade_decide`/`_cu_error*`/`_cu_system_prompt`/`_cu_llm_kw`（约 90 行） | computer use 降级判断（工具之上的政策） | 独立 policy 模块；`_confirm` 只调一个接口 | computer use 政策圈 |
| `_round_sig`/`_has_progress_signal`/`_judge_loop_verdict`/`_last_n_tool_rounds`（约 60 行） | 循环检测逻辑（round_tracker.py 独立类已存在，有内嵌重复嫌疑） | 并入 round_tracker | 循环检测圈 |
| `_takeaway_worthy`/`_extract_takeaways`（约 50 行） | 沉淀价值判断 + 提取 | 搬入 skill_sedimenter 接口 | 沉淀接口圈 |
| `_workspace_recon`（约 30 行） | 收工对账（只读 git 侧写） | 独立 | 可随流水线圈 |

### C 档：可议（二期，不在近期圈）
- `_auto_decide` 决策体（约 70 行）：一半分类政策（可在 command_safety）、一半要写 audit+快照。拆需设计薄壳接口，风险中等。
- teaching mode 全套：engine 功能子集，与状态机耦合不深不浅。

### D 档：组合的辅助（已是正确方向，防反噬）
`verifier`/`checkpoint_mgr`/`tracker`/`proactive`/`injector`/`skill_loader` 均为独立类实例——engine 该有的形态（内核 + 注入组合）。
⚠️ 黄灯：`injector` 已 1,250 行，与 context 边界模糊（ARCHITECTURE-MAP 载重表已标），防反噬优先级高。

## 3. 解耦顺序建议

按体积 × 风险排序：
1. 收尾 5 闸（~200 行，风险最低——已定流水线圈）
2. workspace_recon（~30 行，纯只读，可并入流水线圈）
3. computer use 政策（~90 行，中等）
4. 循环检测（~60 行，并入既有类，低）
5. 沉淀提取（~50 行，搬既有模块接口，低）

全部拆完后 engine 预计 2,208 → ~1,700 行，且每行只属六项内核之一。

## 4. 判定准则（拆分的运行时判据）

1. **职责归属**：该逻辑属于 engine 六项内核之一吗？（第一原则，最高优先）
2. **状态归属**：有私有计数器/私有状态 → 倾向独立模块。
3. **耦合方向**：只读回合数据快照可出；动 engine 内脏（history/深度/return 控制流）须留。
4. **控制流 vs 决策**：决策可纯函数化；决策后的收尾动作（清计数/发事件/return）是 engine 胶水。
5. **代码量不作拆分依据**——代码量是"精简"话题，与拆分无因果关系（owner 2026-08-23 明确）。
