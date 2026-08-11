# Tmux Office 保护与恢复 Standard v2

> keywords: tmux office, 办公室, 调度, orchestrator, 保护层, 误关, 恢复, 员工卡住, relay, 覆盖, 分支切换, 降级, 编制, 执法层, protected_paths
> 触发：用户要求建立/管理多个 tmux 办公室、调度员监督员工、出现"界面被覆盖"或"员工卡住"或"调度层报错"时。
> 定稿：TICKET-O3 · O3-2（2026-08-11）——新增执法层摘要 / relay 降级机制 / 编制规则三章。本手册是建议性文档，不承载任何"开关/拦截"语义（执法在 O-1 代码层）。

## 0. 核心原则（违反即事故）

1. **一个办公室 = 一个独立 tmux session**。绝不把两个办公室放进同一个 session 的不同 window。
2. **建新 session 必须 detached**（`tmux new-session -d -s 名字`），绝不碰正在 attach 的 client 屏幕。
3. **绝不在用户正 attach 的 session 里执行** `new-window / select-window / move-window / kill-window`——这会把用户视图切走，造成"覆盖"错觉。
4. **误关终端 ≠ 数据丢失**：session 在后台继续跑，`tmux attach -t 名字` 随时回来。
5. **文件属于 git 分支**：relay/工具脚本必须在当前分支存在；跨分支运行会 ImportError/工具加载失败。
6. **保护层必须常驻**：`~/.tmux.conf` 里 `destroy-unattached off`。

## 1. 标准办公室布局（当前生效）

| 办公室 | tmux session | 成员 | 职责 |
|--------|-------------|------|------|
| 员工办公室 | `staff_office` | 4 员工（bobo/hermes/claude/pi） | 干活、产出 |
| 调度层办公室 | `orchestrator_office` | 2 调度员（bobo + pi） | 只读监督、发现/警告/汇报 |

- 老板（本会话）不占 tmux，通过 execute_terminal 遥控。
- relay 脚本 `tools/team_relay_v2.py`：`SES = "staff_office"`，PANES 指向 staff_office:0.0~0.3。

## 2. 保护层配置（~/.tmux.conf，必须存在）

```tmux
set -g destroy-unattached off   # 最后一个客户端断开时保留 session
set -g allow-rename off         # 窗口名不自动跳变
bind x confirm-before -p "kill-pane #P? (y/n)" kill-pane   # 杀 pane 前确认
```

验证：`tmux show-options -g destroy-unattached` 应输出 `off`。

## 3. 建新办公室的操作纪律

```bash
# ✅ 正确：detached 创建，零干扰
tmux new-session -d -s 新办公室名 -n 窗口名

# ❌ 错误：会覆盖用户当前视图
tmux new-window -t 现有session -n 办公室名
```

- 创建后把 attach 命令交给用户自行执行：`tmux attach -t 新办公室名`。
- 给调度员下指令用 `tmux send-keys -t 办公室:窗口.pane "消息" Enter`，消息要加【大老板指令】前缀。

## 4. 误关/丢失恢复流程

1. `tmux list-sessions -F '#{session_name} windows=#{session_windows} attached=#{session_attached}'` 确认 session 还在。
2. 还在 → 直接 `tmux attach -t 名字` 恢复；`Ctrl+b d` 脱离。
3. 不在 → 查回收站/进程：`pgrep -f "tsx src/entry.tsx"`，用原命令重启 TUI。

## 5. 员工卡住处理（禁止 Ctrl+C 杀引擎）

bobo 是单进程 TUI（zsh → `npm exec tsx src/entry.tsx`），**Ctrl+C 会杀掉整个引擎**（状态显示 `引擎退出: interrupted`，Enter 无法唤醒）。

正确处理顺序：
1. 先观察 1-2 分钟，看是否自行消化队列（relay 已停则不会灌新消息）。
2. 需中断时**直接重启**：`pkill -f "tsx src/entry.tsx"` 后在同一 pane 重新 `cd ui-tui && npx tsx src/entry.tsx`。
3. 重启会清上下文，但产出已落 Obsidian 汇总，不亏。

## 6. relay/工具脚本跨分支缺失恢复

症状：调度层 TUI 报 `ImportError: cannot import name 'X'` 或 `工具加载失败: 某脚本.py`。

排查：
```bash
git branch --show-current          # 当前分支
git ls-files | grep -i relay       # 当前分支是否有该文件
git branch --list "feat/team-relay-v2"   # 文件所在分支
```

