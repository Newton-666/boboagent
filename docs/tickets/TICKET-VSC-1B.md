# 票 VSC-1B：VS Code 扩展侧边栏落地 + 连接死锁双 bug 修复

分支 `feat/ticket-vsc-1b`，自最新 main（`9d6aa67f`）切出。
回滚标签 `rollback/pre-vsc-1b` 先打再动工。
六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等 Kimi 终审。

---

## 背景（Kimi 实测定案，非猜测）

owner 在 VS Code 使用 Ask bobo 永远报 `bobo: not connected to the bobo gateway.`。
Kimi 于 2026-08-17 下午逐项实证排除了后端与链路：

- 后端（GW-MULTI 新代码，PID 88434）监听 `$TMPDIR/bobo-gw-main.sock` 正常；
  Kimi 用扩展同一份 `out/socketClient.js` 实测：gateway.ready ✓、session.create ✓、
  桌面端占线下并发流式问答 ✓（deltas→complete 全通）。
- VS Code 扩展宿主 TMPDIR 与终端一致；settings.json 无 bobo.socketPath 错误覆盖；
  安装版扩展（~/.vscode/extensions/bobo-local.bobo-vscode-0.1.0/）与仓库 out/ 逐字节一致。

根因是扩展自身两个 bug 叠加（均已逐行核实）：

**Bug 1 —— 侧边栏面板没有注册入口。**
`src/extension.ts:38` 调用了 `vscode.window.registerWebviewViewProvider('boboChat', ...)`，
但 `apps/vscode-extension/package.json` 的 `contributes` 里**没有 `viewsContainers`
和 `views` 声明**（Kimi 已打印全文核实：只有 commands/menus/keybindings/configuration）。
VS Code 的 webview view 必须在 package.json 声明容器+视图才会出现在侧边栏——
当前 Activity Bar 没有 bobo 图标，面板永远不可能被打开。

**Bug 2 —— sessionId 赋值错误依赖面板存在。**
`src/extension.ts:157-162`（onConnect 回调内）：

```ts
void client.send('session.create', {}).then((r: any) => {
  const sid = r && r.session_id;
  if (sid && st.panel) {        // ← st.panel 为 null 时 sid 被静默丢弃
    st.sessionId = sid;
    st.panel.setSession(sid);
  }
}).catch(() => {});
```

`st.panel` 只在 `resolveWebviewView`（侧边栏视图被打开）时创建（extension.ts:39-41）。
两 bug 叠加成死锁：面板打不开（Bug 1）→ `st.panel` 恒 null → session.create 明明成功，
sessionId 被丢弃（Bug 2）→ `askWithContext`（extension.ts:202-207）走 `!st.sessionId`
分支 → 报 "not connected"。此错 100% 复现，与后端状态无关。

**owner 新需求（本票顺带落地的最小版）**：像 Claude Code 一样，VS Code 侧边栏有 bobo
面板；编辑器里选中一段代码时，面板能实时显示当前选中的代码（文件 + 行区间 + 内容预览）。

---

## 施工项

改动面**只允许 `apps/vscode-extension/` 目录内**。仓库其余零 diff。

1. **package.json 注册侧边栏**（修 Bug 1）
   - `contributes.viewsContainers.activitybar`：注册 bobo 容器（id `bobo`，标题 `bobo`，
     一个 SVG 图标，放 `media/` 下，简洁单线条风格，禁止 emoji）。
   - `contributes.views.bobo`：注册视图 `{ "id": "boboChat", "name": "Chat" }`。
   - 同步修订 `activationEvents`：加 `onView:boboChat`。

2. **sessionId 与面板解耦**（修 Bug 2）
   - extension.ts onConnect 回调：`st.sessionId = sid` 无条件执行；
     `if (st.panel) st.panel.setSession(sid)` 单独分支。
   - `resolveWebviewView` 里已有 `if (state.sessionId) panel.setSession(...)`（:42），
     保持——面板后开也能补 session，时序双向闭环。
   - `askWithContext` 的报错分支（:204-206）拆两种提示：socket 未连上 → 原提示；
     已连接但 sessionId 未就绪 → 提示 "bobo: connecting, try again in a moment."
     并自动重试一次 `session.create`（不许报假 "not connected"）。

