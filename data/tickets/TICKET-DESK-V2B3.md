# TICKET-DESK-V2B3：桌面端斜杠命令路由 + 命令面板

- 状态：待施工（F9 之后）
- 开票：Kimi 2026-08-14（owner 实弹：桌面端打 /clear-handoff 被当普通消息发给 LLM；要求 / 触发命令面板）
- 分支：feat/ticket-desk-v2b3（自最新 main 切出）
- 授权路径：apps/desktop/dist/index.html + bobo_tui_gateway/handlers/prompts.py（如需补命令清单端点）+ tests/
- **施工前必读 docs/GUI-LESSONS.md**
- owner 工作前提：所有交流与施工默认在桌面端进行（切 TUI 会另行告知）

## 病灶
桌面端仅 AUTO 开关走了 slash.exec；输入框打 "/..." 一律 prompt.submit 发给 LLM。TUI 有完整 slash 命令体系（/help /clear /clear-handoff /undo /tools /auto /office /scan 等），桌面端完全没有。

## 修复要求
1. **斜杠路由**：发送时检测输入以 "/" 开头 → 走 slash.exec（携带 session_id），结果显示为系统消息；不再进 LLM
2. **命令面板**：输入框首字符为 "/" 时，上方弹出命令面板：
   - 列出全部可用命令 + 一句话说明（数据源：后端 commands.catalog 端点已有，见 handle_commands_catalog；不够就补字段，只加不改）
   - 输入继续过滤（如 "/cl" 只剩 /clear /clear-handoff）；↑↓ 选择、Enter/Tab 补全、Esc 关闭、点击可选
   - 面板位置：输入框正上方，左对齐输入框左缘，宽不超过输入框宽，最大高 260px 可滚
   - 视觉：--bg2 底、--border 发丝线、圆角 8px、选中行 --bg3，全部取色板
3. 铁律照旧：既有 CSS 零改动、TUI 零变化、DOM 在 script 前、不破坏 V2A/V2B/V2B2 任何行为
4. IME 组合输入期间不触发面板（中文输入法 composition 保护，教训册 F1 案例）

## 验收
1. 实弹：桌面端打 "/clear-handoff" → 走后端执行返回"待人工清单已清零"，不再发给 LLM
2. 实弹：打 "/" 弹面板、打 "/cl" 过滤、Esc 关面板、Enter 补全
3. 专项 + 全量零回归；md5 闸门；DOM 顺序闸过

## 纪律
不 commit/merge/push 等终审；五查；数字可复现；撞轮次报断点
