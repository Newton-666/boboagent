# 票 U：429 余额不足误归类为可重试限流

> 状态：待开工
> 分支：`feat/balance-error`（从最新 main 新建）

## 病灶

`core/llm_caller.py` 的 `_classify_error`（约 297 行）只接收 status_code，
收不到响应体。所有 429 一律返回 `("rate_limit", True, ...)` 走指数退避重试。

但多家厂商的**余额不足**也返回 429：
- DeepSeek：`{"error":{"message":"Insufficient Balance"}}`
- OpenAI：`{"error":{"code":"insufficient_quota"}}`
- 部分网关：`余额不足` / `balance insufficient`

后果：余额耗尽时每次调用都白等 3 轮退避（1s+2s+4s…）才失败，
错误消息还显示"请求过于频繁"，误导用户去等而不是去充值。
实战记录：2026-07-28 晚 DeepSeek 余额耗尽期间大量无谓重试。

## 处方（只动 llm_caller.py 一处 + 测试，禁止扩 scope）

### 1. `_classify_error` 增加可选参数 `response_body: str = None`

429 分支改为：若 response_body 命中以下关键词（小写化后匹配）——

```
"insufficient balance", "insufficient_quota", "余额不足", "balance insufficient"
```

则返回 `("balance_error", False, "API 余额不足，请检查账户余额或更换 provider")`。
未命中则维持 `("rate_limit", True, "请求过于频繁，已被限流")` 不变。

顺手：401/403 分支若 response_body 命中同样关键词（有些厂商用 401 报余额），
也归入 `balance_error`。没有命中时各分支行为一律不变。

### 2. 调用点传响应体

状态码检查处（约 421-424 行）改为：

```python
error_type, retryable, message = _classify_error(
    status_code=response.status_code,
    response_body=response.text[:500],
)
```

注意：此处是 stream=True 的请求，但非 200 时错误体很小，
`response.text` 一次性读尽是安全的；截断 500 字符防异常大错误页。

### 3. 下游通道不新增

`balance_error` 走现有非重试通道（与 auth_error/bad_request 同路），
UI 状态灯自然落红色 error。**禁止**为此改 engine/UI。

## 验收金标准（tests/ 追加）

1. 429 + body 含 "Insufficient Balance" → `balance_error`，retryable=False，
   **不发生重试**（mock 计数只调用 1 次）。
2. 429 + 普通限流 body → 仍 `rate_limit`，重试行为不变。
3. 429 + 空 body / body 为 None → `rate_limit`，行为不变（回归）。
4. 401 + body 含 "insufficient_quota" → `balance_error`。
5. 错误消息含"余额"字样，用户可读懂。
6. 全量 pytest 通过，现有 llm_caller 测试零回归。

## 纪律

- 开工前 `git branch --show-current` 确认在 `feat/balance-error`。
- 完成后五查汇报（含 git status 原文 + git branch --show-current 原文），
  ⛔️ 禁止 merge、禁止 push，等 Kimi 终审。
- 改了 core/ → 五查第 6 项填"是，需重启生效"。
