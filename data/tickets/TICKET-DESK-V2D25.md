# TICKET-DESK-V2D25 —— 工具卡精致化（SVG 细线图标 + 流光运行态）

> 施工前必读 docs/GUI-LESSONS.md + docs/GUI-DESIGN.md 规则 6（样式票：锚点段 + 独立回溯）。分支 feat/ticket-desk-v2d25（自最新 main 切出）。未 commit 等终审。
> owner 定调：图标用 SVG 细线（非 emoji）；运行态要"华光划过去"的流光效果，克制不闪。

## 范围：只改工具卡一个组件（.tool 及其子元素），其余一概不动

### D2.5-1 细线 SVG 图标体系

- 名字前加 14px 内联 SVG 图标，1.25px 描边、currentColor 取色板，风格统一克制
- 映射表（icons 集中一个 JS 对象，后续可扩）：execute_terminal→›_ 终端框 / read_local_file→文档 / edit_file→✎ 笔 / grep_code→⌕ 搜索 / save_memory·load_result→◈ 记忆 / task_ledger→☰ 清单（细线版）/ run_tests→✓ 验证 / web_search→◎ / 默认→小方块
- 未知工具回退默认图标，不许空白

### D2.5-2 状态语义（替代裸文本）

- **删掉 "running" 裸文本**，状态全部由视觉表达：
  - 运行中：状态点=橙色细圈缓慢脉冲（1.6s ease-in-out 呼吸）
  - 完成：灰绿实心小点，耗时列淡入
  - 失败：红点定住（不脉冲）
- 工具名字重 600；上下文（文件名/命令前 40 字符）收进等宽弱色 chip（--bg3 底、圆角 4px、SF Mono 10px）

### D2.5-3 流光（运行中专属）

- 运行中的工具卡叠加一道斜向柔光：linear-gradient 半透明白/暖光（浅色底上 25-35% 透明度），`background-size` 放大 + keyframes 从左到右 2s 一轮 infinite
- 完成/失败瞬间移除流光 class（光停）
- `prefers-reduced-motion` 媒体查询下流光与脉冲全部禁用（无障碍纪律）
- 聚合卡内的考古工具条、历史重放（F12 聚合卡）**不带流光**（历史是静的）

### 纪律

- 新 CSS 全部进 /* === V2D25 工具卡 === */ 锚点段；既有 .tool 样式只加不改（覆盖走锚点段优先级）
- 流光用 CSS animation，禁止 JS 定时器

## 验收

- 专项 node 实跑：①图标映射存在且未知工具回退 ②running 文本不存在于 DOM ③运行中加 shimmer class、完成移除 ④reduced-motion 下 class 不加 ⑤F6C/F6D/F8/F12 聚合与历史渲染断言不破
- 全量零回归 + md5 闸门 + L12 汇报 + 实弹截图（运行中一张、完成一张）
