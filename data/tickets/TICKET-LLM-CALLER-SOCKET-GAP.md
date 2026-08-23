# TICKET-LLM-CALLER-SOCKET-GAP

> 类型：候选真 bug 评估票（由 TICKET-MAIN-REGREEN B5 判研产出）
> 开票：2026-08-23
> 状态：**待评估**——先定性，后决定修法

---

## 1. 现象

`core/llm_caller.py` 的 headers 看门狗（TICKET-PROVIDER-ADAPTER 并发竞态修复后）：
- `_sock_holder` 改为 `threading.local()`；
- socket 由 **worker 线程** 创建并写入 `_sock_holder.sock`（worker 自己的线程局部）；
- **主线程**读取 `_sock_holder.sock` 得到的是**主线程自己的局部值（None）**。

## 2. 后果（两个）

1. **中断路径**（已修，B5）：`_sock_holder.get("sock")` 不存在 → 已改为 `getattr` 兜底（修崩溃，测试过）；
2. **socket 关闭语义 gap**（本票，未修）：主线程因线程局部隔离**永远读不到 worker 的 sock** → 中断/headers 超时时的 `_close_socket` 实际从不执行（`_sock is None` 恒真）→ 卡死的连接不被主动关闭，只能等系统级超时/进程退出。

## 3. 影响评估（待完成）

- 严重度：中——不主动关 socket 的后果是连接泄漏与"中断响应慢"（worker 的 requests.post 仍在阻塞，直到自身超时）；
- 触发面：真实生产中断场景（用户 Stop 时 headers 阶段）；
- 与 B5 修复的关系：B5 只修了"崩溃"，本票修"真的关掉连接"。

## 4. 候选修法（评估后选一）

| 方案 | 做法 | 取舍 |
|---|---|---|
| A. 共享句柄队列 | 每调用一个 `{sock}` 共享容器（调用级 dict 而非线程级），worker 写、主线程读 | 恢复 PROVIDER-ADAPTER 前的可关闭性；需防并发覆盖（原竞态问题） |
| B. 主线程自建连接 | headers 阶段的连接改由主线程预建再交 worker | 改变请求架构，风险高 |
| C. 接受现状 + 文档化 | 中断只抛异常不关连接，依赖请求自身超时 | 零风险，但"主动关闭"承诺失效 |

## 5. 验收

- 方案 A：单测模拟 headers 挂起 + 中断 → 断言 `_close_socket` 被调用（真实 sock 关闭）；
- 方案 C：更新注释与文档，明确"中断不主动关连接"为设计行为；
- 定案后入 CHANGE-LOG。
