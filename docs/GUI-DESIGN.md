# BOBO 桌面端设计文档（GUI-DESIGN）

> v1.0 · 2026-08-13 建立 · 维护纪律见文末「编年史规则」
> 适用文件：`apps/desktop/dist/index.html`（单文件 GUI，约 2000 行）
> 对应外部参照：docs/analysis/hermes-desktop.md（Hermes 源码研读）
> 施工必读：docs/GUI-LESSONS.md（教训册，GUI 票动工前 bobo 必读）

---

## 一、设计哲学（owner 拍板，不可单方面推翻）

1. **视觉保持现状**——DESK-V2 全系列只加新态新组件，不改既有颜色/圆角/间距/字体（ROADMAP 铁律）
2. **显示哲学**：
   - 编辑流摊开：思考→编辑卡+diff 永不入聚合卡，一步一 visible
   - 连续读取吞并：读类工具链进聚合卡（档案柜，可展开考古）
   - 连续思考合并：相邻思考合为一框；被状态行隔开仍算相邻（F6D）
   - diff 同级：与回复同级的独立区块，整行红绿底色（TUI 同款语义），不是文字变色
3. **TUI 零干扰**：桌面端一切改动不得改变 TUI 显示语义；共享层只加字段
4. **学 Hermes 方法，不学体系**：product/technical 双模式、设计宪法思路可借鉴；技术栈不迁移

## 二、设计 Token（CSS 变量，:root 唯一定义点）

| Token | 值 | 用途 |
|---|---|---|
| `--bg` | #faf9f2 | 主背景（米白，**浅色暖系主题**） |
| `--bg2` | #f2f1e8 | 次背景（侧栏/卡片/工具聚合卡） |
| `--bg3` | #eae8dc | 三级背景（输入框/选中态/hover 加深） |
| `--text` | #2d2d2d | 主文字 |
| `--text2` | #777 | 次文字（工具卡/描述） |
| `--text-muted` | #999 | 弱文字（占位/箭头/时间） |
| `--border` | #e0ded4 | 发丝线（唯一分隔手段） |
| `--hover` | #e8e6da | hover 填充 |
| `--green` | #4caf50 | 连接状态绿点 |

**非变量语义色（现状，散在规则中——V2C 候选 token 化）**：

| 色 | 值 | 语义 |
|---|---|---|
| 品牌橙 | #e8913a | 强调：focus ring、ASCII logo、active tab 下划线、AUTO 开启态、粗体 |
| 思考蓝 | #5b9bd5 | think-box 边框/标签/呼吸点（rgba 0.04~0.12 透明度底） |
| 成功绿 | #50a14f | 工具完成点、diff-add 文字（tool 卡内） |
| 错误红 | #f48771 | 错误/diff-del/stop 按钮（rgba 0.12~0.22 透明度底） |
| diff 整行底色 | 加 `rgba(80,161,79,.20)` 底 #2c5e2b 字 / 删 `rgba(244,135,113,.20)` 底 #8a3a2c 字 | F3-5 diff-block，**owner 点名保护对象** |
| 危险红 | #f44336 | 删除按钮/断连点 |

**字体**：正文 -apple-system/PingFang SC，15px/1.6；等宽 SF Mono/Monaco/Menlo（logo、diff、tool-result）
**圆角阶梯**：4（小元素）→ 6（工具卡）→ 8（卡片/diff块/思考框）→ 12（消息气泡/输入框）
**动效**：fadeIn 0.25s（消息入场）、dotPulse 3s（运行中）、thinkPulse 1.4s（思考点）、sessionLoading 1.2s（会话加载呼吸）、侧栏滑动 0.2s

## 三、布局骨架

```
┌──────────┬─────────────────────────┬────────────┐
│ sidebar  │ main (max 800px 居中)    │ right-panel│
│ 240px    │  welcome / chat / input  │ 340px 可拖 │
│ 会话+插件 │  auto-toggle/stop/send   │ 多 tab     │
└──────────┴─────────────────────────┴────────────┘
```

