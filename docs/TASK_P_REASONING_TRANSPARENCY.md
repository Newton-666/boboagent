# 票 P · reasoning 透明化 + 流解析兜底 — K2.6/K3 兼容治本

> 立案：2026-07-28 晚。K2.6 实测：moonshot 三次 200、每次 1-2s、SSE 流零内容块 →
> 空响应兜底。根因二合一：① `core/llm_caller.py` 流式解析只收 `delta.content`，
> `reasoning_content` 整体丢弃；② 服务端对 streaming 请求可能直接回非 SSE 的普通 JSON，
> SSE 解析器找不到 `data: ` 行 → 空。7-25 K3"不回复"悬案同根。
> 用户提案（已采纳）：思考过程流动打印、与最终回复隔离、完成后自动折叠可展开——
> 对齐 Claude Code / Kimi Code 体验。
> 纪律：票 ≠ 开工令。本票由 Kimi 终审立项。

## 一、修复要求（与票 N2 同一分支 feat/sse-watchdog 一趟修，同一流式循环）

### ① reasoning_content 透明化（用户提案）

- 流式循环新增 reasoning 缓冲区：`_dl.get("reasoning_content")` 单独累积，
  **绝不混入 full_content**（最终回复纯净）
- 新增可选回调：call_llm 增加 `reasoning_callback=None` 参数，收到 reasoning 块即推
- engine 接线：把 reasoning 块作为独立事件推给 TUI（与 content 流分通道）
- TUI 呈现（降级许可）：优先折叠式"💭 思考过程（流动）→ 完成自动折叠"；
  TUI minified bundle 做不了折叠 → 降级为消息流内分隔线灰显区块
  （`── 💭 思考过程 ──` … `── 思考结束（N 秒）──`），同样不与正文混
- 事件：回合结束写 `llm.reasoning`（reasoning_chars、content_chars、时长）

### ② 非 SSE 兜底解析（治病根）

- 流式读取全程零内容块（content+reasoning+tool_calls 全空）时：
  不要直接判空响应——把整个响应体按**非流式 JSON** 重新解析
  （`response.json()` → choices[0].message.content / reasoning_content / tool_calls）
- 兜底命中 → 按正常结果返回 + WARNING 日志 + 写 `llm.non_sse_fallback` 事件
- 兜底也空 → 才走空响应通道

### ③ 禁止项

- reasoning_content 禁止混入最终回复正文
- 禁止破坏 DeepSeek 现有流（回归测试必须全绿）
- 折叠 UI 不许硬改 minified bundle（走降级方案）

## 二、验收金标准

1. 模拟 SSE 流只发 reasoning_content + 末尾 content → full_content 只含 content，
   reasoning 单独可回放 ✓
2. 模拟非 SSE JSON 响应（stream=True 但返回普通 JSON）→ 兜底解析出 content ✓
3. DeepSeek 现有全部测试零回归，pytest 全绿（基线 944）
4. reasoning_callback 缺席时行为与现状一致（兼容旧调用）
5. 五查汇报 + git status 原文

## 三、边界

- 只动 core/llm_caller.py（+ engine.py 回调接线 + 必要时 TUI 协议层）
- K2.6 实测开口说话是终审最后一环（Kimi 亲验）
