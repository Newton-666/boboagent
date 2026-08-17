# 票 VSC-1C：VS Code 面板渲染对齐桌面端（复刻，不创新）

分支 `feat/ticket-vsc-1c`，自最新 main（`548933f9`）切出。
回滚标签 `rollback/pre-vsc-1c` 先打再动工。
六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等 Kimi 终审。

---

## 背景（Kimi 实测定案）

VSC-1B 已打通链路（连接/配对/发送/选区上下文全通，owner 实测确认）。
现状问题（owner 原话收敛）：面板是"粗糙版"——行间距排版差、用户消息和 bobo 回复
在视觉上拉不开差异、初始空态没有桌面端那行标题字、Markdown 只有一个 100 行的
inline mini-renderer（renderInto，只认 `code`/`**`/换行），代码块/表格/列表全废。

桌面端基准（终审时已核实，照抄对象）：
- `apps/desktop/dist/index.html:96-159`——欢迎屏（#welcome-title，font-reply 700 36px）、
  消息气泡（.msg 圆角 12px padding 10/18、.msg.user 右对齐 bg2+border、.msg .who 12px 600）、
  代码块（#f3f2ea 底、SF Mono 13px）、diff 增色（#7ec87b/#f48771）、表格样式
- 桌面端正文渲染管线：marked + DOMPurify + highlight.js（vendor 本地，
  index.html:727/1315-1319），流式半截语法由 marked 容错 + DOMPurify 兜底

目标（owner 原话）："复刻一遍就行"——VS Code 面板的渲染观感对齐桌面端，不创新设计。

## 施工项

改动面**只允许 `apps/vscode-extension/`**。仓库其余零 diff。

1. **渲染管线替换**：废弃 chatPanel renderInto mini-renderer。把桌面端 vendor 的
   marked.min.js / purify.min.js / highlight 相关文件拷入 `apps/vscode-extension/media/vendor/`，
   `media/chat.js` 里 bobo 回复（delta 流式 + complete 定稿）走
   marked.parse → DOMPurify.sanitize 管线；流式期间允许半截语法容错渲染。
   CSP 的 script-src 补 nonce 已在前票就位，外置脚本按现有模式加 nonce 引用即可。
2. **消息气泡复刻**：用户消息右对齐气泡（bg2+border 圆角 12）、bobo 回复左对齐
   无气泡带 "bobo" .who 标签；行间距/字号/字体栈对照 index.html:96-159 逐个抄值；
   代码块/行内 code/表格/diff 增色样式同步抄。
3. **空态欢迎**：面板无消息时显示桌面端同款标题 "Let's finish up something today."
   （font-reply 700 大字号居中），有消息后消失。子标题不加（桌面端 P2 已去掉）。
4. **选区卡片**：保留现有功能，样式微调到与气泡同一套 design token。
5. webview 消息协议不变（kind: session/explain/selection/pairing/event/delta/complete），
   只改渲染层。

## 禁止项

- 不改 `src/extension.ts` / `src/socketClient.ts` / `src/sessionFlow.ts` 的任何逻辑
  （链路已验收，本票纯渲染）；唯一例外：如 CSP meta 需加 highlight.js 的样式来源，
  允许改 chatPanel.ts 的 renderHtml 头。
- 不引入 npm runtime 依赖（vendor 文件物理拷贝，不用 CDN——CSP 也不允许）。
- 不做 diff 协作/Apply 按钮（VSC-2 范围）。
- 不动桌面端一行。

## 验收标准（终审逐条复跑）

1. `npm test` 全绿（基线 40/40）；新增单测：markdown 管线对 代码块/表格/加粗/半截代码块
   四例快照断言（纯函数可测）。
2. 全量回归 `.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` 零失败
   （基线 2722 passed / 2 skipped / 1 xpassed）。
3. 实弹（终审执行）：deploy.sh 部署 + Reload Window 后——
   a. 空面板显示 "Let's finish up something today." 大标题；
   b. 发问后用户气泡右对齐、回复含代码块时带 #f3f2ea 底色等宽字体；
   c. 让 bobo 返回一段含表格的回复，表格正常渲染（对照 TEL-b 转义教训）；
   d. 截图对比桌面端同内容，观感一致。
4. 收工汇报落盘 `library/agent开发/TICKET-VSC-1C完成报告.md`，含 md5/git 实况/截图。

## 风险自查点

- CSP：新增 vendor 脚本全部走 nonce + 本地 asWebviewUri；禁止 eval/new Function
  （highlight.js 某些版本有用，选用无 eval 的用法，DOMPurify 配置禁掉危险标签）。
- marked 流式半截代码块会渲染成未闭合 pre——complete 时重渲染定稿即可。
- 拷 vendor 文件注意 license 头注释保留。
- 面板窄（~300px）：气泡 max-width 85% 在窄面板下别溢出，横向滚动只给 pre。
