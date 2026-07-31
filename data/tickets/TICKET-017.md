# TICKET-017: gateway 静默退出留痕 + 会话恢复纠偏

| 属性 | 值 |
|------|-----|
| 分级 | P0 |
| 分支 | fix/ticket-017-gateway-exit-tracing |
| 前置 | TICKET-016（已合并 fd84631） |

## 背景

2026-07-31 晚 python gateway 发生 **5 次静默退出**
（22:04:46 / 22:06:16 / 22:22:37 / 22:40:26 / 22:47:09）：

- 全部 exit code 0，无 traceback、无信号日志、无 stdout 断裂告警
- 每次死在 LLM 流式调用或施工中途，TUI 显示
  "gateway exited · recovering session…"，在途回复丢失
- 恢复时 `planGatewayRecovery` 回落到"resume most recent"，
  而"最近会话"被错误会话刷新过 → 每次恢复都回错会话（串台）

已知退出路径（`bobo_tui_gateway/entry.py`）均**不留日志**：

1. `_shutdown()`（SIGINT/SIGTERM）→ `shutdown_sessions()` → `sys.exit(0)`
2. 主循环 `for raw in sys.stdin` 读到 EOF（stdin 被关闭）
3. `write_json` 失败 → `break`（stdout 断裂，有 warning 但不记退出原因）

Node 侧（`ui-tui/src/gatewayClient.ts`）：
`start()` 替换存活 child 时直接 `proc.kill()`（约 433/637 行），
**不经过 `GatewayClient.kill()`**，因此无面包屑。

## 任务内容

### 1. python 侧：每条退出路径留遗言

`bobo_tui_gateway/entry.py`：

- `_shutdown(signum, frame)`：先 `logger.critical("gateway 退出: 收到信号 %s", signum)`
  再执行原有逻辑
- stdin EOF 退出路径：`logger.critical("gateway 退出: stdin EOF（父进程关闭了管道）")`
- stdout 写入失败 `break` 处：补 `logger.critical("gateway 退出: stdout 断裂")`
- 主循环正常结束处：`logger.critical("gateway 退出: 主循环结束")`

目标：下次死亡，`data/logs/bobo.log` 最后一行必须写明死因。

### 2. Node 侧：补面包屑

`ui-tui/src/gatewayClient.ts`：

- 找到 `start()` 替换存活 child 的直接 `proc.kill()` 调用点，
  在 kill 前加 `this.lifecycle('[lifecycle] start() replacing live child pid=...')`
- 若有其他绕过 `kill()` 方法的直接 `proc.kill()`，同样补上

### 3. 恢复纠偏：回到崩溃前的会话，而不是"最近修改"

`ui-tui/src/app/useMainApp.ts` 的 `exitHandler` +
`createGatewayEventHandler.ts` 的恢复逻辑：

- 崩溃前 `getUiState().sid` 存在时，优先 resume **该 sid**
  （现有 `recoverSidRef` 机制），不得回落到 most-recent
- 仅当该 sid resume 失败（会话已不存在）时才回落 most-recent，
  且此时 `turnController.pushActivity` 明确提示"原会话已丢失，已回到最近会话"
- 阅读 `planGatewayRecovery` 现有逻辑，最小改动实现，不顺手重构

### 4. 回归测试

- `pytest tests/ -q` 全绿
- `cd ui-tui && npm test`：不允许出现**新增**失败
  （基线：gatewayClient.test.ts websocket mock 12 个失败为环境问题，不算回归）
- 手动验证（写进五查）：启动 bobo，`kill -TERM <gateway pid>`，
  `data/logs/bobo.log` 末尾必须出现"gateway 退出: 收到信号 15"

## 验收标准

- [ ] 1. 4 条 python 退出路径均有 `logger.critical` 遗言
- [ ] 2. Node 侧绕过 `kill()` 的 `proc.kill()` 全部补上面包屑
- [ ] 3. 恢复逻辑：sid 存活时绝不串台；sid 丢失时回落有明确提示
- [ ] 4. `pytest` 全绿；`npm test` 无新增失败
- [ ] 5. kill -TERM 手动验证的日志截图/原文写进五查汇报
- [ ] 6. 改动全部在 `fix/ticket-017-gateway-exit-tracing` 分支，不碰 main，不 push
