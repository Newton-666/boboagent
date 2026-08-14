# TICKET-TOOL-PARK-1 —— 工具外挂仓：51 个零调用工具打包出链（owner 2026-08-14 设计）

> 施工前必读 docs/GUI-LESSONS.md。分支 feat/ticket-tool-park-1（自最新 main 切出）。未终审不 commit。
> 数据依据：reports/tool_profile_report.md（events.jsonl 4.1 万行真实日志挖矿）。

## owner 设计原话（本票最高指导）

死工具**不删除**，打包成外挂仓：① 不经过 Agent 系统流程（不进 prompt schema）；② 外挂仓是可随时调整的外部资源库，以后还能往里加；③ 后续（本票不做）加指令让用户手动管理仓内仓外。

## 本票范围（只做第一步：打包外挂）

### PARK-1 外挂仓机制

- 新增 `data/tool_park.json`（仓单）：`{"parked": ["api_register", ...51 个名单见下]}`
- `tools/__init__.py` 装配 TOOLS_SCHEMA 时读仓单：**仓内工具的 schema 不进 TOOLS_SCHEMA**（prompt 不再带它们的定义，每轮省 ≈4,279 tokens）
- **可执行性保留**：工具函数照常注册，引擎收到对仓内工具的调用（老会话记忆/手动指定）仍正常执行——外挂只是不 advertised，不是禁用
- `describe_tool` 必须能查到仓内工具的完整 schema（它本来就是按需取描述的入口，仓内工具是它的主要服务对象）
- 仓单缺失/损坏时兜底：全部工具照常上线（宁多勿缺，不许启动失败）

### PARK-2 名单（51 个，画像实证零调用）

api_register, code_to_obsidian, review_to_obsidian, cross_project_search, github_pr_comment, set_reminder, discuss_with_pi, browser_open, notion_create_page, index_project, restore_checkpoint, github_create_repo, move_note, notion_append, copy_to_notion, delete_folder, copy_to_obsidian, batch_copy_notes, github_create_pr, move_to_folder, rename_note, batch_move_notes, github_pr_diff, save_skill, github_setup, notion_setup, browser_get_title, batch_delete_notes, notion_search, read_email_content, read_recent, delete_note, create_folder, notion_read_page, classify_analyze, web_extract, send_notification, web_fetch_markdown, list_calendar_events, analyze_emails, read_email_recent, search_emails, classify_confirm, create_calendar_event, write_clipboard, open_url, read_clipboard, render, github_check_auth, wiki_rebuild, list_reminders

（极低频 8 个本票不动：bobo_schedule, office_manager, github_*, 等——只动零调用的，保守第一刀）

### 明确不做（后续票）

- /tools 管理指令（查看仓/移入移出）——TOOL-PARK-2
- 工具合并（obsidian 系 13 个并一个）——沙盒验证后另开票

## 验收

- 专项 tests/test_ticket_tool_park_1.py：①TOOLS_SCHEMA 不含 51 个仓内工具 ②仓内工具仍可被引擎执行 ③describe_tool 对仓内工具返回完整 schema ④仓单缺失时 82 个全上线兜底 ⑤schema 总税从 ≈8,276 降到 ≈3,997 tokens（±5%）
- 全量零回归 + md5 闸门；收工汇报按 L12
