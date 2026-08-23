# Bobo 架构地图（Architecture Map）

> 一页纸的全貌快照。它不是教程，不写"怎么用"，只回答三个问题：**系统现在长什么样 / 数据怎么流 / 哪里已经超载**。
> 阅读链：`HARCHITECTURE.md`（宪法：原则与禁令）→ **本文（地图：现状全貌）** → `data/Agent开发手册`（清单：有什么）→ `docs/GUIDANCE.md`（行为：怎么做）。
> 维护规则见文末"刷新纪律"——**数字过期 = 地图作废**。

---

## 1. 鸟瞰：五个层次

```
┌─────────────────────────────────────────────────────────────┐
│  表现层    ui-tui/ (React+Ink TUI)   apps/desktop/ (Electron) │
│            ↕  JSON-RPC over Unix socket                      │
├─────────────────────────────────────────────────────────────┤
│  网关层    bobo_tui_gateway/  (server.py · entry.py)         │
│            唯一的 Python 入口；进程守护、60s 自动重启          │
├─────────────────────────────────────────────────────────────┤
│  引擎层    core/engine.py        状态机: IDLE→THINKING→       │
│    (大脑)  core/tool_runner.py   EXECUTING→RESPONDING→DONE   │
│            core/context.py       上下文预算与 L1/L2 压缩      │
├─────────────────────────────────────────────────────────────┤
│  通信层    core/llm_caller.py    SSE 流式 + 双看门狗          │
│    (嗓子)  core/provider.py      10 家 provider 声明式注册    │
├─────────────────────────────────────────────────────────────┤
│  能力层    tools/ (97 个文件, 16,353 行)                      │
│    (手脚)  自动发现注册; 51 个停放在 tool_park.json           │
└─────────────────────────────────────────────────────────────┘
   横切（不属于任何一层，但被各层调用）：
   安全: command_safety / file_safety / checkpoint / privacy
   记忆: v5_memory / obsidian_tools / skill_sedimenter / living_notes
   事件: event_bus / round_tracker / verifier / injector
```

**一句话架构**：两个前端（TUI、桌面）通过 Unix socket JSON-RPC 共享同一个 Python 网关进程，网关背后是一个显式状态机引擎，引擎驱动声明式的 provider 层和自动发现的工具层，安全与记忆作为横切面缠绕其间。

---

## 2. 一条消息的完整旅程（运行时链条）

以"用户在桌面端发一句话，agent 调工具后回答"为例：

```
用户输入
  → Electron renderer (apps/desktop/src)          聊天 UI
  → preload.cjs → main.cjs → gateway-socket.cjs   IPC 桥
  → Unix socket JSON-RPC
  → bobo_tui_gateway/server.py → handlers/        请求路由
  → core/engine_adapter.py                        引擎注册表 + 写审批门 + 中断管道
  → core/engine.py :: Engine.run()                外层循环（步数保险丝 MAX_STEPS，每步查中断事件）
  → core/engine.py :: _step()                     ← 全系统最大单体（约 580 行）
       ├─ core/context.py     组装上下文（token 预算、L1/L2 历史压缩、注入器）
       ├─ core/injector.py    动态注入（模式通告、技能标准、记忆）
       → core/llm_caller.py                       HTTP SSE 流式请求（headers/read 双看门狗）
            → core/provider.py                    按 provider 声明适配协议
       ← 流式返回（含 tool_calls）
       ├─ ToolRunnerMixin._execute_tool_loop()    两阶段：先确认/高危门，后并行执行
       │    ├─ core/command_safety.py             shell 风险分类（1,031 行）
       │    ├─ core/file_safety.py + checkpoint   写保护与回滚
       │    ├─ ThreadPoolExecutor                 并行执行，每工具独立超时
       │    └─ tools/*（若 spawn_worker）          子 agent：独立上下文的子 Engine
       └─ 循环，直到无 tool_calls → RESPONDING → DONE
  → core/event_bus.py                             全程事件流
  → gateway → socket → 渲染进程逐 token 渲染
```

**后台并行线程**（不在这条主链上，容易被遗忘）：
- `core/skill_sedimater.py` —— 记忆沉淀守护线程（对话产出 → 笔记/记忆）
- `core/proactive.py` —— 主动行为
- `tools/living_notes.py` —— 活笔记
- 桌面端 `widget`（只读投影小窗）——独立窗口，共享同一后端

---

## 3. 各层现状：载重表

> "载重"= 该模块当前承受的复杂度。**红线**是触发偿还的阈值，不是理想值。

### 引擎层（大脑）——⚠️ 超载
| 模块 | 行数 | 职责 | 状态 |
|---|---|---|---|
| `engine.py` | **2,209** | 状态机 + 验证器 + 门控 + 沉淀调度 | 🔴 `_step()` 约 500 行（office 快照闸已拆，2026-08-23 D1）|
| `injector.py` | 1,250 | 上下文动态注入 | 🟡 与 context.py 边界模糊 |
| `tool_runner.py` | 878 | 工具两阶段执行 | 🔴 特判 restore_checkpoint/cross_search，内嵌巨型 fallback 字典 |
| `context.py` | 934 | token 预算、L1/L2 压缩 | 🟢 结构清晰 |
| `engine_adapter.py` | 558 | 引擎注册表/审批/中断 | 🟢 |

<details><summary><b>_step() 组分图</b>（1,873–2,452 行，约 580 行的内部结构）</summary>

序曲（每步必查）：中断检查 + 守卫检查。然后按状态分派四个分支：

