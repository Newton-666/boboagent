# bobo × VS Code 深度集成设计构想（VSC 线）

> 状态：构想备案，VSC-1 待 DESK-P2 收口后开票
> 动机：owner 大学学习场景——在 VS Code 里读到不懂的代码，就地选中直接问 bobo
> 日期：2026-08-17

## 架构前提（已具备）

- bobo desktop = Electron 壳 + 本地 gateway（WebSocket RPC + 事件总线）
- widget.html 已证明 gateway 支持**多客户端**接入（第二前端消费同一事件流）
- DESK-P1 后 gateway RPC 面基本冻结，扩展有稳定协议可用
- 文件工具绝对路径解析（edit_file resolve），bobo 改项目文件 → VS Code 自动刷新（零成本"连接"今天已存在）

## 分期

### VSC-1 最小闭环：选中即问
- VS Code 扩展（TS），webview chat 面板，连本地 gateway ws
- 右键 "Ask bobo" / 快捷键：自动附带上下文（文件路径、选中片段、语言、行号、诊断报错）
- bobo 流式回答，Markdown 渲染（复用桌面端管线思路）
- **Explain 模式**（学习场景特调）：回答默认教学视角——讲概念、讲为什么、给延伸阅读，不只给答案；实现 = prompt 前缀，成本极低
- 扩展检测 gateway 未运行时给出人话提示（如何启动 bobo）

### VSC-2 协作闭环
- bobo 改文件 → VS Code 实时 diff 视图 → accept / reject
- 任务台账 / 工具调用流面板（Telescope 移植）

### VSC-3 发布
- vsix 本地包 → 成熟后考虑 marketplace

## 安全与边界

- gateway 只监听 127.0.0.1；扩展连接需一次性配对确认（防本地其他进程冒连）
- Explain 模式不改主推理模型（owner 红线：能力不降）
- 扩展自身零遥测

## 与队列关系

- DESK-P2（英文化）→ VSC-1
- 连接韧性票（19% 长尾）与 VSC-1 并行不冲突（不同改动面）
- VSC-1 落地后，DESK-V1 票据面板的渲染资产可被 VS Code 面板复用
