# TICKET-018: unix socket 传输解耦——前端故障不再杀死 gateway

| 属性 | 值 |
|------|-----|
| 分级 | P0 |
| 分支 | fix/ticket-018-socket-transport |
| 前置 | TICKET-017（已合并 cf02f88） |

## 背景（故障证据链）

2026-07-31 晚 bobo TUI 连环死亡案（TICKET-016/017 已记录）：
前端 Node 进程每次崩溃/退出，都会通过 stdio 管道连带杀死 python gateway。
`gatewayClient.ts` 以父进程身份 spawn python，父子通过 stdin/stdout 管道绑定——

- 前端 fd 被原生层误关 → 管道断裂 → python 侧 stdin EOF / stdout EPIPE → 静默退出
- 前端 Node 崩溃 → 管道关闭 → python 侧同样逃不掉
- 每次死亡都是"无声死亡"（exit 0、无 traceback），恢复又串台

**架构病根**：gateway 的生命周期被绑死在"前端进程是否活着"上，前端任何
故障都必然传导为后端死亡。治本方案是解耦——让 gateway 自己 hold 住
监听 socket，前端只是"客户端"，断了重连即可，不判 gateway 死亡。

## 方案

### Python 侧（bobo_tui_gateway）

1. `transport.py` 新增 `SocketTransport`：unix socket 连接封装，`write()`
   对端断开时返回 False 不抛异常（gateway 不死的根基）。
2. `entry.py` 新增 `_run_socket_backend(sock_path)`：python bind/listen
   unix socket（0o600 权限），`set_transport(SocketTransport(conn))` 后
   走 `_serve_connection`；前端断开只记日志（"前端断开，等待重连"），
   **进程保持存活**，回到 `accept()` 等待重连。
3. 入口：`BOBO_GW_SOCKET` 环境变量非空 → socket 模式；否则回退 stdio。

### Node 侧（ui-tui/src/gatewayClient.ts）

1. spawn 时若 socket 未禁用，生成 `bobo-gw-<pid>-<ts>.sock` 路径并
   注入 `BOBO_GW_SOCKET` 环境变量。
2. `connectSocketWithRetry`：等待 socket 文件出现（50 次重试），
   连接成功即 `wireSocket`（readline 解析 JSON 帧）。
3. `handleSocketClose`：child 活着但 socket 断了 → **不判 gateway 死亡**，
   自动重连（最多 20 次）；child 死了才走既有 recovery 流程。
4. 逃生阀：`BOBO_DISABLE_SOCKET_TRANSPORT=1` 可强制 stdio 模式
   （等待 socket 超时 50 次后自动降级 stdio 并重启 child）。

## 验证

新增 `tests/test_ticket018_socket_transport.py`（8 个测试，全绿）：

- `SocketTransport.write` 正常发送 / unicode 保真 / 对端关闭返回 False
- `close()` 幂等；close 后 write 返回 False
- `set_transport` 切换后 `write_json` 走新通道
- **核心命题**（子进程集成测试）：连接→断开→重连→断开，三次循环
  gateway 进程始终存活；bobo.log 记录"前端断开"断开原因

回归：`test_server_utils.py` + `test_llm_caller.py` 37 个测试全过；
`ui-tui` 构建（esbuild）成功，socket 代码已编入 `static/entry.js`。

## 遗留

- `tsc --noEmit` 有 3 个**历史遗留**错误（prompts.tsx / theme.ts /
  gatewayClient.ts:81 ArrayBufferLike），stash 验证与本次改动无关，
  不在本票范围内。
- socket 模式下 TUI 的"gateway exited · recovering"提示应改为
  "重连中"文案，待前端 UI 跟进（另开票）。
