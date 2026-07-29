# 票 X：headers 看门狗引爆复核

**优先级**：中（四连败事故的复查课）｜ **风险**：低（纯验证 + 补缺，原则上不改逻辑）
**分支**：`feat/headers-watchdog-audit` ｜ **禁止**：merge / push，完成后五查汇报 + git status 原文等 Kimi 终审
**开工铁律**：`git branch --show-current` 先行；commit 后 `git checkout main` 归位 HEAD。

---

## 一、背景

headers 看门狗（core/llm_caller.py，`HeadersStallError`）是昨天 k2.7 网关三连断气案的手术成果：requests.post 放 worker 线程，主线程 join(headers_timeout)，超时判断流并重试。单元测试已有（tests/test_headers_watchdog.py）。

但**单元测试 ≠ 战场**。复核要回答一个问题：在真实网络条件下，这套看门狗的每一个环节是否都真的咬合。

## 二、复核清单（逐项给结论：咬合 / 松动 / 缺齿）

1. **真撞闸（核心）**：起一个真 TCP 服务器——accept 连接但**永远一个字节不回**（不是 mock，不是合成异常），用真 requests 走完整 `create_llm_caller` 调用链：
   - headers_timeout 内是否准时引爆 `HeadersStallError`
   - 重试是否发生（`_get_max_retries`），重试后仍断气是否抛出
   - `llm.headers_stall` 事件是否落总线（含 elapsed_ms、action）
2. **僵尸线程审计**：超时后主线程走了，worker 线程还阻塞在 requests.post 里——它会不会成为孤儿？（票 H 教训：线程必须有归宿）验证：超时后 60s 内 worker 是否随 socket 关闭/进程退出策略有明确结局；如果设计就是"弃疗等 OS 回收"，文档里写明。
3. **双看门狗咬合**：headers 看门狗（连接后无响应）与 read 看门狗（流中断）的分界是否清晰——构造"先发 200 响应头然后断气"的服务器，验证归 read 看门狗管，不误触发 headers 路径。
4. **超时配置链**：`BOBO_HEADERS_TIMEOUT` 环境变量 → `_get_headers_timeout()` 的默认值与上下限；进程 env 里实际值是多少（bobo 进程有 BOBO_READ_TIMEOUT=60，确认 headers 没被撞名覆盖）。
5. **引擎层生还**：HeadersStallError 抛出后，engine._call_llm 的错误路径是否正确归类（network_error、可重试），不会把回合打成 STATE_ERROR 死局。

## 三、验收标准

1. 复核清单 5 项逐项结论 + 证据（测试输出/日志原文）
2. 真撞闸测试进 tests/（真 socket 服务器，tmp port，禁止 mock requests）
3. 发现松动/缺齿就修，修复必须带回归测试
4. 全量 pytest 基线 1145 passed / 2 skipped 不回归
5. 若改 core/，五查第 6 项必填"是"

## 四、交付物

- tests/test_headers_watchdog_live.py（真撞闸）
- 复核结论写进 docs/TASK_X_HEADERS_AUDIT.md 末尾"结案"节
- 五查汇报 + git status 原文 + git branch --show-current 原文
