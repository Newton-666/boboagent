# TICKET-VSC-2 VS Code 扩展：完整聊天 + diff 协作闭环

> 状态：待派工（开票日期 2026-08-17，Kimi 撰写）
> 前置：VSC-1 已合并（d305652a）；**GW-SOCK 必须先落地**（自动连接前提）
> 分支：feat/ticket-vsc-2（自 GW-SOCK 合并后的最新 main 切出）
> 回滚标签：rollback/pre-vsc-2
> 设计依据：docs/DESIGN_VSCODE_INTEGRATION.md
> 动机：owner 大学场景——VS Code 是主战场，bobo 要从"问答版"长成"协作版"

## 施工

1. **完整聊天面板**：VSC-1 的 webview 从单问单答升级为多轮会话
   （历史滚动、会话切换列表、New chat）；渲染继续走扩展内 vendor 的
   Markdown 管线；中文讲解英文代码注释的 Explain 惯例保留。
2. **diff 协作闭环**：bobo 经工具写文件 → 后端事件流推送 → 扩展在
   VS Code 打开原生 diff 视图（vscode.diff），提供 Accept / Reject 按钮
   （Reject = 还原文件内容快照，快照在 diff 展示前落内存）。
3. **任务台账可视**：面板分区展示 task_ledger 事件（参考 Telescope
   渲染思路，全渲染 Markdown，不许 raw JSON）。
4. **会话上下文绑定**：默认绑定 VS Code 当前工作区根为 project_root
   （DESK-P1 既有字段，直接复用，不许改后端语义）。
5. **零干涉红线**：core/、gateway handlers 零改动；只允许使用既有 RPC
   与事件。缺方法 → 记录报终审裁决，不许私加。

## 验收标准

- 扩展单测新增：diff 快照/Reject 还原、台账渲染、会话切换状态机
  （npm test 全绿，原 30 项不破）
- 实弹（真后端 socket + Extension Development Host 或实装扩展）：
  a. 多轮问答上下文连续（第二轮记得第一轮内容）
  b. bobo 写一个测试文件 → VS Code 弹 diff → Accept 落盘 /
     Reject 后文件逐字节还原
  c. 台账区随工具调用实时更新
  d. 截图三态以上落盘 data/eval/
- 仓库全量回归零失败（基线 2722 + 2 skipped + 1 xpassed）

## 流程

切分支前先打回滚标签；扩展 .gitignore 相对路径（VSC-1 终审教训：
node_modules/out/vsix 必须真实拦住，commit 前 git check-ignore 验证）；
未终审不许 commit/merge/push；收工报告落
`library/agent开发/TICKET-VSC-2完成报告.md`。

## 分期备注

VSC-3（完整桌面端体验搬进 VS Code + vsix 私有分发）在 VSC-2 终审后另开。
