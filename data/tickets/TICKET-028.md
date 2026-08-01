# 票 TICKET-028：单实例守卫授权范围——误杀修复（Kimi 紧急直修）

## 案情（2026-08-01 TUI 冷启动崩屏）

026 的守卫杀伤面过大：任何 gateway 子进程启动都会清理 pidfile 里的"残留实例"。
第三方 agent（claude code 基准测试、pytest 野子进程）在同仓库起测试 gateway
时未设 BOBO_TEST_MODE，守卫把**用户的真 bobo gateway** SIGKILL，
TUI 瞬间断粮崩屏（10:58 日志实锤 pid=97295 被误杀）。

## 修复

- 守卫仅在 `BOBO_GW_GUARD=1` 时启用；node 前端 spawn 时显式设该旗标
  （gatewayClient.ts），python 见旗标才执行清理
- 测试/基准/其他 agent 的子进程不携带旗标 → 永不触发守卫
- 金标准测试：无旗标时 pidfile 指向的存活实例**不被清理、pidfile 不被覆写**

## 验证

- tests/test_ticket026_startup_guard.py 6 项全绿（含误杀案复现场景）
- 全量 1444 passed / 2 skipped 零回归
