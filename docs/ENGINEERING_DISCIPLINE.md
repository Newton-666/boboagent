# 施工纪律（ENGINEERING DISCIPLINE）

> TICKET-ENG2 (b③) 建立：2026-08-12 六连发事故（5 个旧 office tmux 会话僵尸前端
> 集体重连风暴 → 内存飙升 → macOS jetsam 击杀活跃前端）后，将血泪教训固化为纪律。
> 违反本条纪律 = 引入同类事故风险，施工前必读。

## 1. 施工并发限流：真实后端并发 ≤2（硬约束）

E2E / 冒烟测试 / 手动验证中，**同时存活的真实 gateway 后端进程数不得超过 2**。

- 测试侧硬约束已落地：`tests/backend_guard.py`（`spawn_backend` / `release_backend` /
  `shutdown_all`）。所有测试内 Popen 真实后端必须走 `spawn_backend`，超过 2 个抛
  `BackendConcurrencyError`。
- 手动验证起多个后端时自行计数，用完即 `terminate`。
- 理由：后端进程每个占 ~200-500MB RSS，3+ 并发即可触发内存风暴（六连发实锤场景）。

## 2. Office 散场纪律：演练/施工结束必须 kill-session 清场

团队演练、office 施工、双 TUI 联调结束后，**必须**清理所有 tmux 会话与孤儿进程：

```bash
# 列出残留会话
tmux ls

# 逐个杀掉（或按事故名批量）
tmux kill-session -t <session-name>

# 兜底：确认没有孤儿前端/后端残留
ps aux | grep -E "bobo_tui_gateway|ui-tui|entry\.tsx" | grep -v grep
```

- 本次事故根源：5 个旧 office tmux 会话（stage0-2staff、office-2w 等，周一/周二启动）
  的前端一直活着，22:59:54 同一毫秒集体拉起新后端（孤儿后端 PPID=1，60s 后自动退出），
  内存瞬间飙升 → jetsam 击杀活跃前端 → SIGKILL 无清理 → 鼠标模式残留乱码。
- 原则：**开工建会话，收工必清场**。任何跨天残留的 tmux 会话都是潜在僵尸。

## 3. 防僵尸机制（双层自动退出）

| 层 | 机制 | 超时 |
|----|------|------|
| 前端 | TUI 闲置自动退出（无输入/无后端活动）| 默认 30 分钟，`BOBO_TUI_IDLE_TIMEOUT_MINUTES` 可调，0=禁用 |
| 后端 | gateway 无重连自动退出 | 60s（已有） |

- 前端闲置退出会清理终端模式（鼠标/kitty 键盘等），见 `ui-tui/src/lib/idleExit.ts`。
- 被 SIGKILL 的前端无法自我清理——依赖下次启动时的终端复位兜底
  （`resetTerminalModes`，启动/退出双路径），见 `ui-tui/src/lib/terminalModes.ts`。

## 4. 终端复位保底（ENG-2a）

- 启动：进入交互界面前先发鼠标模式复位序列（`\e[?1002l \e[?1003l \e[?1006l` 全套）。
- 退出：SIGTERM/SIGINT/正常 exit 路径全部走 `resetTerminalModes`（onSignal + cleanups + 'exit' hook 三层兜底）。
- SIGKILL 防不住，由下次启动复位兜底——这是最后一道防线，不可移除。
