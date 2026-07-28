# TASK_L3_ENGINE_E2E — L3 任务单②：Engine 状态机端到端测试台

> 2026-07-28 Kimi 出单。L3 级（测试基础设施，多场景）。
> 来源：Cloud 扫描清单"Engine 状态机无集成测试"——崩溃凶手住在
> 这个状态机里，而 Engine.run() 主循环零覆盖。
> 这是崩溃案的终极回归测试台：有了它，"中途 kill → 孤儿 → 清洗"
> 全链路可以在测试里反复重演，不用等真崩溃。

## 已确认的地基（先读码核实）

- `Engine(llm_caller, tool_executor=None, callback=None,
  confirm_callback=None, test_mode=False)`——两个依赖都可注入，
  这是测试台的天然接口（core/engine.py:45）
- 状态机：IDLE → THINKING → (EXECUTING) → RESPONDING → DONE/ERROR
  （core/engine.py:36-41、_step 600-644）
- llm_caller 协议：返回 dict（error）或 OpenAI 格式 choices；
  流式走 stream_callback——假 caller 只需实现这几条
- 孤儿清洗已上线：core/context.py clean_orphan_tool_calls
- 数据隔离铁律：一律 tmp_path/mock，禁碰真实数据文件

## 任务文本（粘贴给 bobo）

```
任务：Engine 状态机端到端测试台（feat/engine-e2e-harness 分支）

工作目录：/Users/niuqingwei/Desktop/BOBO_Project_Backup

背景：Engine.run() 主循环没有集成测试。Engine 的 llm_caller 和
tool_executor 都是可注入的（engine.py:45），用假实现即可在
pytest 里驱动完整回合，不需要真 API、不需要真工具。

要求：
1. git checkout -b feat/engine-e2e-harness，全程在该分支
2. 先读 engine.py 的 __init__/run/_step（36-100、600-660、778-830），
   和 llm_caller 的返回协议，画出状态转换图（放 commit message）
3. 建测试台（tests/e2e/ 或 tests/test_engine_e2e.py）：
   - FakeLLMCaller：预编程响应队列（文本/工具调用/error 可编排），
     实现真实 caller 的返回协议
   - FakeToolExecutor：白名单假工具（echo/写文件到 tmp_path），
     记录每次调用参数
4. 场景覆盖（每个都是独立测试）：
   a. 简单问答：单轮文本进 → STATE_DONE，history 结构正确
   b. 工具回合：caller 第一轮发 tool_calls、第二轮给最终文本 →
      完整走 THINKING→EXECUTING→THINKING→RESPONDING→DONE，
      历史中 assistant tool_calls 与 tool 结果正确配对
   c. 错误恢复：caller 返回 error dict → STATE_ERROR →
      下一轮正常输入后恢复（不卡死）
   d. 中途 kill 模拟：EXECUTING 阶段假 executor 模拟中断
      （assistant 的 tool_calls 已入 history、tool 结果未写）→
      用 clean_orphan_tool_calls 清洗后历史结构合法
      （这是崩溃案的回归测试：孤儿产生 → 清洗 → 合法）
   e. 多轮连续：3 轮对话后 history 长度与结构正确，
      无消息丢失/乱序
5. 零真实依赖：不打真 API、不写真数据文件（铁律）、
   不依赖网络。全部 mock/tmp_path
6. ./.venv/bin/python3 -m pytest tests/ -q 全绿
7. 在 feat 分支 commit，五查汇报（表格），然后停
   （v2 规矩：允许本地 merge，禁止 push）

验收标准（逐条可判定）：
① 五场景全覆盖且各自独立可运行
② 场景 b 断言状态转换序列完整（不只是最终状态）
③ 场景 d 是"孤儿产生→清洗→合法"的完整链路，不是只测清洗函数
④ 零真实依赖（断网可跑——我验收时会断网跑一遍）
⑤ 状态转换图在 commit message
⑥ pytest 全绿 + 五查表格 + 未 push
```

## 我（Kimi）初审时的独立检查

- 断网跑全量 pytest（零真实依赖的硬验证）
- 场景 d 是否真走"产生→清洗"全链路（而非直接调清洗函数）
- FakeLLMCaller 的协议保真度：和真 llm_caller 返回结构逐字段对
- 有没有为了过测试改 engine 本身（测试台任务不该动被测代码，
  除非发现真 bug——那要单独说）

## 意义

状态机从此有护身符：以后每次改 engine/_step/工具循环，
这套 e2e 会第一个报警。场景 d 把崩溃案从"破过一次"
变成"永远抓得到"。
