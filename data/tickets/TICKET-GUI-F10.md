# TICKET-GUI-F10 —— 事件流串台修复（P0）

> 施工前必读 docs/GUI-LESSONS.md。分支 feat/ticket-gui-f10（自最新 main 切出）。未终审不 commit。

## 背景（owner 2026-08-14 实弹）

会话 A 运行中，切到会话 B（或新建会话），A 的 message.delta/tool 事件流直接渲染进 B 的窗口——"新会话加载了老会话正在运行的任务"。

## 根因（Kimi 已定位）

`server_utils.emit` 的 params 里带 `session_id`，但 apps/desktop/dist/index.html 的全部事件回调（on('message.start') / on('message.delta') / on('message.complete') / on('tool.start') / on('tool.complete') / 及其他渲染类事件）**不过滤 sid**，谁的流都往当前窗口渲染。

## 修法

1. 统一入口过滤：在事件分发层（on() 的回调包装或每个 handler 开头）判断 `params.session_id`（注意：sid 在 params 顶层，不在 payload 里——先读代码确认回调拿到的数据结构，设计适配）：
   - `session_id === currentSessionId` → 正常渲染
   - 不一致 → **不渲染**，但该会话的事件要缓存（建议：后台会话只记录"有活动"标记 + 轻量缓存最近事件用于切回时 resume 已有机制兜底即可，不搞复杂的前台缓存回放——切回时 F9 的 resume 忙分支会拉全量，够用）
2. 侧栏可以给"后台活动中"的会话加一个小圆点指示（弱色，色板取色），可选加分项
3. 中断按钮（Stop）：只对 currentSessionId 发 session.interrupt（现状已是，不动）

## 验收

- 专项 tests/test_ticket_gui_f10.py：node 实跑模拟双会话——A 会话事件流灌入时 currentSessionId=B，断言 B 窗口零渲染；切回 A 后 resume 数据完整
- F6/F6B/F6C/F6D/F8/F9/V2 系全部回归不破；全量零回归；md5 闸门
- 收工汇报按 L12：正文只写人话摘要，证据落盘
