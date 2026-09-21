# 工具超时生命周期（GitHub #2）

`core/tool_lifecycle.py` 是超时、取消和写槽的单一事实源。`config.TOOL_TIMEOUT` 为通用默认；`execute_terminal=120`、`spawn_worker=310` 为长任务上限。

## 超时后会发生什么

1. 设置本次调用的 `cancel_event`
2. 对已登记子进程 `killpg(TERM/KILL)`（`execute_terminal`、`code_execution`、`run_tests` 经 `run_cancellable_subprocess` 登记）
3. 相同副作用身份若仍在途 → **硬拒绝**；若外层已超时但内层随后成功 → 短 TTL 回放，避免二次落地

## 写槽覆盖

`WRITE_TOOLS` / `SIDE_EFFECT_TOOLS` 覆盖本地写路径（含 **`code_execution`**、笔记/目录变更、`task_ledger`、`run_tests`）以及终端/Worker。

远程写 API（GitHub / Notion / 日历 / 提醒等）也进写槽，但 **没有可杀的子进程**：超时只能协作取消 + 在途拒绝，HTTP 调用本身无法 `killpg`。

## 已知残留（无法硬杀）

**Python 不能强制杀死已经在跑的线程。**

纯 Python 卡住（无限循环、无超时的阻塞 syscall、不轮询 `is_cancelled()` 的函数）时：

- 外层 `future.result(timeout)` 仍会返回超时
- **不能** 硬杀该线程
- 只能：协作 `is_cancelled()` + 写槽挡住同参重试，直到 worker **自己返回** 才释放槽、结束线程

子进程路径（终端、`code_execution` 解释器、`run_tests`）可以 killpg，不在此残留范围内。

没有后续票把「纯 Python 线程硬杀」做进本修复；若需要，应另开进程级沙箱，而不是在 ThreadPool 里 `kill` 线程。
