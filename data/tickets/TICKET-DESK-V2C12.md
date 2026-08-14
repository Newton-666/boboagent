# TICKET-DESK-V2C12 —— 完整 Markdown 渲染 + Charter 衬线正文（样式票，独立回溯）

> 施工前必读 docs/GUI-LESSONS.md + docs/GUI-DESIGN.md（规则 6 样式票纪律）。分支 feat/ticket-desk-v2c12（自最新 main 切出）。未终审不 commit。
> owner 要求：Markdown 渲染 99% 成功率（粗体/斜体/下划线/删除线/标题/列表/引用/代码块高亮/**表格**/链接全渲染）。

## C1 完整 Markdown 渲染

- **库选型：vendor 本地引入 marked + DOMPurify**（下载到 apps/desktop/vendor/，本地文件 script 引入，不走 CDN——桌面端离线可用；保留 LICENSE 文件）
- **渲染范围：仅助手正文气泡**（.msg-text 类）。工具卡/思考框/diff 块/实况折叠卡/状态行**一律不走 markdown**（它们是结构化组件，渲染管线不动）
- 流式：message.delta 期间用 marked 增量渲染（每 chunk 重渲染当前气泡 html），message.complete 后定稿；表格/代码块在流式中途半截语法不炸（marked 容错即可，DOMPurify 始终过一遍）
- 代码块：高亮用 highlight.js（vendor 本地，只注册常用语言：python/js/ts/bash/json/yaml/markdown/sql），等宽字体保持 SF Mono 不变
- 历史消息重放（resume）与新消息走同一渲染路径
- **CSS 全部新增**集中在 `/* === V2C1 markdown === */ ... /* === end V2C1 === */` 锚点段：md 表格（细发丝线边框、斑马纹用 --bg2）、代码块底（--bg3）、引用左边条（橙）、标题阶梯、列表缩进。取色只用色板 token
- 既有"粗体橙色"渲染逻辑若与新管线冲突，由 markdown 管线统一接管（strong 颜色仍取色板橙）

## C2 Charter 衬线正文

- 字体：Bitstream Charter（X11 自由许可，可捆包）——下载 Regular/Italic/Bold/BoldItalic 四件 woff2 到 apps/desktop/fonts/，附 LICENSE；@font-face 声明集中放锚点段
- **应用范围只有一处**：助手正文气泡的 font-family 变量（新增 `--font-reply: 'Charter', 'Songti SC', 'Noto Serif CJK SC', serif`——西文落 Charter，中文落宋体系，等宽场景不受影响）
- UI 控件/侧栏/输入框/代码/数据全部保持现有无衬线/等宽——只动回复正文一处
- 字体加载失败静默回退系统 serif，不阻塞渲染

## 验收

- 专项 tests/test_ticket_desk_v2c12.py（node 实跑）：①10 个 markdown 用例（粗斜下划线/删除线/三级标题/有序无序列表/引用/行内代码/代码块/表格/链接）渲染断言 ②流式半截表格不炸 ③工具卡/思考框内容不被 markdown 触碰 ④DOMPurify 注入测试（<script> 被剥）⑤@font-face 与 --font-reply 变量断言 ⑥CSS 锚点段存在且段外零新增
- F2-F10/V2 系 GUI 测试全不破；全量零回归；md5 闸门
- 实弹截图自验：一段含表格+代码块+列表的回复渲染效果
- 收工汇报按 L12
