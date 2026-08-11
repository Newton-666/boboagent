---
ticket: TICKET-O5
title: 新窗口前置——office_manager 开窗后 activate 把窗口推到台前
branch: feat/ticket-o5
mode: 单人票（bobo 施工，Kimi 终审）
status: 待施工
author: Kimi 开票（依据 2026-08-11 实测：窗口已开但藏在后台，owner 没看到）
date: 2026-08-11
assignees:
  staff-a: 施工
authorized_paths:
  - tools/office_manager.py
  - tests/
---

# TICKET-O5 新窗口 activate 前置

## 一、事故背景

2026-08-11 14:45 实测：老板搭建 stage0-2staff 后汇报"新 Terminal 窗口已打开并 attach"，
但 owner 屏幕上没看到任何新窗口。Kimi 查 tmux 实况：`stage0-2staff attached=1`
（/dev/ttys019）——窗口**真实存在**，osascript 成功了。

根因：`tools/office_manager.py::_open_new_window` 的 osascript 只有
`tell application "Terminal" to do script ...`，**没有 activate**——macOS 开了窗口
但不推到台前，被当前窗口挡住。

## 二、施工内容

- Terminal.app 分支：do script 之前（或之后）补 `tell application "Terminal" to activate`。
- iTerm.app 分支：同样补 activate。
- **Ghostty 分支（新增，owner 2026-08-11 19:29 裁决：团队终端迁往 Ghostty）**：
  - 先侦查：Ghostty 的 `$TERM_PROGRAM` 实际值（预期 `ghostty`）、是否支持 AppleScript 开窗
    （Ghostty 的 osascript 支持有限，必须先实测，不许假设）。
  - 支持 → 加独立分支开窗 + 前置；不支持 → 显式识别 Ghostty 并走降级文案
    （文案里写明"Ghostty 不支持脚本开窗"，不混进通用"未知终端"分支）。
  - 侦查结论写进五查报告，作为后续终端适配的判据。
- 降级分支（其他终端返回 attach 文本）：不动。
- 失败文案分支：不动。
- 测试：断言生成的 osascript 命令串含 `activate`；Ghostty 分支按侦查结果覆盖；
  三分支回归；全量零回归（基线 2006）+ 真实库 md5 闸门。

## 三、验收清单

1. 测试全过 + 全量零回归 + md5 闸门
2. 实弹（**在 Ghostty 中验收，owner 2026-08-11 裁决 Ghostty 为主力终端**）：
   office_manager launch 一个新办公室 → 新窗口**跳到台前**（owner 亲测确认）；
   Ghostty 不支持脚本开窗时，降级文案实弹确认显示正确
3. Terminal/iTerm 作为兼容性分支回归（不炸即可）
4. 五查汇报附测试原始输出 + Ghostty 侦查结论

## 四、纪律

- 分支 `feat/ticket-o5` 自最新 main 切出；未终审不 merge 不 push。
- 一行级改动，不许顺手重构 office_manager 其他部分。
- 不做：vscode 等其他终端的开窗支持（降级语义保持）。
