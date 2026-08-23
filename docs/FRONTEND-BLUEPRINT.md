# 前端蓝图（Frontend Blueprint）

> **本文件是桌面端成品的宏观蓝图（宪法 Principle 6：蓝图先行）。**
> 任何 agent 在做前端相关改动前，必须先读本文件；改成品前先与 owner 对齐蓝图。
> 成品 = `apps/desktop/dist/index.html`（手写维护的生产界面，Electron 直接加载）。
> 说明：`apps/desktop/src/` 是**废弃存档**（git 记录 2026-06-19 df8fa055 删除、08-12 7f0a6b40 注明"仅留参考"）——不是蓝图，不可作为修改依据。
> 刷新纪律：蓝图过期 = 作废；每次前端票合入必须同步更新本文件（同 CHANGE-LOG 微观/宏观交替）。

---

## 1. 产品现状（功能清单）

| 区域 | 组件 |
|---|---|
| 侧栏 | 折叠按钮；New session / Memory / Skills / Session 导航；会话搜索；会话列表（pin/改名/删除/投影小组件、活跃圆点、loading）；Plugin 折叠区（Notes/Project/Terminal/Telescope）；status-mode 徽标、widget 开关、settings 入口 |
| 主区 | 欢迎页；Memory 面板（六类记忆分组+diff+删除/改类型）；Skills 面板（preset/custom 开关）；聊天区（气泡/thinking 折叠/工具卡/工具聚合卡/独立 diff/工作区实况卡/待人工清单卡/profile 卡/skill.activate 卡）；上下文仪表盘；输入区（斜杠面板/选图/项目 pill/Roles-Rules 面板/AUTO 开关/COMPUTER 开关/stop/发送） |
| 右侧面板 | Notes/Project/Terminal/Telescope + 拖拽 resize |
| 模态 | 设置弹窗（Basic/API/Advanced/Profile 四 tab）；首次配置屏；审批模态；删除确认；连接覆盖层（connecting/failed/disconnected）；Toast；HTML 预览；Telescope diff 模态 |
| 渲染管线 | 本地 vendor：marked + DOMPurify + highlight.js + KaTeX（mdReply 全管线 / md 简管线 / 数学公式提取还原） |
| 本地持久化 | 会话草稿 boboDraft_\<sid\>（图+文）、最近项目、考古模式、历史姿势/高度 |
| 小组件 | widgetUserMsg/CtxStats/Sessions/CurrentSession/PinSession 只读广播 |

## 2. 接口契约（最高价值——改前端必查）

### 2.1 RPC 面（29 个，成品↔后端 100% 自洽）
session.create/list/resume/activate/rename/delete/pin/interrupt/set_request · prompt.submit（参数：session_id/text/**image**/**project_root**）· approval.respond · slash.exec · commands.catalog · tools.list · config.full/set · model.options · memory.list/delete/update · skills.list/toggle · context.stats · profile.get/save/rollback · metrics.read · project.set_root · file.read · setup.status/submit

### 2.2 事件面（20 类订阅）
gateway.ready · backend.exited · gateway.error · message.start/delta/complete · reasoning.delta · tool.start/complete · status.update · approval.request · memory.changed · profile.update · skill.activate · session.auto_state / office_state / computer_use_state · notes.tree · project.tree · terminal.output
> 注意：成品**不监听** thinking.delta（蓝图存档里有，勿照抄）。

### 2.3 关键内部函数
sendPrompt(text, image) → prompt.submit；handleSlash/execSlash（本地/后端斜杠分派）；messaging + renderBusyUI（**按会话隔离的忙碌闸，勿删**）；setSidBusy/currentBusy；imgPick/attachImg/saveDraft（选图上传）；addMsg/addTool/addStatus（渲染）；loadSessions/loadSession（含窗口化历史、request 回显、开关同步）；md/mdReply/extractMath；stopThinking；widgetToggle/widgetPinSession；showOverlay/retryConnect（连接状态机）。

### 2.4 localStorage 键
boboDraft_\<sid\>、boboRecentProjects、bobo_hist_arch_mode、bobo_hist_pose_\<sid\>、bobo_hist_h_\<sid\>

## 3. 维护纪律（动成品三步）

1. **改前看蓝图**：读本文件 + 相关区域代码 → 与 owner 对齐改动；
2. **改后同步蓝图**：本文件必须反映改动（新增功能/接口变更逐项登记）；
3. **守卫全绿**：tests/ 中前端守卫（busy_gate/css 冻结/slash 路由/布局）必须通过。
禁止：跳过蓝图直接改成品；改成品不同步蓝图；把成品回退到任何旧版本（成品是事实源）。

## 4. 版本记录（每次前端票更新）

| 日期 | 变更 | 蓝图同步 |
|---|---|---|
| 2026-08-23 | 蓝图初建（调查自 dist 现状，含 24 模块缺失史：src 存档非蓝图） | v1 |
