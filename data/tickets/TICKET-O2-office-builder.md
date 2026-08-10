---
ticket: TICKET-O2
title: OFFICE MODE 老板开关与搭建器——/office + office_manager + 新窗口自动打开
branch: feat/ticket-o2
status: 待施工
author: Kimi 开票（依据设计稿 v0.3.1 + owner 新窗口裁决 2026-08-10）
date: 2026-08-10
authorized_paths:
  - bobo_tui_gateway/handlers/prompts.py
  - bobo_tui_gateway/server.py
  - tools/office_manager.py
  - ui-tui/
  - bobo_tui_gateway/static/entry.js
  - tests/
---

# TICKET-O2 /office 开关 + 搭建器 + 新窗口自动打开

## 一、定位

owner 亲手按下的第一个开关。O-1 造好了镣铐，R1 造好了总线，本票造"开公司的手"。

## 二、最高原则

1. **普通模式零影响**（同 O-1/票 C，每条验收配对照组）。
2. **/office 全世界只存在于 owner 终端**：员工（进程环境含 BOBO_ROLE）执行 /office 一律拒绝——"员工没有这个命令"。
3. 放行语义复用 AUTO 决策树，本票不造新的确认机制。

## 三、施工内容

### O2-1 /office 开关（prompts.py）

- `/office`（无参）翻转会话级 office 状态；状态存 `server.py` ctx（仿 `_auto_mode`：`ctx.office_state: dict[sid, {...}]`），resume/activate 恢复（仿票 F auto_state 同款处理）。
- **角色闸**：进程环境含 `BOBO_ROLE`（staff/dispatcher）→ 拒绝并提示"员工无 /office 命令"；写审计 `office.guard`。
- 开 → 返回引导语（"已进入 OFFICE 模式，告诉我需求：几个人配合、分工、几个窗口/几个 office"）+ 底栏指示（O2-4）。
- 关 → 走收尾（O2-3）。

### O2-2 搭建器（新工具 tools/office_manager.py）

**流程铁律（owner 2026-08-10 21:54 裁决）：/office 打开瞬间零 tmux 副作用**——只翻状态+亮底栏+回引导语，不建任何 session。owner 自然语言说配置 → 老板先出布局方案（session/pane/角色/启动命令清单）→ owner 确认 → 才调 launch。无默认配置、无自动搭建。

工具 `office_manager`，actions：`status` / `launch` / `teardown`。纪律全部内置在工具里，不靠 LLM 自觉：

- `launch`（参数：staff 数量、分工描述、session 名、窗口布局）：
  1. detached 建 tmux session（`tmux new-session -d`，沿用 tmux-office skill 纪律）
  2. 每个员工 pane 启动命令注入环境：`BOBO_ROLE=staff|dispatcher`（+ 有票时 `BOBO_TICKET`）
  3. 起 relay v2：`RELAY_SESSION=<session名>`（R1 已参数化，直接复用）
  4. 写审计 `office.setup`（布局、角色清单、session 名）
  5. 返回布局图文本
- `status`：读 tmux 列出本 office 的 session/pane/角色/存活状态
- 工具内所有 tmux 调用走 `execute_terminal` 执行（**不直接 subprocess**）——让 AUTO 决策树天然管放行/确认
- 安全红线：launch/teardown 只允许操作**本工具创建的 session**（内部登记台账）；拒绝 kill 用户已有的其他 session（如 bobo-pi-chat、staff_office 里用户手建的）；违反即拒绝 + 审计

### O2-3 收尾（teardown）

- 停 relay → 各员工 pane 发退出指令 → 问 owner session 保留还是清理（off 时一次性确认，不逐窗问）→ 写审计 `office.teardown`

### O2-4 底栏指示 + 新窗口自动打开

- 底栏：office on 时 StatusRule 显示 `OFFICE`（仿 AUTO ON，莫兰迪系另一色，ui-tui 改动）；gateway 发 `session.office_state` 事件 + resume 恢复（仿票 F 全链路）
- **新窗口自动打开**（owner 2026-08-10 裁决）：
  - 检测 `$TERM_PROGRAM`（`Apple_Terminal` → Terminal.app `do script "tmux attach -t <s>"`；`iTerm.app` → iTerm2 `create window with default profile command`；其他（含 vscode）→ 直接降级）
  - 降级方案：无权限/不支持 → 不失败，返回 attach 命令文本让 owner 手动
  - 放行语义：osascript 命令走 execute_terminal → auto on 自动放行（灰名单可逆副作用）、auto off 弹窗确认（owner 裁决）；命令含危险串仍被黑名单硬锁
- ui-tui 改动收工必须 `npm run build` + 拷 `dist/entry.js` → `bobo_tui_gateway/static/entry.js` + 产物提交

### O2-5 测试

- /office：翻转/角色闸拒绝/会话隔离/resume 恢复
- office_manager：launch 注入命令含 BOBO_ROLE（mock execute_terminal 断言）、只动自建 session 红线、status 解析
- 新窗口：TERM_PROGRAM 三分支 + 降级不炸
- 底栏：vitest OFFICE 指示（仿票 F 测试）
- 普通模式对照组：无 office 状态 /office 外一切行为不变

## 四、验收清单

1. O2-5 测试全过 + 全量零回归（基线 1850 passed / 2 skipped）
2. 员工环境 /office 拒绝实测
3. 红线实测：teardown 指向非自建 session → 拒绝 + 审计
4. **零副作用实测**：/office 开 + 未说配置前，tmux list-sessions 前后对比零新增
4. 前端 build 产物双份一致（md5）
5. 真实库三文件 md5 闸门
6. 五查汇报附测试原始输出

## 五、纪律

- 分支 `feat/ticket-o2` 自最新 main（bda9efd）切出；commit 前核对分支名；未终审不 merge 不 push。
- 不做：快照机制（O-3）、auto 决策树改动、agent_connect/team_relay_v2 代码改动（只调用）、O-1 决策链改动。
- 与稿/票有出入以票为准并在汇报中说明。
