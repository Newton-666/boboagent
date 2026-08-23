# 设计草案：_step() 收尾闸流水线化（Step Pipeline）

> 状态：**草案，待 owner 批准。本文档不含任何代码改动。**
> 所属战役：`_step()` 拆解 · 第 1 圈（共 N 圈，N 待本圈结束后决定）
> 阅读链：`ARCHITECTURE-MAP.md` §4 边界清单（本圈偿还假设 1/3 的部分债务）
> 风险对策依据：2026-08-23 对话确认的五条风险（行为漂移 / 契约设计 / 时序语义 / 半途而废 / 认知地图）

---

## 0. 为什么从收尾闸下手（而不是从别处）

> **2026-08-23 owner 战略裁决：office 模式与 duo 模式决定移除**（使用效率不符预期）。
> 本设计因此增加**前置圈**：先拆模式，后拆函数——给准备拆除的房间重新装修是双倍浪费。

**前置圈（独立 ticket，先于本圈）：移除 office / duo 模式**
- 拆除对象：`engine.office_role` 全部判断、S2 闸（office 快照比对）、S5/S7 的 office 激活分支、
  `_verify_snapshot`/guardsnap 机制、gateway 的 `get_office_on`、duo_orchestrator。
- 收尾闸链预计 8 闸 → 6 闸（S2 消失，S5/S7 仅剩 auto 分支）。
- **显式裁决点（不得顺带滑过）**：宪法 Principle 4"快照抓漏"源于真实事故（前拦截实测仅
  60-70%），其保护对象若只剩 auto 模式，原则保留与否需 owner 单独裁决并记入宪法修订，
  不随模式删除顺带作废。

实读 `engine.py::_step()`（1,873–2,454 行段）后确认：收尾段**已经是事实上的流水线**——一串
ticket 战役（PERF-1 / R3-c / 票Z缝2 / R2b / 票C / O8 系列）各自往 THINKING→RESPONDING 的
过渡点插入了一段逻辑，段间靠 `self._pending_content`、`return`、计数器 flag 耦合。
这意味着：

- 拆它**不是重新设计，而是给已排队的逻辑发工牌**——行为漂移风险最低的切入点；
- 它是 `_step()` 里最大的一块（估计 300+ 行），拆完 `_step()` 降到约 250 行，红线压力立减；
- 每段都有现成的 ticket 回归测试（test_ticket_* 家族），保护网现成。

**明确不在本圈范围**（记 backlog，防"顺便"）：
- 悬浮段（空响应重试 / verifier）——已并入本圈（S0a/S0b，2026-08-23 修订）；
- EXECUTING 的 tracker 记账段（2,329–2,380，约 50 行独立组分）——与收尾闸同性质（"执行后观察者"），留第 2 圈；
- RESPONDING 的终稿组装（台账尾注/交接清单/思考块展示）——**展示层逻辑长在引擎里**，边界清单假设 5 的新证据，独立战役；
- 四处风险分类合并——独立战役；
- tool_runner 的 fallback 字典与特判——独立战役。

## 1. 现状清单：收尾段现有 8 个闸（迁移对象）

以代码出现顺序（engine.py 1,908 起），每闸 = 未来一个 Stage：

| # | 段（票） | 职责 | 决策类型 | 现有测试 |
|---|---|---|---|---|
| S1 | 沉淀派发（PERF-1） | 收尾时派发后台沉淀线程（test_mode 同步） | fire-and-forget，**永不拦截** | test_engine_core（E4a）|
| S2 | 快照比对（O3-1） | office 会话收工 md5 审计，**只告警不拦截** | append-only 警告文本 | O 系列票测试 |
| S3 | 承诺检测（票Z缝2） | 未来时承诺 + 无施工证据 → 回注 THINKING | **可拦截**（回注/放行/熔断三路） | 票Z/R3 测试 |
| S4 | 答复质量（R2b） | 台账腔/思考落纸检测 → 回注一次 | **可拦截**（每回合限 1 次） | R2b/R3-b 测试 |
| S5 | 补账检测（O8-2） | auto/office 批量创建即全 done → deny | **可拦截** | O8 测试 |
| S6 | 台账字段质量（票C/L1） | 字段质量 pass-with-note | **放行附注** | 票C/L1 测试 |
| S0a | 空响应重试（1,908） | 空响应回注一次，两次报错 | **可拦截** | engine_core |
| S0b | 验证器（R3-c，1,927） | 声称完成零工具 → 回注 | **可拦截** | R3 测试 |

> 2026-08-23 修订：实读全部 580 行后由 6 闸更正为 8 闸（补入 S0a/S0b）。
> S0a/S0b 在收尾闸链最前端、结构上同属"生成后决策"，一并纳入（批 4 迁移）。