- 侧栏可收起（margin-left 负值滑出）；右栏默认隐藏，tab 含关闭
- 输入区浮动三控件（F4-4 防撞车坐标）：send `right:24 bottom:32`、stop `right:64 bottom:36`、AUTO `right:104 bottom:37`

## 四、功能清单（截至 main 67e8cc2，与票据一一对应）

| 功能 | 来源票 | 行为要点 |
|---|---|---|
| 消息流 | 基础 | 用户气泡右置；bobo 纯文本（markdown 简渲染：粗体橙） |
| 思考框 think-box | F1/F6/F6B/F6D | 流式蓝框；tool.start 收束；连续合并；状态行不阻断相邻判定；默认折叠态可展开 |
| 工具卡 .tool | 基础/F4 | 友好名（TOOL_FRIENDLY 模块级映射）+ 状态点 + 路径/命令摘要；零 JSON 倾倒；2000 字符预览拦截 |
| 聚合卡 .tool-agg | F2/F4/F6C/F6D | 第 2 步起建卡吞并读类步骤；写类工具（WRITE_TOOLS 20 项名单）与其思考永不入卡；纯编辑流不建空卡 |
| diff 块 .diff-block | F3-5/F8 | 同级独立区块、整行底色、默认展开；**历史会话切回同样恢复（F8）** |
| 会话管理 | F3/F7/F8 | 加载呼吸态；resume 显示摘要分隔行+空占位；手动命名优先于自动命名；历史恢复 diff+思考（新会话起） |
| AUTO 开关 | F2/F4/AUTO-G1/G2 | 携带 session_id 翻转；AUTO=白名单放行/黑名单即拒，TUI=GUI 语义一致 |
| 中断 | INT-1 | stop 按钮/Esc 一刀切（工具/测试/终端/思考皆可断） |
| 连接状态 | 基础 | 侧栏底绿/红点 |
| 右侧面板 | 基础 | 笔记树/预览/终端 tab |

## 五、已知差距（对照 Hermes，排队中）

见 ROADMAP 第一梯队：DESK-V2A（状态覆盖层/会话搜索/pin/Toast/三态组件，票已开）→ V2B（差异化面板）→ V2C（markdown 简版/记忆面板/中文排版/token 化）

> ⚠️ 勘误（2026-08-14 Kimi）：本文件早期对比笔记中"bobo 深色写死"为错误记录——实际为米白浅底（--bg:#faf9f2），Anthropic cream 路线。涉及主题的判断以此为准。

## 六、编年史规则（维护纪律，Kimi 执行）

1. **每次 GUI 相关票终审合并后**，Kimi 在本文件追加编年史条目：票号 / 新增了什么（class、组件、token、行为）/ 改动文件 / 合并 commit / 回滚标签
2. 新增 token 或语义色 → 同步更新第二节表格
3. 新功能 → 更新第四节功能清单
4. **本文件随 docs/ 走 git，每次更新单独 commit 并推送**——出问题时 `git log docs/GUI-DESIGN.md` 即完整回溯链
5. bobo 施工不得修改本文件；只有 Kimi 终审后落笔
6. **样式票独立回溯**（owner 2026-08-14 立）：凡涉及字体/Markdown/配色等纯样式改动，必须 ① 独立分支独立 rollback 标签，不与逻辑改动混票；② 新增 CSS 集中放在带明显注释锚点的连续区段（如 `/* === V2C1 markdown === */ ... /* === end V2C1 === */`），保证整段可外科式摘除；③ 编年史记录样式锚点位置

## 七、变更编年史

