# [P0] shutdown_sessions 导致子进程超时 SIGKILL

**状态**: 待派单  
**优先级**: P0  
**创建**: 2026-07-28  
**关联**: `scripts/smoke_boot.py` 第 5 征"退出干净"挂账  
**关联案**: 崩溃案（共享 `prompts.py` 线程生命周期区域）

---

## 症状

```
smoke_boot.stop() 关闭子进程 stdin
  → entry.py: for line in sys.stdin → EOF
  → shutdown_sessions() 被调用
  → shutdown_sessions 内 thread.join() 等待 engine 线程
  → engine 线程阻塞在 requests.post() / SSE 读流
  → join 不返回
  → 30s 超时后 smoke_boot 发 SIGKILL
  → 退出码 -9
```

**受影响文件**: `bobo_tui_gateway/server.py` → `shutdown_sessions()` → `prompts.shutdown_sessions(ctx)`

**冒烟表现**: 5/6 PASS + 1 PEND（受控退出挂账）

---

## 三条新证据

### 证据 1: 孤儿进程实证 — shutdown 链条断裂导致进程残留

2026-07-28 12:50 系统清理中确认：119 个残留 `bobo_tui_gateway.entry` 进程对 SIGTERM 无响应——`pkill -15` 发出后无一退出，最终只能 `pkill -9` 强清。这些进程的 shutdown_sessions 从未执行到线程回收阶段，因为 `thread.join()` 阻塞在 requests/SSE 流上，信号 handler 注册了但永远不会被主线程交付。

注：PID 1160/6600/83337 为当前活跃 bobo 会话后端（清理时特意保留），非孤儿。

**结论**: 不是偶发超时，是系统性 shutdown 断裂。119 个残留进程 = 119 次 SIGTERM 无效的实证。

### 证据 2: SIGTERM 无效

在 stderr 文件化之前的测试中，`smoke_boot.stop()` 对子进程发送 SIGTERM：
- 子进程主线程卡在 `sys.stdin.readline()`（C 调用中信号不交付）
- SIGTERM signal handler 注册了但永远不会被调用
- 30s 后 smoke_boot 只能发 SIGKILL 强杀

转用 stdin close 触发 EOF 后，`shutdown_sessions` 确实被调用了，但内部 `thread.join()` 又形成新的阻塞点。SIGTERM 和 stdin close 两条路径都堵死。

### 证据 3: stderr PIPE 死锁嫌疑已排除

2026-07-28 将 `subprocess.PIPE` 改为临时文件（`tempfile.NamedTemporaryFile`），完整模式实测结果不变：5/6 PASS + 1 PEND，退出码仍为 -9。PIPE 缓冲区满写阻塞不是根因，证实阻塞点在 `shutdown_sessions` 的 `thread.join()`。

---

## 方向（已定优先级）

**首选: engine 线程守护化 + shutdown 跳过 join + os._exit 兜底**

1. Engine 线程已标记 `daemon=True`，进程退出时 OS 自动终止——不需要 join
2. `shutdown_sessions()` 只做必要清理（保存会话到磁盘），然后 `os._exit(0)`
3. 不等待 engine 线程、不依赖信号交付、不碰 stdin 阻塞

**备选 (仅作记录)**:
- bounded join (3s) + 超时 `os._exit` — 比首选多一层无意义的等待窗口
- engine.cancel JSON-RPC 端点 — 最干净但需新增 RPC 协议，工作量最大

---

## 与崩溃案的关系

与崩溃案共享线程生命周期区域（`bobo_tui_gateway/handlers/prompts.py` 第 89-105 行 engine 线程创建 + `daemon=True`）。治本方案应同时覆盖两案的线程生命周期边界。

---

## 禁止项

- 禁止把退出码 -9 判为 PASS（当前已在冒烟中标记为 PEND/挂账）
- 治本前不修改 engine/entry 源码（按当前规则）