3. **选中代码实时显示**（owner 新需求最小版）
   - extension.ts 注册 `vscode.window.onDidChangeTextEditorSelection` 监听：
     取当前编辑器选区（非空时），调 ChatPanel 的方法把 `{filePath, startLine,
     endLine, text}`（text 截断到前 500 字符）发进 webview。
   - ChatPanel webview 顶部加一个"当前选中"卡片：文件名 + 行区间 + 等宽字体代码预览；
     无选区时卡片隐藏或显示 "No selection"。样式跟随现有面板风格，CSS 从简。
   - 该选区与 Ask bobo 发送的 SelectionContext 同源复用，不另造数据结构。

4. **断线韧性小补**（防本次"粘死连接"复现）
   - SocketClient 重连成功（onConnect 再次触发）时，extension.ts 必须重新
     `session.create` 并把新 sid 推给 panel（现有回调已在此路径上，确认即可）；
   - `bobo.socketPath` 设置项不变。

---

## 禁止项

- 不动仓库内 `apps/vscode-extension/` 以外的任何文件一行（gateway/core/desktop/测试守卫零 diff）。
- 不实现 diff 协作、Apply 按钮、多轮对话历史持久化——那是 VSC-2 的范围，不许顺手做。
- 不改 SocketClient 的协议帧格式；不改 pairing 确认逻辑。
- 图标禁止 emoji，用 SVG。
- 不发布到 marketplace；本地安装链路（拷贝到 ~/.vscode/extensions/）行为保持不变。

---

## 验收标准（终审逐条复跑）

1. **单测**：`cd apps/vscode-extension && npm test` 全绿（基线 30/30，新增用例另计）；
   新增用例至少覆盖：onConnect 无 panel 时 sessionId 仍被保存；panel 后开时补 setSession；
   选区监听只发非空选区、text 截断 500。
2. **package.json 静态断言**：单测断言 contributes 含 viewsContainers.activitybar 的 bobo
   容器 + views.bobo 的 boboChat 视图 + activationEvents 含 onView:boboChat。
3. **全量回归**：`.venv/bin/python -m pytest tests/ -q -p no:cacheprovider`，
   零失败（基线 2722 passed / 2 skipped / 1 xpassed；只认这个口径）。
4. **实弹（Kimi 终审执行，施工方须提供可复跑脚本）**：
   a. 扩展重新部署到 ~/.vscode/extensions/ 后重载 VS Code，Activity Bar 出现 bobo 图标；
   b. 打开面板，桌面端 bobo 在线时，VS Code 里选中代码 → 面板"当前选中"卡片实时更新；
   c. 右键 Ask bobo（或 Cmd+Shift+B）→ 面板流式收到回答（不再出现 "not connected"）；
   d. kill 后端 → 重启桌面端 → 不重启 VS Code，Ask bobo 自动恢复（断线重连重发现）。
5. 收工汇报落盘 `library/agent开发/TICKET-VSC-1B完成报告.md`，含 md5、git 实况、
   测试原话、实弹脚本路径。

---

## 风险自查点

- package.json 的 viewsContainers/views JSON 结构别写错层级（views 的 key 是容器 id `bobo`）。
- webview 里取选区数据要走 `webview.postMessage` + panel 侧 `onDidReceiveMessage`
  反向已有先例，照 chatPanel.ts 既有消息通道加类型即可，不新开通道。
- 选区监听要防刷屏：300ms 内多次 selection 事件只发最后一次（防抖）。
- 修 Bug 2 时别把 `.catch(() => {})` 的静默吞错扩大——session.create 失败要留 log。
- 改完 out/ 必须重新 `npm run compile`（或等效 build），安装目录的 out/ 同步更新，
  别让源码和产物不一致（VSC-1 的 .gitignore 教训）。
