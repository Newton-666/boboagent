# TICKET-VSC-2 VS Code 扩展：完整聊天 + diff 协作闭环 + 对比度治理

> 状态：待派工（2026-08-17 重写，Kimi；取代 08-17 早间旧版）
> 前置已落地：VSC-1（扩展骨架）、VSC-1B（侧边栏+连接死锁修复+选区上下文）、
> VSC-1C（渲染复刻桌面端）。当前 main `52bba249` 起。
> 分支：feat/ticket-vsc-2，自最新 main 切出；回滚标签 rollback/pre-vsc-2 先打再动工。
> 六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等 Kimi 终审。

## 背景（全部实证过）

面板已可用但仍是"问答版"：单会话无历史切换、无 diff 协作、对比度不达标。
owner 大学场景以 VS Code 为主战场，目标：**体验与能力对齐桌面端 + 多一件
桌面端没有的事（选区感知 + Explain）**。

### 本票必带的 VSC-1B/1C 血泪教训（每条都是实弹踩出来的）

1. views 声明必须 `"type": "webview"`，否则 VS Code 当树视图，provider 永不解析。
2. webview **内联脚本零容忍**：一律外置 media/*.js + nonce + 显式 CSP meta；
   改 chatPanel.ts 的 CSP 头时必须同步覆盖新资源来源。
3. webview 加载完成前 postMessage 会丢：所有 host→webview 消息必须过
   ChatPanel 的 ready 队列（已有，不许绕过）。
4. 任何提问入口都必须走 `buildUserMessage(selCtx, question)` 带选区上下文，
   不许发裸文本（已有 currentSelectionContext() 共用helper，直接复用）。
5. deploy.sh 已修 `rm -rf` 再拷贝；改 media/ 后必须 deploy + Reload Window 实弹。

## 施工项

改动面**只允许 `apps/vscode-extension/`**，仓库其余零 diff。

### A. 对比度治理（owner 原话："不要出现这种低对比的颜色"）

- 面板内所有**内容文字**对底色对比度 ≥ 4.5:1（WCAG AA），**可测量**：
  npm 单测里写一个对比度计算函数（相对亮度公式），对每条 (前景, 背景) 组合断言。
- 具体基调（在 52bba249 的加深基础上继续）：
  - `--text2`（#777，约 4.4:1）只允许用于占位符/禁用态；内容文字禁用。
  - `--text-muted`（#999，约 2.8:1）全面退出内容文字（含 .who 标签、状态栏、
    选区卡片头、代码注释以外的 hljs token）。
  - 代码块：正文 token 一律 var(--text)（#2d2d2d，15:1）；注释可灰但 ≥ #6b6b6b；
    数字/字面量保持深黄褐或更深；关键词橙 #e8913a 在浅底上偏亮（约 2.9:1），
    加深到 #b35a1e 级（≥4.5:1）；字符串绿 #50a14f（约 3.3:1）加深到 #3d8a3c 级。
  - 选区卡片下缘的"重影"（气泡边露出）顺手修掉。
- 桌面端同色系偏淡问题记 ROADMAP 囤单（本票不动桌面端）。

### B. 完整聊天

- 多轮会话历史滚动（现有单会话内已可多轮，补：New chat 按钮 + 会话切换列表，
  数据源走既有 RPC session.list / session.load——**先用SocketClient实探后端有无
  这两个方法，没有则记录报终审裁决，不许私加 RPC**）。
- 思考过程折叠展示（splitThinking 已有，渲染成可折叠块，样式对齐桌面端 think-box）。
- 工具调用过程：message.delta 之外的 tool 事件渲染成桌面端同款工具行
  （图标+名称+摘要，可折叠），不许 raw JSON。

### C. diff 协作闭环

- bobo 经工具写文件 → 后端事件流（tool.complete / 既有写文件事件）→ 扩展侧：
  ① 写入前对目标文件取内存快照；② 用 `vscode.commands.executeCommand('vscode.diff',
  快照uri(只读内存文档), 文件uri, 'bobo 改动')` 打开原生 diff；③ 面板同步出
  Accept / Reject 卡片：Accept 关闭 diff 即完；Reject 把快照写回（逐字节还原）。
- 快照用 TextDocumentContentProvider 提供只读内存文档，不落临时文件。
- 后端推送的事件字段先实探（events.jsonl / 真实会话观测），不许凭猜测定字段名。

### D. 台账可视（轻量）

- 面板底部可折叠区渲染 task_ledger 事件条目（标题+状态点），全 Markdown 渲染。

## 禁止项

- core/、gateway、桌面端零改动一行；只用既有 RPC/事件，缺方法报终审裁决。
- 不引入 npm runtime 依赖、不用 CDN；vendor 只准物理拷贝。
- 不做 vsix 打包分发（VSC-3）；不动 pairing/socket 逻辑。
- 不许为了好看发明新色板——全部从既有 token 加深/替换，新色值必须在票基准上
  逐个对照并在收工报告列出。

## 验收标准（终审逐条复跑）

1. `npm test` 全绿（基线 46/46 + 新增）；新增单测至少含：对比度矩阵全组合断言、
   diff 快照/Reject 逐字节还原、会话切换状态机、think 折叠渲染。
2. 全量回归 `.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` 零失败
   （基线 2722 passed / 2 skipped / 1 xpassed）。
3. 实弹（deploy.sh + Reload Window，终审执行）：
   a. 多轮问答上下文连续（第二轮记得第一轮）；
   b. 让 bobo 写一个测试文件 → VS Code 原生 diff 弹出 → Accept 落盘 /
      再改一次 → Reject 后文件逐字节还原（md5 前后一致）；
   c. 对比度：代码块/标签/状态栏截图，抽 3 处像素取色验证 ≥4.5:1；
   d. New chat + 会话切换可用（若后端缺方法，以终审裁决记录为准）；
   e. 截图 ≥3 态落盘 data/eval/。
4. 收工报告落 `library/agent开发/TICKET-VSC-2完成报告.md`（md5/git 实况/测试原话/截图）。

## 风险自查点

- 对比度改动只动 CSS 变量映射与具体色值，别动布局几何（圆角/padding 已对）。
- vscode.diff 的左侧快照必须只读；Reject 写回走 fs 不走编辑器 dirty 缓冲。
- tool 事件订阅靠 sid 过滤（GW-MULTI 全广播语义，别渲染别的会话的事件）。
- 思考折叠块默认收起；流式期间不要反复抖动高度。
