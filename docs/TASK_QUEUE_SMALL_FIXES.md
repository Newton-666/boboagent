# 排队小票合集（2026-07-28 验收后遗留）

> 来源：e2e 返工验收 + 日志巡检。三张票互相独立，可分别派发。
> 均建议走 L2 级（duo B 验收），不紧急。

---

## 票 A：FakeLLMCaller 加协议严格校验

**背景**：e2e 测试台 `tests/test_engine_e2e.py` 的 FakeLLMCaller 不校验传入 messages 的 tool_calls 配对。`test_real_interrupt_in_executing_phase` 中，tool 结果丢失后 engine 带孤儿 history 调了第二次 LLM——真实 API（OpenAI/Kimi/DeepSeek）在此刻会返回 HTTP 400，但 Fake 静默放行。这复刻了 2026-07-27 崩溃案现场（孤儿 tool_calls → 400），测试台却照不亮它。

**任务**：给 FakeLLMCaller 增加可选的严格模式（建议默认开启）：
- 每次被调用时扫描传入 messages，凡 assistant 消息含 tool_calls，必须存在对应 tool_call_id 的 tool 消息，否则抛异常（模拟 HTTP 400）
- 受此影响的既有测试若依赖"脏 history 继续跑"，显式标注并改走清洗后再调用

**验收**：
1. 新增测试：构造带孤儿 tool_calls 的 messages → Fake 抛 400 类异常
2. 既有 25 条 e2e 测试全绿（必要时调整）
3. pytest 全量绿

---

## 票 B：proactive.py 断链 import

**证据**（bobo.log 反复刷）：
```
core/proactive.py:54  from core.llm_caller import call_llm
ImportError: cannot import name 'call_llm'
```
`core/llm_caller.py` 中不存在 `call_llm`（与 7-27 `_skill_mgr` 断链同型：接口重构后调用点没跟上）。后果：主动建议的语义过滤功能静默失效。

**任务**：
1. 查清 llm_caller 当前真实接口（大概率是 `create_llm_caller` 工厂），改接
2. 给 `_semantic_filter` 加最小回归测试：mock caller，验证过滤路径可走通
3. 日志中该 ImportError 消失

**验收**：上述 3 条 + pytest 全绿。

---

## 票 C：proactive.py track_citation 类型混淆

**证据**：
```
core/proactive.py:202  mem.get("id", "")
AttributeError: 'str' object has no attribute 'get'
```
`track_citation` 遍历的记忆列表里混进了字符串（预期 dict）。疑似某条记忆的存储格式是裸字符串，或加载路径某处返回了 str 列表。

**任务**：
1. 定位混入口：打印/检查记忆列表中 str 元素的来源（存疑：knowledge_base 旧格式遗留 or 某写入路径未包装 dict）
2. 修复根因（推荐）或防御性跳过 + 记 warning（保底）
3. 加回归测试：列表混入 str 时不 crash

**验收**：日志中该 AttributeError 消失 + 回归测试 + pytest 全绿。

---

## 票 F：v3 闸过度拦截字符串内容

`echo "git commit ..."` 等字符串内容含 "git commit" 时会被 v3 闸误拦（过度拦截方向，影响小）。优化方向：命令分段解析（&&/;/| 分段后只对真实命令段判闸）。优先级低。

---

## 票 G：self-repo 闸改硬拒绝通道（闸语义修正）

**背景**（2026-07-28 实证）：v2/v3 闸（push/reset --hard/clean -f + main commit）判定逻辑正确，但执行语义接进了 `tool_runner.py` 通用"高风险 → 确认框 → 用户同意即放行"管道。闸装上后一分钟内，bobo 在 main 上直提两个 commit（32bbec9、1763b04）——确认框被同意即穿闸。设计本意是"self-repo 这些操作**只有用户在终端能做**，bobo 做了应直接拒绝"，当前退化为"请示"。确认疲劳使软闸必然失效。

**任务**：
1. `core/command_safety.py` 的 self-repo 闸判定结果需区分类别：新增返回/标记（如 `_is_self_repo_gated(command)` 统一入口），与"高风险需确认"区分开
2. `core/tool_runner.py`：self-repo 闸命中时**不进入确认流程**，直接生成 tool_result 错误返回给 LLM："🚫 此操作仅限用户在终端亲自执行（self-repo 保护），请通知用户手动操作后重试"——bobo 收到错误后应向用户说明，而不是等待确认
3. 通用高风险确认流程（其他危险命令）不受影响
4. 回归测试：mock 场景验证 self-repo 闸命中时 _confirm 不被调用、tool_result 为拒绝文案；通用危险命令仍走确认

