# TICKET-GW-SOCK 桌面端后端切 socket 常驻模式

> 状态：待派工（开票日期 2026-08-17，Kimi 撰写）
> 分支：feat/ticket-gw-sock（自 main d305652a 之后最新 main 切出）
> 回滚标签：rollback/pre-gw-sock
> 动机：VS Code 扩展（VSC-1 已合并）需要可发现的 unix socket；桌面端目前
> spawn 后端走 stdio（main.cjs:97-98 强制），扩展无可连。顺带根治旧伤：
> 前端崩溃/闪退杀死后端（TICKET-018 设计本意 = 前端故障不死 gateway）。

## 施工

1. `apps/desktop/electron/main.cjs` spawn 后端时设
   `BOBO_GW_SOCKET=$TMPDIR/bobo-gw-main.sock`（固定名），前端连接从 stdio 管道
   改为 unix socket；原 D1b E1 环境变量清理逻辑同步适配。
2. 前端断开/渲染进程崩溃：后端不退出，前端重连后恢复会话（TICKET-018 既有语义）。
3. SAFETY-1 联动：后端 code-0 自动重启逻辑在 socket 模式下仍生效；
   启动时清理陈旧 sock 文件（EADDRINUSE 安全处理）。
4. 扩展发现链路零改动：`apps/vscode-extension/src/discover.ts` 已扫描
   tmpdir 下 `bobo-gw-*.sock`，固定名 `bobo-gw-main.sock` 天然命中。
5. `bobo` TUI 命令行为不变（stdio 照旧），仅桌面端切 socket。

## 验收标准

- 专项测试：spawn env 断言 / 断连重连 / 陈旧 sock 清理 / TUI stdio 不受影响
- 实弹（缺一不可）：
  a. 桌面端启动后 `$TMPDIR/bobo-gw-main.sock` 存在且可连
  b. 强杀渲染进程 → 后端进程存活，前端重连后会话原样恢复
  c. VS Code 扩展在该 socket 上实连收发（Ask bobo 全链路）
- 全量回归零失败（基线 2722 passed / 2 skipped / 1 xpassed + 扩展 npm test 30/30）

## 流程

切分支前先打回滚标签；core/ 零改动则无需守卫适配，若动 gateway 文件按
白名单+标记先例（DESK-CLI 起）适配守卫；未终审不许 commit/merge/push；
收工报告落 `library/agent开发/TICKET-GW-SOCK完成报告.md`。