恢复：
```bash
git checkout <文件所在分支> -- tools/<缺失文件>.py   # 取文件，不切分支
# 然后修复 import 引用（函数改名后要同步）：
#   pi_idle → pi_finished（pi_relay.py 当前版本已改名）
# 最后验证：
python3 -c "import sys; sys.path.insert(0,'tools'); import team_relay_v2"
```

## 7. 停止监督权（调度员职责）

出现以下任一情况，调度员必须警告 4 员工停止并收敛：
1. 讨论超 6 轮或 relay 转发满 24 次
2. 运行超 1 小时
3. 任务已产出结论
4. 任一方 token 接近上限
5. 大老板叫停
6. 话题跑偏超 2 轮

停止信号：`tmux send-keys -t staff_office:0.<n> "【调度员·停止信号】..." Enter`。

## 8. 收尾检查清单

- [ ] relay 无残留进程：`pgrep -f team_relay` 为空
- [ ] 全员空闲：各 pane 有提示符（`>`/`❯`/`~`），无 Working/reflecting
- [ ] 讨论汇总已落 Obsidian（`library/agent开发/四Agent团队讨论汇总-*.md`）
- [ ] 调度员收到停止信号且确认收敛
- [ ] session 状态正常：`tmux list-sessions` 两个办公室都在

## 9. 执法层摘要（O-1 一句话版 · 只引用不管执法）

> TICKET-O3 · O3-2 定稿章。本手册不管执法、不承载拦截语义；执法实现在代码层（O-1），这里只给引用指针。

- OFFICE MODE（`BOBO_ROLE=staff|dispatcher`）下，员工写权限由 **票据 `authorized_paths` 豁免清单** 决定；受保护路径清单在 **`data/protected_paths.json`**（globs 表达式，目录前缀即命中）。
- 一句话：**员工只能写票据豁免的路径，受保护路径清单见 protected_paths.json，明细以代码与票据为准。**
- 事后抓漏（O3-1）：office 角色会话写操作会生成 `data/guardsnap_<sid>.json` md5 快照，收工比对不一致写 `office.snap` 审计并在回复中告警——快照是抓漏不是执法，不阻断收工。
- 查证路径：`core/command_safety.py`（`load_protected_paths` / `is_protected`）、`core/engine.py`（`_office_decide` / `_snapshot_protected_paths`）。

## 10. relay 降级机制（故障时 tmux 直派 · 每次降级必须写审计）

> TICKET-O3 · O3-2 定稿章，来自 2026-08-11 实战经验制度化。正常派工一律走 relay（team_relay_v2），tmux 直派是**降级通道**，不是默认通道。

1. **判定 relay 故障**：relay 进程死亡（`pgrep -f team_relay_v2` 为空）、双向转发 2 分钟无进展、或 relay.state 指针停滞且日志无"忙碌暂缓"以外的报错。
2. **降级动作**：调度员 `tmux send-keys -t 办公室:0.<n> "【降级直派】..." Enter` 直派消息。
3. **每次降级必须写审计**：在当天工作汇总/笔记中记录降级事件——时间、触发原因（故障现象）、直派消息、恢复时间。格式：`relay 降级：<时间> 原因=<现象> 直派=<pane> 恢复=<时间>`。
4. **恢复后回归**：relay 恢复运行后停止直派，回到 relay 通道；直派期间 relay 收不到的消息视为已降级，不补发。
5. **纪律红线**：relay 正常时禁止直派（直派=绕过 relay 单实例/转发审计，破坏派工证据链）；降级不写审计视同事故。

## 11. 编制规则（标准小队 · relay 饱和线）

> TICKET-O3 · O3-2 定稿章。编制是建议性配置，不承载拦截语义。

- **标准小队**：1 调度（dispatcher，只读监督派工）+ 2-3 员工（staff，按模块干活）+ 1 评审（reviewer，只读挑刺）。示例：`bobo(调度) + pi + hermes(员工) + claude(评审)`。
- **relay 饱和线 6 人**：轮巡名单超过 6 人时 relay 轮询间隔内消息积压风险显著上升；超员应拆分为多个办公室（一个办公室 = 一个 tmux session，见第 0 章）。
- **按模块不切工序派工**：一个员工包干一个模块的完整工序（施工→测试→自验），不把同一模块的工序切给多人——减少 relay 上下文搬运与交接损耗。
- **两人最小配置**：调度 + 1 员工即可开票（如 O-3 豁免的 `RELAY_ORDER=bobo,pi`），评审可后置。

## 12. 版本记录

- v1（2026-08-11 前）：八章基础版（布局/保护层/建办纪律/恢复/卡住/分支缺失/停止监督/收尾）
- v2（2026-08-11，TICKET-O3 · O3-2 定稿）：+执法层摘要（§9）/ relay 降级机制（§10）/ 编制规则（§11）