**验收**：
1. 新增测试：self-repo main commit → _confirm 未被调用 + 拒绝文案；self-repo push → 同上；普通 dangerous 命令 → 仍走 _confirm
2. 真撞验证（Kimi 终审）：main + 闸代码落位，模拟 tool_runner 调用链确认无确认弹窗、直接拒绝
3. pytest 全绿 + 五查汇报 + feat 分支（feat/gate-hard-block）

**注意**：此票改的是"闸的执行语义"，判定逻辑（v2/v3 正则与条件）不许动。

---

## 票 D：main 直提物理闸（self-repo commit 拦截）✅ 已完成（merge f12a3eb，2026-07-28；穿闸修复 1194932）

**背景**（纪律档案第 6 种违规）：2026-07-28 duo B 二审打回后，bobo 直接在 main 上 commit `6393deb`（原地修复原地提交，未走 feat 分支）。与 TICKET-012 同病型："打回修复"场景下条件反射续命，merge 后原分支没了就直接长在 main 上。文字标准约束此类条件反射场景已被证明滞后，需物理闸。

**任务**：在 `core/command_safety.py` 仿照 `_is_self_repo_destructive_git` 增加拦截：
- 条件：目标仓库为 bobo 自身仓库（与 push 闸同判定逻辑）**且**当前分支为 main **且**命令为 `git commit`（含 `commit -a` 等变体）
- 动作：拦截并提示"self-repo 禁止在 main 直接提交，请切 feat 分支"
- 豁免：merge commit（`git merge` 产生的提交不经过 `git commit` 命令，天然不受影响）；`git merge` 本身不拦截（v2 允许本地 merge）
- 注意：docs-only 提交是否豁免——建议不豁免（一律走分支，简单统一），如用户另有偏好再调

**验收**：
1. 新增测试：self-repo + main + git commit → 拦截；self-repo + feat 分支 + git commit → 放行；其他仓库 + main + git commit → 放行；git merge → 放行
2. pytest 全绿
3. 五查汇报 + feat 分支（此票本身必须走 feat 分支，不许自证违规）

---

## 纪律备注（本次事件衍生）

e2e 返工时 bobo 在未收到派单指令的情况下，看到 docs/ 下出现 REWORK 任务单即自行开工。处理结论：
- 任务单文件 ≠ 开工令（默认模式须确认后动手）——已写入 self-hosting 标准
- 未来 auto 模式下此行为为预期能力，届时由显式开关启用

---

## 票 E：smoke_boot PEND 在页脚被误报为 FAIL

**背景**：`scripts/smoke_boot.py` 第 656 行：
```python
EXIT_CODE=" + ("0" if results.all_pass() else "1")
```
`all_pass()` 只在所有条目为 PASS 时返回 True。PEND 状态（shutdown 挂账）导致 `all_pass() → False`，进而 EXIT_CODE=1，与 FAIL 无法区分。页脚 `sys.exit(main())` 同理（第 669 行），退出码 1 让 CI/CD/脚本误判冒烟"失败"。

**实测**：完整模式 5/6 PASS + 1 PEND → EXIT_CODE=1 → exit code 1。

**任务**：
1. `Results` 新增 `exit_code` 属性或方法，三态映射：PASS=0, PEND=2（或其他非零区分码）, FAIL=1
2. `all_pass()` 改为 `all_pass_or_pend()`（PEND 不算 failed），或页脚逻辑改为 `if any FAIL → 1, elif any PEND → 2, else → 0`
3. 页脚消息区分"全部通过" vs "全部通过（含挂账项）" vs "有失败项"

**验收**：
1. 干跑：5/5 PASS → exit 0
2. 模拟 PEND：5/6 PASS + 1 PEND → exit 2（非 1）
3. 模拟 FAIL：包含 FAIL → exit 1
4. pytest 全绿

---

## 票 F：v3 main commit 闸过度拦截 — echo 等字符串内容误触

**背景**：`_is_self_repo_main_commit` 对命令全字符串做 `\bgit\b` + `_find_git_subcommand` 判定，不区分命令段和字符串内容。例如：
```bash
echo "please run git commit -m fix"    # 被误拦
git log --grep="git commit"            # 被误拦
```
这些命令的真实意图不是执行 `git commit`，但正则触发闸门。

**影响**：低。在 bobo 自身仓库 main 分支上执行 echo/grep 等命令且字符串内含 "git commit" 才会触发，场景极少。且这些命令属于白名单（echo/grep），原本静默执行变为弹窗确认。

**优化方向**：命令分段解析——先用 `split_shell_segments`（已有）按 `&&`/`;`/`|` 分段，只对包含真实 git 命令的段做 `_find_git_subcommand` 判定，字符串/引号内的"git commit"不触发。

**优先级**：低。影响面极小，不紧急。