关键观察：8 个闸只有两种交互模式——**拦截（回注 THINKING + return）** 和 **旁路（append 警告 / 派发线程）**。契约只需覆盖这两种，这就是"对着全部实现一起设计契约"的答案。

## 2. Stage 契约（保守版）

```python
# core/steps/base.py（新）
class StepStage:
    name: str                      # 事件/日志里可辨认（如 "promise_gate"）

    def run(self, ctx: StepContext) -> StageResult:
        """ctx 只暴露收尾闸需要的东西（见下）；禁止摸整个 engine。"""

class StepContext:                 # 只读视图 + 明确的白名单写口
    pending_content: str | None    # 读
    history                         # 读
    round_tool_exec_count: int      # 读（施工证据判定用）
    round_had_write_tool: bool      # 读
    office_role / auto_mode: bool   # 读
    # 写口（显式、可审计，取代散落的 self._xxx）：
    def append_warning(text)        # S2/S3/S6 放行时附告警 —— 唯一的文本写口
    def request_reinjection(msg)    # S3/S4/S5 拦截：回注 user 消息 + 回 THINKING

class StageResult(Enum):
    PASS          # 继续下一闸
    REINJECT      # 已回注，_step() 立即 return（对应现在的 return 路径）
    # 注意：没有 SKIP——条件不满足就是 PASS 直接返回（现状语义）
```

**契约要点（对应五条风险）：**

1. **顺序即注册顺序**，pipeline 是固定有序列表，不用权重/优先级魔法——现状六闸顺序
   即初始注册顺序，迁移动 = 行为等价。
2. **中断语义**：六个闸全在回合收尾点，无流式输出、无并行段，天然原子——
   中断检查点不变（闸前/闸后各一次，与现状一致）。此条写死在 base.py docstring。
3. **失败语义**：Stage 内部异常 → log + `notes.error` 事件 + PASS（旁路），
   **任何闸坏了不拦收工**——与现状 PERF-1 的"失败只留事件不影响回合"一致。
4. **计数器归属**：`_ledger_reinject_count`、`_reply_quality_reinject_count` 等
   防死循环计数器移入对应 Stage 自身（每闸自限），engine 不再持有闸的私有状态。
5. **禁止项**（写给未来的自己）：Stage 不得 import engine；不得写 history
   （只能 request_reinjection）；不得直接起线程（S1 的线程派发收在 Stage 内部但通过 ctx 事件）。

## 3. 快照基线（动代码前的第一件事）

1. 用 `tests/mock_llm.py` 写 6 条固定剧本会话，每条命中一个闸的正/反路径
   （含 promise 回注、quality 回注、office snap 告警、沉淀事件）；
2. 跑现 engine，落盘每步的：事件序列（events.jsonl 摘要）+ history 全文 + 
   `_pending_content` 终值 → 存 `data/eval/step_baseline/`；
3. **迁移完成的唯一验收标准：同剧本重跑，diff = 0**（时序差异除外——S1 后台线程
   的到达时间允许不同，事件集合必须相同）。

## 4. 分批迁移计划（每批一个 ticket + 回滚 tag）

> 前提：前置圈（office/duo 移除）已合入，收尾闸链为 6 闸（S2 已随模式删除）。

| 批 | 内容 | 验收 |
|---|---|---|
| 0 | 建**行为基线** + `steps/base.py` 骨架（engine 未接） | 基线落盘，骨架单测 |
| 1 | 只迁 **S1（沉淀派发）**——永不拦截、含 test_mode 分叉，风险最小的存活闸 | 基线 diff=0，E4a 测试绿 |
| 2 | 迁 **S4（质量闸）**——第一个拦截闸 | 基线 diff=0，R2b 测试绿 |
| 3 | 迁 S3、S5（auto 分支）、S6、S0a、S0b | 同上 |
| 4 | 删 `_step()` 内旧段，`_step()` 收尾段缩为 `for stage in pipeline` | 地图数字更新 |

**第 1 批合入后即触发"当场决定"**（防半途而废协议）：继续第 2 批 / 暂停在
"半流水线但稳定"状态并在 ARCHITECTURE-MAP 记录停在 X/N。每批独立可回滚——
任一批失败只回滚该批，不牵连。

**注**：原第一批候选 S2（office 快照闸）因模式移除而作废，改为 S1。
术语修订：全文"快照基线"改称"**行为基线**"，与 office 模式内部的"快照比对闸"区分。

## 5. 完成线与本圈退出条件

- 本圈完成 = 批 4 合入（全部存活闸入流水线）**或** owner 明确决定停在 X/N；
- 退出时更新 `ARCHITECTURE-MAP.md`：`_step()` 行数新值、横切面"四处风险分类"
  不变（不在本圈）、边界清单假设 1 状态；
- 本圈**不产生**的行为承诺：回复内容、事件序列、时序与现状完全一致——
  这是验收标准，不是目标，目标只是结构。
