# 任务：duo 商讨模式编排代码化（硬触发 /duo → 确定性流程）

日期：2026-07-27。优先级：一轮定生死（做完看真实使用效果决定 duo 去留）。
前置：`docs/DESIGN_DUO_MODE.md`（设计）、`docs/TASK_DUO_SLASH.md`（已完成，
/duo 已注册为斜杠命令并透传对话管线）、duo skill 已上线。

## 背景与问题

duo skill（prompt 剧本）引导的商讨模式遵从不稳定：
- 09:43 真跑：spawn A → 转播 → spawn B → 清单 ✅（产出质量用户认可）
- 09:52 / 10:01 两轮假跑：主 Bobo 零 spawn_worker 调用，
  自己读 12~25 个文件后**分饰 A/B 两角**输出结论 ❌
  （access_log 铁证：spawn_worker 调用数全程无变化）

结论：核心流程不能赌模型自觉遵守。编排下沉到代码层：
**模型只负责出观点，流程由代码保证。**

## 总原则

1. **硬触发只认 `/duo` 斜杠命令**（server.py 已有 duo 分支，见下"入口"）。
   自然语言（"商讨一下"/"双员"）不进代码编排，继续走 skill 软引导，
   行为与现状一致，不会更糟。
2. **并联不改串联**：新增独立编排函数，普通对话管线、spawn_worker 既有行为、
   其他斜杠命令全部不动。验收含"非 duo 对话零行为变化"。
3. **本版只编排商讨模式**。实现验收模式（A 干活 B 验收）仍走 skill 软引导，
   不在本任务范围。

## 改动

### ① 新增 `core/duo_orchestrator.py`（主要交付物）

导出 `run_deliberation(question: str, emit, sid: str) -> None`，流程全确定性：

```
Phase 0 现状简报（代码执行，零 LLM）：
  - 直接 subprocess 跑 git log --oneline -15（cwd = 仓库根）
  - 读 README.md 前 100 行
  - 拼成 ≤10 行简报文本。任何一步失败就跳过，不阻断。
  （不用 LLM、不用工具管线，所以不存在"读 25 个文件 4 分钟"的失控）

Phase 1 派 A：spawn_worker.execute(
    instruction="就 <question> 提出你的方案。给出观点、理由、风险。",
    name="duo-A-propose", context=<Phase 0 简报>, allow_tools=False)
  完成后把 A 的结果原文通过会话消息流转播给用户
  （前缀 "▶ A 的方案原文"）。转播机制：向 session 消息流注入 assistant
  消息并 emit 对应事件，具体走 engine_adapter 现有事件通道，
  要求 TUI 里渲染为普通 assistant 文本，不是 thinking 灰字。

Phase 2 派 B：spawn_worker.execute(
    instruction="有人提出以下方案：\n---\n<A 的结果全文>\n---\n
      你的任务是挑刺：找出假设漏洞、遗漏场景、更优替代。
      只输出问题清单，不需要重述方案。",
    name="duo-B-critique", context=<Phase 0 简报>, allow_tools=False)
  同样原文转播（前缀 "▶ B 的挑刺原文"）。

Phase 3 汇总（唯一一次用主对话模型的步骤，二选一，实现者选简单的）：
  a) 用 worker 同款 llm_caller 发一个纯文本请求（无工具 schema），
     prompt = 决策清单模板 + A/B 全文；
  b) 或代码直接按模板拼装（共识/分歧/建议/待拍板留空由用户填）。
  推荐 a，模板沿用 data/skill-standards/duo/standard.md 的输出格式段。

超时：每个 worker 硬上限 90s（spawn_worker 超时参数化，见②）。
超时即失败，向用户输出明确错误（"A 超时，请重试"），不重试不降级为自演。
任何一步失败：输出失败原因，流程终止。禁止静默降级为"主模型自己演 A/B"。
```

### ② `tools/spawn_worker.py`：加 `allow_tools` 参数（向后兼容）

- `execute(..., allow_tools: bool = True)`，schema 的 properties 加同名可选参数。
- `allow_tools=False` 时：worker Engine 的 tool_executor 替换为桩函数，
  任何工具调用返回 `"[工具已禁用] 这是纯思考任务，请直接输出文字结论。"`。
  这样"禁工具"从 prompt 请求变成代码强制，worker 一轮出文字，速度可预期。
- `True` 时行为与现状完全一致（既有调用方零影响）。
- 顺带把 `_WORKER_TIMEOUT = 110` 变成 `execute()` 的可选参数 `timeout=None`
  （None 用现有 110/300 逻辑），编排器传 90。

