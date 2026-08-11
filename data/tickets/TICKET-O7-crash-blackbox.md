---
ticket: TICKET-O7
title: 崩溃取证黑匣子 + SSE 断流致死真因（Ghostty 20:08 事故）
branch: feat/ticket-o7
mode: 单人票（bobo 施工，Kimi 终审）——侦探活，优先黑匣子
status: 待施工
author: Kimi 开票（依据 2026-08-11 20:08-20:14 Ghostty 前端连死两次事故）
date: 2026-08-11
assignees:
  staff-a: 施工
authorized_paths:
  - bobo_tui_gateway/entry.py
  - bobo_tui_gateway/server.py
  - core/llm_caller.py
  - tests/
---

# TICKET-O7 崩溃取证黑匣子 + SSE 断流致死真因

## 一、事故现场（2026-08-11，全部日志实证）

```
20:08:03-09  SSE 流断流 ×4（ConnectionError → api.deepseek.com，session=?）
20:09:45     Ghostty bobo 执行 office.setup（office-bobo-hermes）
20:11:31     gateway pid 29099 重启（第一次死亡后）
20:13:53     gateway pid 30749 重启 → 前端连上 4 秒后断开（eof）
20:14:57     60s 无重连自动退出，窗口消失
```

- Ghostty 应用本体未崩（无 .ips 报告，App 进程存活）——死的是 bobo 前端 node 进程，窗口随之关闭。
- **证据断点**：前端（node entry.js）的 stderr 无任何落盘，死前输出不可见，真因无法锁定。

## 二、施工内容（顺序即优先级）

### O7-1 黑匣子（必须先做）

- gateway 启动前端子进程时，把 node 前端 stderr 持久化到
  `data/logs/frontend_<pid>.log`（追加模式，含启动时间戳头）。
- 前端异常退出时，gateway 写一条 CRITICAL 日志：退出码 + stderr 尾部 50 行内联进
  `data/logs/bobo.log`（黑匣子外的第二保险）。
- 日志滚动：frontend_*.log 保留最近 20 份，超出清理。

### O7-2 真因挖掘（有黑匣子后）

- 沿 "SSE 断流（llm_caller ConnectionError）→ 前端死亡" 的链路排查：
  断流重试/超时路径是否有未捕获异常抛到前端、gateway 在断流风暴下的 rpc 行为。
- 若真因需改 llm_caller 重试/熔断语义，**只在证据充分时改**，并在五查中附
  事故时间线与修复前后行为对比。

### O7-3 测试

- 黑匣子：stderr 落盘、异常退出 CRITICAL 内联、滚动清理
- 全量零回归（基线 2016）+ 真实库 md5 闸门

## 三、验收清单

1. O7-3 测试全过 + 全量零回归 + md5 闸门
2. 黑匣子实弹：故意 kill 前端 → `data/logs/frontend_<pid>.log` 与 bobo.log
   CRITICAL 双双有记录（终审亲手复验）
3. 真因结论：要么修复+回归测试，要么如实写"未复现，黑匣子待下次事故"——
   禁止无证据断言已修复
4. 五查汇报附测试原始输出

## 四、纪律

- 分支 `feat/ticket-o7` 自最新 main 切出；未终审不 merge 不 push。
- 排期：O-5 之后单独施工（老板当前在 O-5）。
- 不做：office_manager、relay、injector（O-4 已合并）。
- 取证现场：`office-bobo-hermes` tmux 会话保留至本票关闭。
