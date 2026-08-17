# TICKET-GW-MULTI socket 后端多客户端支持（桌面端 + VS Code 并发在线）

> 状态：待派工（开票日期 2026-08-17，Kimi 撰写，附实测根因）
> 前置：GW-SOCK 已合并（4a5e3074）
> 分支：feat/ticket-gw-multi（自最新 main 切出）
> 回滚标签：rollback/pre-gw-multi

## 根因（Kimi 实测，非猜测）

`_run_socket_backend`（bobo_tui_gateway/entry.py）`listen(1)` + 单连接服务循环：
accept 一条 → 服务至断开 → 才 accept 下一条。桌面端长连占线时，VS Code 扩展
TCP 握手成功（backlog）但永远得不到服务 → 5s 超时 → "not connected"。
实测：桌面端断开时扩展链路全通（15:43 session.create + prompt.submit 流式
complete）；桌面端在线时扩展挂死。

## 施工

1. socket 后端改为每连接一个服务线程（threading.Thread per accepted conn），
   共享既有 ctx（sessions/engine 单例，现有锁机制沿用）。
2. 事件广播：engine 事件当前通过"活跃 transport"单播（transport.py
   _active_transport），需升级为多订阅者分发——每个连接独立 SocketTransport，
   事件按 session_id 分流或全广播（择一并在报告论证；建议全广播 + 客户端
   按 sid 过滤，widget.html 已有 sid 过滤先例 V4B）。
3. 空闲超时语义升级：全部客户端断开才计空闲（TICKET-027/030 语义保持）。
4. 防双实例守卫、陈旧 sock 清理、TUI stdio 模式全部不许回归。
5. 并发安全：session.create / prompt.submit 双客户端并发各跑一次，
   会话数据不串不丢（现有 sessions_lock 覆盖则断言即可）。

## 验收标准

- 专项（node --test 增补）：双客户端并发连接 → 各自收 ready → 各自
  session.create → 甲发 prompt 乙收事件（或正确隔离）→ 甲断开乙不受影响
- 实弹：桌面端在线 + VS Code 扩展同时在线，Ask bobo 流式回答到达，
  桌面端会话不受影响
- 全量回归零失败（基线 2722 passed / 2 skipped / 1 xpassed +
  socket 专项 6/6 + 扩展 30/30）

## 流程

切分支先打回滚标签；守卫按白名单+标记先例适配；未终审不许
commit/merge/push；收工报告落 library/agent开发/TICKET-GW-MULTI完成报告.md。

## 教训备案（进 TICKET-WRITING）

GW-SOCK 终审只验了"扩展单连"场景，没验"桌面端+扩展并发"——多客户端
产品的验收必须包含并发在线用例。
