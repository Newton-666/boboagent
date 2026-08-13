# Hermes 桌面端源码研读（2026-08-13，Kimi）

源码：data/skill-standards/hermes-agent-main/apps/desktop（React + TS + assistant-ui + nanostores，388 文件）

## 核心发现

1. **设计宪法 DESIGN.md（167 行）**：一个关注点一个原语、token 不用字面量、扁平不套盒；上线前 7 项 checklist。我们没有宪法 → "爪子感"根源。
2. **工具行统一单元**（tool-fallback.tsx 466 行）：状态图标 + 友好名 + 实时耗时 + 复制按钮；详情 stdout/stderr 分块、错误摘要/正文分离、diff 走 DiffLines。
   - 重要：它**明确反对聚合**（"we never group"），理由是回合收尾会重排消息流。我们已拍板"编辑流摊开/读取流聚合"哲学，不学它的永不聚合，互鉴即可。
3. **双视图模式**：product / technical 一键切换（store/tool-view.ts），治"JSON 倾倒 vs 细节不可见"两头难题。
4. **思考手风琴**（thread.tsx）：连续思考成组折叠、空思考组整组丢弃、流式实时预览——与我们 F6/F6B 方向互验。
5. **todo 提升面板**（todo-tool.tsx）：当前任务标题 + 完成项 45% 透明度淡化 + 进行中旋转图标。

## A 类（追平）裁决记录

照做：状态覆盖层、会话管理、控件体系、Toast、三态反馈
打折：markdown（只做简版）、主题（只 token 化，缓做浅色）、乐观更新（对齐 Interrupt 语义）
不做：Flat 视觉全面改造（owner 拍板保持现状样式）、打包等宽字体

## B 类（差异化，Hermes 没有）

工具活动流时间线 / Worker 活动视图 / 上下文仪表盘(_marking_stats) / 记忆面板(signal score) / 中文优先排版 / 审计隐私视图

→ 立项：DESK-V2A（体验地基）→ DESK-V2B（差异化面板）→ DESK-V2C（锦上添花），票在 data/tickets/。