### ③ 入口：`bobo_tui_gateway/server.py` 的 duo 分支改造

现状（TASK_DUO_SLASH 交付）：duo 分支透传 `handle_prompt_submit`。
改为：

```python
elif command == "duo" or command.startswith("duo "):
    rest = command[3:].strip()
    m = re.match(r'^(商讨|讨论)[:：]\s*(.+)$', rest, re.S)
    if m:
        # 商讨模式 → 代码编排（确定性流程）
        question = m.group(2).strip()
        # 仿照 handle_prompt_submit 的线程模式：
        # 后台线程跑 core.duo_orchestrator.run_deliberation(question, _emit, sid)
        # 主线程立即 return _ok(rid, {"output": f"双员商讨已启动：{question}"})
        # 会话不存在/is_running 检查复用 handle_prompt_submit 的前置逻辑
    else:
        # 实现验收模式等其他 duo 用法 → 维持现状透传 prompt.submit（skill 软引导）
        return handle_prompt_submit(
            {"session_id": sid, "text": f"duo {rest}".strip()}, rid)
```

注意 `import re` 的位置（本文件有过 import 位置坑，放函数顶部）。

### ④ `data/skill-standards/duo/standard.md`：降级为软引导说明

顶部加一段："/duo 商讨 已由代码编排保证（core/duo_orchestrator.py），
本文件仅用于自然语言软触发时的行为引导。"
状态机内容保留（自然语言触发时仍可参考）。

## 明确不做

- 不编排实现验收模式（A 干活 B 验收），仍走 skill。
- 不改 spawn_worker 既有调用方的任何行为（allow_tools 默认 True）。
- 不做 worker 间消息总线、不做跨 provider、不做自动触发。
- 不删 skill 文件。

## 验收

1. **铁证级**：TUI 输入 `/duo 商讨：bobo 未来架构的提升方向` 后，
   `data/access_log.jsonl` 必须新增恰好 2 条 `spawn_worker` 记录
   （duo-A-propose、duo-B-critique）——这是"真 worker"的硬证据，
   杜绝自演双簧。
2. TUI 里依次看到：双员商讨已启动 → ▶ A 的方案原文（全文） →
   ▶ B 的挑刺原文（全文） → 决策清单四段。转播是普通 assistant 文本。
3. 总耗时 ≤ 3 分钟（禁工具 + 90s 上限，应该远小于此）。
4. B 的挑刺内容与 A 的方案有真实交锋（B 确实读到了 A 的文本）。
5. 自然语言"duo 商讨：xxx"（不带斜杠）行为与现状一致，不触发代码编排。
6. **非 duo 对话零行为变化**：普通问答、其他斜杠命令、
   普通 spawn_worker 使用场景全部回归正常。
7. `pytest tests/ -q` 全绿；新增编排器单测（mock llm_caller：
   A 先于 B、B 的 instruction 含 A 文本、allow_tools=False 时工具桩生效、
   超时路径输出明确错误）。
8. `python3 -m py_compile` 所有改动文件通过（交付底线，上次翻过车）。

---

## 追加返工（2026-07-27 10:41，用户发现）

### Phase 0 简报加话题闸门（默认跳过）

问题：`run_deliberation` 里 `briefing = _briefing()` 无条件执行——
讨论哲学问题时 A/B 的 context 也会塞入 bobo 的 git log，
不仅无用还可能污染视角（把理念问题带向工程方向）。
skill 版设计原文是"仅当问题涉及具体项目/代码库时"才跑 Phase 0，
代码化时条件丢失。

修法（`core/duo_orchestrator.py`）：

```python
# 简报是特例不是默认：只在问题命中项目信号时执行 Phase 0
_PROJECT_SIGNALS = ("bobo", "代码", "架构", "仓库", "引擎", "engine",
                    "worker", "skill", "tui", "代码库", "项目")
if any(sig in question.lower() for sig in _PROJECT_SIGNALS):
    briefing = _briefing()
else:
    briefing = ""
```

误判代价不对称，宁漏勿滥：项目讨论漏简报只是退回旧版水平，
理念讨论误塞简报会污染输出。

### 验收（追加）

9. `/duo 商讨：AI 应该拥有权利吗` → A/B 的 spawn context 为空，
   TUI 中不出现"现状简报"段。
10. `/duo 商讨：bobo 未来架构方向` → 简报正常出现（回归）。
11. 新增测试：哲学问题断言 spawn 的 context 参数为空字符串。
