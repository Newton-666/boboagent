# TICKET-GUI-F11 —— 自动命名持久化（重启不丢，用户命名优先，TUI 同步）

> 施工前必读 docs/GUI-LESSONS.md。分支 feat/ticket-gui-f11（自最新 main 切出）。未 commit 等终审。

## 背景（owner 2026-08-14 实弹）

GUI 自动起的会话名，重启后丢失，回退成默认数字时间戳名。

## 根因（Kimi 已定位）

自动命名只更新前端/内存，未走持久化。`handle_session_rename`（sessions.py:375）是手动通道——设 `user_named=true` 落盘。自动命名若复用它会把 user_named 也置真（破坏 F7"用户命名优先"），所以当时没接落盘。

## 修法

1. `handle_session_rename` 增加可选参数 `auto: bool`（默认 False 保持现状）：`auto=true` 时落盘标题但**不设 user_named**（用户后续手动命名仍可覆盖，且自动命名对未命名会话可再更新）
2. 前端自动命名触发点改调 `session.rename { auto:true }`
3. 落盘字段不变（title 本就进会话文件）——TUI 读同一文件，自动同步，无需改 TUI
4. 防线：auto=true 且会话已 user_named=true → 拒绝覆盖（返回 ok 但不动标题）

## 验收

- 专项：①auto 命名落盘重启后仍在 ②auto 不置 user_named ③auto 不覆盖 user_named 会话 ④手动命名后 auto 跳过（F7 语义不破）
- 全量零回归 + md5 闸门 + L12 汇报
