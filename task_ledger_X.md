# 票 X 台账

**分支**: feat/headers-watchdog-audit
**任务**: headers 看门狗引爆复核（docs/TASK_X_HEADERS_AUDIT.md）

---

## 复核清单

### ✅ 1. 真撞闸（核心）→ 咬合
- [x] test_headers_stall_triggers_within_timeout — 3s 内准时引爆 ✅
- [x] test_headers_stall_retry_happens — 2 次尝试（初始+重试）✅
- [x] test_headers_stall_event_bus_fires — ≥2 次 llm.headers_stall 事件 ✅
- [x] 结论: **咬合** — 真撞闸 4 项测试全绿，8-9s 内准确返回 error dict

### ✅ 2. 僵尸线程审计 → 松动
- [x] test_worker_thread_cleaned_after_timeout — 无非 daemon 遗留线程 ✅
- [x] `_close_socket` 执行 shutdown(SHUT_RDWR)+close，然后 `_t.join(timeout=2.0)`
- [x] 结论: **松动** — daemon 未设 True，join 到期后极端情况可残留；当前风险低

### ✅ 3. 双看门狗咬合 → 咬合
- [x] test_dual_watchdog_200_then_stall — error_type=stream_stall，非 headers_stall ✅
- [x] 结论: **咬合** — 200 头后断气精确归 read 看门狗，分界清晰

### ✅ 4. 超时配置链 → 咬合
- [x] 默认 90s / 环境变量覆盖 / 非法值回退 / 不与 BOBO_READ_TIMEOUT 撞名 — 4 项全绿
- [x] 当前进程 env: BOBO_READ_TIMEOUT=60, BOBO_HEADERS_TIMEOUT=<未设置>
- [x] 结论: **咬合**

### ✅ 5. 引擎层生还 → 松动
- [x] HeadersStallError → ("headers_stall", False, ...)，engine 收 retryable=False 走 STATE_ERROR
- [x] 返回 error dict 不崩溃
- [x] 结论: **松动** — 分类命名不一致但行为正确

---

## 交付记录

- [x] tests/test_headers_watchdog_live.py（11 项真撞闸测试）
- [x] 复核结论写入 docs/TASK_X_HEADERS_AUDIT.md 末尾"结案"节
- [ ] 五查汇报 + git status 原文 + git branch --show-current 原文
- [ ] commit 后 git checkout main 归位