| 日期 | 票 | 新增 | commit | 回滚标签 |
|---|---|---|---|---|
| 2026-08-13 | 文档建立 | 本文件；此时点全量快照见第一~四节 | （见 git log） | — |
| 2026-08-13 | DESK-V2A | 状态覆盖层 #overlay-root（连接中/失败/断连，z-5000 全屏，0.1s 淡入）；会话搜索 #session-search（new-chat 正下方）；pin 置顶（.pin-mark 标题左侧 + .pin-btn 行内 + 稳定排序 + session.pin API + pinned 字段落盘）；行内重命名（替代 confirm）；删除改模态二次确认；Toast #toast-root（右上 14px，success/fail 左边条，3s 自动消失）；三态组件 .v2a-loader/.ovl-*；focus-visible 1px 橙环 + #send hover；既有 CSS 零改动（测试闸门锁死，合并后基线切换 rollback 标签） | 6d11d0b + 修正 + 68373a3（DOM 顺序修复：新组件必须在 script 之前，否则顶层 JS 空指针全崩；已补回归闸 test_v2a_dom_before_script） | rollback/pre-desk-v2a |
| 2026-08-14 | DESK-V2B2 | 上下文细条改进度药丸：圆角 999px 药丸内嵌进度条+百分比+已用/上限；三色阶 <60% 蓝 / ≥60% 橙 / ≥85% 红；context.stats 加 context_limit；点击展开明细/Esc 收起保留 | aacdeb3 | rollback/pre-desk-v2b2 |
| 2026-08-14 | DESK-V2B3 | 斜杠路由（"/" 输入走 slash.exec 带 session_id，不进 LLM）；命令面板 #slash-panel（输入框正上方左对齐，max-height 260px，过滤/↑↓/Enter 补全/Esc；.sp-item/.sp-active/.sp-name/.sp-desc/.sp-empty，全取色板 token）；handle_commands_catalog 新增 descs 一句话说明字段（只加不改）；IME composition 保护沿用 F1-1 三判定 | 59d23a0 | rollback/pre-desk-v2b3 |
| 2026-08-14 | DESK-V2B4 | 实况折叠卡（收工对账区块默认折叠，CSS 锚点段 /* === V2B4 实况折叠卡 === */）；药丸数据源切活引擎 get_live_history 双兜底 + tool.complete 轻量刷新；kimi-k3 model_context 补登 1M | 71de7ec | rollback/pre-desk-v2b4 |
| 2026-08-14 | GUI-F10 | 事件流 sid 过滤闸门（emit 的 params.session_id 注入回调数据，非当前会话不渲染）；后台活动中圆点（弱色 --text-muted，切回即清）；审批弹窗应答回来源会话 _approvalSid（防切窗错配） | a916d41 | rollback/pre-gui-f10 |
| 2026-08-14 | DESK-V2C12 | 完整 Markdown 渲染管线（marked+DOMPurify+highlight.js vendor 于 dist/vendor/，含三件 LICENSE；作用域仅 .msg.bobo .txt；流式增量渲染；hljs 主题取色板+语义橙绿）；Charter 衬线（dist/fonts/ 四件 woff2 + LICENSE，--font-reply 仅助手正文，中文落 Songti/Noto Serif）；全部 CSS 在 /* === V2C1 markdown === */ 锚点段 | 420bf8a | rollback/pre-desk-v2c12 |
| 2026-08-13 | DESK-V2B | 工具卡耗时时间线（updateToolResult 对称填充，含聚合卡考古）；上下文仪表盘 #ctx-stats-bar（#input-box 正上方 22px 细条，点击展开明细/Esc 优先收起不打断中断语义；context.stats 只读端点，无轮询） | 31e09cb | rollback/pre-desk-v2b |
| 2026-08-13 | V2A 打磨（owner 实弹反馈三条） | 确认弹窗 Enter=确认/Esc=取消+自动聚焦（对齐原生 confirm 手感）；行内三键统一 .act 体系（16px 同尺寸、紧凑右置、顺序 pin→改名→删除、默认弱色 hover 显形、删除仅 hover 变红）；emoji 图钉改细线 SVG（PIN_SVG 弱色，激活细橙）；CSS 闸门加特批豁免段（.del/.re→.act 重构） | 9a690dd | rollback/pre-v2a-polish |
