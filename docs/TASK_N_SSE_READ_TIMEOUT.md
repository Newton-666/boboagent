# 票 N · SSE 流式读超时 + 断流重试 — 引擎假死治本

> 立案：2026-07-28 17:28 假死案。faulthandler 堆栈铁证：引擎线程卡死在
> `llm_caller.py:145 call_llm → requests iter_lines → urllib3 read_chunked → ssl.py:1138 read`，
> SSE 流半开（TCP 未断、服务器不再吐字），流式请求无读超时，线程无限期阻塞。
> 同家族悬案：今日多次"半路停"、"崩了一下又恢复"（TCP 自复位后流续上）、
> 2026-07-25 切 Kimi K3 不回复（reasoning 模型流间隔长，同一敏感区）。
> 定位：auto 模式"不停机"难关核心一票，优先级最高。
> 纪律：票 ≠ 开工令。本票由 Kimi 终审立项，bobo 领票后开工。

## 一、病因（禁止跳过的背景）

`core/llm_caller.py` 的流式请求（`requests ... stream=True`，约 line 145 起逐行读 SSE）
没有设置读超时。TCP 半开状态下 `ssl.read` 可无限阻塞 → 引擎线程假死，
TUI 停留在最后状态（ready 假象），用户无法区分"死了"与"在想"。
requests 的 read timeout 语义是**单次 recv 超时**（不是整个响应总时长），
天然适配 SSE：只要每个块在限定时间内到达就存活，超时即抛异常——
长思考模型（K3 等 reasoning 模型）块间隔长，阈值必须兼容。

## 二、修复要求

### ① 读超时（核心）

- 流式请求加 `timeout=(connect_timeout, read_timeout)`
- read_timeout 默认 **120 秒**（块间间隔上限），可被环境变量 `BOBO_SSE_READ_TIMEOUT` 覆盖
- 取 120s 的理由：DeepSeek 实测块间隔秒级；reasoning 模型（K3）思考期可能 30-90s 无块，
  120s 留足余量又保证假死 2 分钟内必被发现
- connect_timeout 10s 不变（若已有）

### ② 断流重试（一次，不多）

- `requests.exceptions.ReadTimeout` / `ChunkedEncodingError` / `ConnectionError`
  在**流读取阶段**抛出的 → 视为断流：
  - 若尚未收到任何内容块 → 原样重发请求重试 1 次
  - 若已收到部分内容 → 丢弃半残响应，重试 1 次（不要拼接半残流）
  - 重试仍失败 → 走现有错误通道返回 retryable 错误，由引擎重试/报错逻辑接管
- 每次断流/重试必须写事件：`llm.stream_stall`（含 session_id、已收块数、耗时）

### ③ 禁止项

- 禁止用"总响应超时"（会误杀长回复，SSE 必须按块间算）
- 禁止无限重试（硬上限 1 次，防 auto 模式下静默死循环刷 API）
- 禁止吞异常（断流必须留事件 + 日志 WARNING）

## 三、验收金标准（逐条物理验证）

1. **假死复活（核心）**：模拟 SSE 流读 3 个块后静默（可用本地假 SSE 服务器/socketpair
   或 monkeypatch urllib3 read）→ 120s 内（测试可注入短超时如 2s）必须抛断流异常并触发重试，
   引擎线程不再永久阻塞
2. **断流留证**：`llm.stream_stall` 事件落盘 events.jsonl，json.loads 可解析
3. **半残不拼接**：已收 2 块后断流 → 重试成功时最终 content 不含半残块内容
4. **正常流零误伤**：现有 FakeLLM/真 API 冒烟全不受影响
5. pytest 全绿（基线 920 + 本次新增）+ 活体冒烟 6/6
6. 五查汇报含第 6 项「是否需重启」+ 附 `git status` 原文

## 四、边界

- 只改 `core/llm_caller.py`（必要时小动 engine 错误通道接线），不动 TUI、不动 gateway
- K3 兼容验证（reasoning 模型实测）不在本票范围，单独立票——本票只保证
  "长块间隔不误判死"的阈值设计合理
- 分支 `feat/sse-read-timeout`，本地 merge 需 Kimi 终审通过，**禁止 push**