| 分支 | 行 | 组分 |
|---|---|---|
| IDLE | 1883–1891 | pre_input → user 落 history → THINKING |
| THINKING | 1892–2202 | 调 LLM → 有工具去 EXECUTING；纯文本走**收尾闸链**（下表） |
| EXECUTING | 2203–2389 | 编辑冲突检测 → 台账基线快照 → 工具循环 → 台账同步/补账嫌疑 → history 落账 → 全绿销账建议 → **tracker 记账**（改动/已读/模式，约 50 行，独立组分）→ 轮次计数 → THINKING |
| RESPONDING | 2390–2452 | 技能提议 → 计数器清零 → 工作区对账 → history 落账 → 引用追踪 → **终稿组装**（台账尾注/交接清单/思考块展示——展示层逻辑长在引擎里）→ complete |

收尾闸链（THINKING 内，按序）：

| # | 闸 | 行 | 票 | 类型 |
|---|---|---|---|---|
| ① | 空响应重试 | 1908 | — | 回注×1 |
| ② | 验证器 | 1927 | R3-c | 回注 |
| ③ | 沉淀派发 | 1943 | PERF-1 | 旁路 |
| ④ | office 快照比对 | 1975 | O3-1 | 旁路 |
| ⑤ | 承诺检测 | 1988 | 票Z缝2 | 回注×2→熔断 |
| ⑥ | 答复质量 | 2039 | R2b | 回注×1 |
| ⑦ | 补账检测+字段闸 | 2077 | O8-2/票C/L1 | 补账回注；字段放行附注 |
| ⑧ | 台账未销账 | 2137 | 票K v2 | 回注×2→熔断 |

</details>


### 通信层（嗓子）——🟢 健康
`llm_caller.py`（892，看门狗最扎实的模块）+ `provider.py`（370，声明式注册表，无 if-else 分支）。**这是全项目设计最好的层，新代码请向它看齐。**

### 能力层（手脚）——🟡 临界
- 97 个工具文件 / 16,353 行；其中 **51 个停放在 tool_park.json**（schema token 减 52%，但本质是"旧边界内腾挪"，不是工具选择机制）。
- 连接器（Obsidian/Notion/邮件/GitHub/日历）是**平铺工具模块，不是连接器框架**——引擎直接知道 Obsidian 语义（blocked folders、沉淀目标），每加一个连接器引擎都要跟着动。
- **无 MCP 支持**：扩展方式 = 改源码，只有作者本人做得到。

### 横切面——⚠️ 四处重复
风险分类逻辑存在于 **4 个地方**：`command_safety.py`（1,031）· `execute_terminal.is_dangerous` · `file_safety.py`（274）· `engine._auto_decide`/`_office_decide`。安全策略没有单一事实来源，每个新执行通道（如 computer use）都要再补一遍。

### 表现层——🟡 中游
- TUI（ui-tui/）：最成熟，但单体文件偏大（textInput.tsx 1,351 行、thinking.tsx 1,224 行）。
- 桌面（apps/desktop/）：electron 主进程小而干净（main.cjs 616 行）；已知债务 = 长会话渲染进程内存（GUI-F29 虚拟滚动重做中）、Cmd+Q 不总杀网关（GUI-F30）、无签名。

---

## 4. 边界清单：已被突破的假设

架构 = 一组假设。下表是当初的假设 vs 现在的现实：

| # | 当初的假设 | 现在的现实 | 突破产生的债 |
|---|---|---|---|
| 1 | **单 agent 体系**（owner 2026-08-23 澄清：子 agent 是当工具用，非架构换血——系统仍是单 agent，多 agent 不是本系统的体系） | spawn_worker 被当工具调用；duo 双 agent 已拆除（D1）；但 spawn_worker 的线程调度细节耦合进了 `_step()` | 债不在"多 agent"，在编排细节挤进主循环——流水线拆分战役正在处理 |
| 2 | 工具十几个，prompt 装得下 | 97 个工具文件 | tool park 补丁；缺真正的工具选择机制 |
| 3 | 安全是"执行命令前拦一下" | 四种执行通道（terminal/computer use/文件写/网络） | 风险分类 ×4 处，无单一策略引擎 |
| 4 | 连接器是工具层的事 | 引擎知道 Obsidian 语义、跨源搜索在 tool_runner 特判 | 引擎↔连接器耦合 |
| 5 | 单用户、单机、macOS、开发者本人 | 开源给陌生用户 | 冷启动/跨平台/错误可见性全缺位 |
| 6 | office/duo 模式是常用工作流 | owner 2026-08-23 终裁：使用效率不符预期，**已拆除**（TICKET-DEMOLISH-OFFICE-DUO，D1 代码层完成） | D2 前端痕迹、D3 数据工件/文档待清扫 |

**螺旋规则**（对应"功能迭代与架构迭代交替"）：每个 ticket 合入前问一句"它碰了地图上哪几个格子、哪个数字变了"；红线（`_step()` 行数、风险分类处数、工具数）一到，下一个功能必须排在偿还之后。

---

## 5. 刷新纪律（本地图的生命周期）

1. **每次合入 ticket**：若改动跨模块或使上表任一数字 ±5%，更新对应行。
2. **每两周一次"登高"**：重读本图 → 跑一次冷启动 → 决定下一个螺旋圈是功能还是偿还。
3. **红线触发**：偿还动作完成后，本图的载重表和边界清单必须同步更新。
4. 地图与代码不一致时，**以代码为准，当天修正地图**——过期地图比没有地图更危险。

---
*基线数字采集于 2026-08-23（wc -l 实测）。下一次复核时重新实测，不要沿用本文数字。*
