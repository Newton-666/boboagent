---
ticket: TICKET-D1
title: 桌面版复活——Electron 升级最新 + 安全基线 + TUI 内核同步机制
branch: feat/ticket-d1
mode: 单人票（bobo 施工，Kimi 终审）
status: 排队（EV-1 之后开工）
author: Kimi 开票（owner 2026-08-12 裁决：桌面版为战略渠道，与 TUI 同步升级，成熟后买签名凭证发布）
date: 2026-08-12
assignees:
  staff-a: 施工
authorized_paths:
  - apps/desktop/
  - tests/
---

# TICKET-D1 桌面版复活

## 一、背景裁决（owner 2026-08-12）

- 桌面版（apps/desktop/，Electron ^33，数周未动）与 TUI 同步升级
- 体验足够好后 owner 购买签名凭证（Apple Developer $99/年）正式发布（D-3，另行立案）
- 现状风险：Electron 33 安全停更；打包是仓库快照，内核落后 main 两周以上

## 二、施工内容

### D1-1 Electron 升级

- 升到最新稳定大版本；过 changelog 破坏性变更；electron-builder 同步升级
- 安全基线：contextIsolation: true / nodeIntegration: false / sandbox 评估，
  逐项写明现状与结论

### D1-2 内核同步机制（核心）

- 打包时把仓库 commit 哈希 + 打包时间写入应用（about 页/启动日志可见）
- 启动自检：内核 commit vs 仓库 main 差距提示（"内核落后 N 个 commit"）
- 目标：桌面版与 TUI 的"同步"可验证，不靠口头

### D1-3 重打包验证

- npm run pack 出包，冷启动实测：开会话、跑一个工具调用、看日志路径
- 记录包体积/启动耗时基线

### D1-4 测试

- 同步机制：commit 哈希写入/读取/落后提示
- 全量零回归（基线 2050，桌面版测试独立）+ md5 闸门

## 三、验收清单

1. D1-4 测试全过 + 全量零回归 + md5 闸门
2. 实弹：新打包的桌面版冷启动可用，about 页显示内核 commit（owner 亲测）
3. 五查汇报附测试原始输出 + 包体积/启动基线

## 四、纪律

- 分支 `feat/ticket-d1` 自最新 main 切出；独立 worktree；未终审不 merge 不 push。
- 排期：EV-1 之后。
- 不做：签名/公证（D-3 需凭证）、桌面 UI 大改（D-2 另立）。
