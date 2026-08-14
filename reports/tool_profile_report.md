# bobo 工具画像报告（COST-1a 第一步 · 如实画像零优化）

> 数据源：data/logs/events.jsonl 41k 行真实事件 + tools/TOOLS_SCHEMA 注册表 · 2026-08-14

## 全局体检

| 指标 | 真实值 |
|---|---|
| 注册工具总数 | **82 个** |
| 每轮 prompt 工具 schema 税 | **≈8,276 tokens**（每轮必带，调不调都交） |
| LLM 调用总次数 | 7,618 |
| prompt_tokens 总消耗 | **386,691,851**（平均每轮 50,760） |
| 空回复（ct=0） | **881 次 = 11.6%** |
| 工具调用总数 | 7,274 |
| 严格重复调用 | 323 次 = 4.4% |

## 成本×价值矩阵（schema 税 vs 真实调用）

| 工具 | schema税 | 调用 | 重复 | 平均ms | 判定 |
|---|---|---|---|---|---|
| spawn_worker | 322 | 3 | 0 | 0 | 🟠 极低频（<5） |
| refactor | 279 | 10 | 1 | 0 | 🟡 高重复率 |
| task_ledger | 250 | 354 | 0 | 0 | 🟢 健康 |
| office_manager | 222 | 12 | 0 | 0 | 🟢 健康 |
| file_operation | 210 | 119 | 1 | 0 | 🟢 健康 |
| api_register | 186 | 0 | 0 | 0 | 🔴 零调用白交税 |
| load_result | 185 | 809 | 0 | 0 | 🟢 健康 |
| code_to_obsidian | 168 | 0 | 0 | 0 | 🔴 零调用白交税 |
| review_to_obsidian | 151 | 0 | 0 | 0 | 🔴 零调用白交税 |
| grep_code | 150 | 247 | 36 | 0 | 🟡 高重复率 |
| cross_project_search | 144 | 0 | 0 | 0 | 🔴 零调用白交税 |
| bobo_schedule | 144 | 3 | 0 | 0 | 🟠 极低频（<5） |
| save_memory | 132 | 5 | 0 | 0 | 🟢 健康 |
| read_local_file | 131 | 938 | 112 | 0 | 🟡 高重复率 |
| edit_file | 124 | 681 | 18 | 0 | 🟢 健康 |
| bobo_config | 123 | 2 | 0 | 0 | 🟠 极低频（<5） |
| github_pr_comment | 121 | 0 | 0 | 0 | 🔴 零调用白交税 |
| set_reminder | 121 | 0 | 0 | 0 | 🔴 零调用白交税 |
| api_call | 120 | 1 | 0 | 0 | 🟠 极低频（<5） |
| discuss_with_pi | 117 | 0 | 0 | 0 | 🔴 零调用白交税 |
| code_execution | 111 | 241 | 43 | 0 | 🟡 高重复率 |
| execute_terminal | 111 | 3512 | 111 | 0 | 🟢 健康 |
| read_obsidian | 111 | 39 | 0 | 0 | 🟢 健康 |
| browser_open | 109 | 0 | 0 | 0 | 🔴 零调用白交税 |
| notion_create_page | 105 | 0 | 0 | 0 | 🔴 零调用白交税 |
| write_obsidian | 103 | 8 | 0 | 0 | 🟢 健康 |
| index_project | 103 | 0 | 0 | 0 | 🔴 零调用白交税 |
| run_tests | 101 | 19 | 0 | 0 | 🟢 健康 |
| append_obsidian | 99 | 3 | 0 | 0 | 🟠 极低频（<5） |
| get_current_time | 99 | 8 | 0 | 0 | 🟢 健康 |
| list_directory | 99 | 86 | 0 | 0 | 🟢 健康 |
| review_diff | 96 | 40 | 0 | 0 | 🟢 健康 |
| restore_checkpoint | 94 | 0 | 0 | 0 | 🔴 零调用白交税 |
| github_create_repo | 94 | 0 | 0 | 0 | 🔴 零调用白交税 |
| describe_tool | 93 | 20 | 1 | 0 | 🟢 健康 |
| move_note | 93 | 0 | 0 | 0 | 🔴 零调用白交税 |
| notion_append | 92 | 0 | 0 | 0 | 🔴 零调用白交税 |
| copy_to_notion | 92 | 0 | 0 | 0 | 🔴 零调用白交税 |
| delete_folder | 91 | 0 | 0 | 0 | 🔴 零调用白交税 |
| web_search | 91 | 1 | 0 | 0 | 🟠 极低频（<5） |
| copy_to_obsidian | 91 | 0 | 0 | 0 | 🔴 零调用白交税 |
| batch_copy_notes | 90 | 0 | 0 | 0 | 🔴 零调用白交税 |
| github_create_pr | 89 | 0 | 0 | 0 | 🔴 零调用白交税 |
| move_to_folder | 88 | 0 | 0 | 0 | 🔴 零调用白交税 |
| rename_note | 88 | 0 | 0 | 0 | 🔴 零调用白交税 |
| batch_move_notes | 86 | 0 | 0 | 0 | 🔴 零调用白交税 |
| search_obsidian | 85 | 30 | 0 | 0 | 🟢 健康 |
| github_pr_diff | 84 | 0 | 0 | 0 | 🔴 零调用白交税 |
| save_skill | 84 | 0 | 0 | 0 | 🔴 零调用白交税 |
| github_setup | 82 | 0 | 0 | 0 | 🔴 零调用白交税 |
| notion_setup | 80 | 0 | 0 | 0 | 🔴 零调用白交税 |
| browser_get_title | 80 | 0 | 0 | 0 | 🔴 零调用白交税 |
| batch_delete_notes | 79 | 0 | 0 | 0 | 🔴 零调用白交税 |
| notion_search | 78 | 0 | 0 | 0 | 🔴 零调用白交税 |
| read_email_content | 76 | 0 | 0 | 0 | 🔴 零调用白交税 |
| read_worker_result | 75 | 1 | 0 | 0 | 🟠 极低频（<5） |
| list_folder | 75 | 11 | 0 | 0 | 🟢 健康 |
| web_fetch | 72 | 11 | 0 | 0 | 🟢 健康 |
| read_recent | 72 | 0 | 0 | 0 | 🔴 零调用白交税 |
| delete_note | 72 | 0 | 0 | 0 | 🔴 零调用白交税 |
| create_folder | 71 | 0 | 0 | 0 | 🔴 零调用白交税 |
| cross_search | 70 | 1 | 0 | 0 | 🟠 极低频（<5） |
| notion_read_page | 70 | 0 | 0 | 0 | 🔴 零调用白交税 |
| classify_analyze | 67 | 0 | 0 | 0 | 🔴 零调用白交税 |
| web_extract | 66 | 0 | 0 | 0 | 🔴 零调用白交税 |
| send_notification | 65 | 0 | 0 | 0 | 🔴 零调用白交税 |
| web_fetch_markdown | 62 | 0 | 0 | 0 | 🔴 零调用白交税 |
| list_calendar_events | 61 | 0 | 0 | 0 | 🔴 零调用白交税 |
| analyze_emails | 60 | 0 | 0 | 0 | 🔴 零调用白交税 |
| git_status | 60 | 35 | 0 | 0 | 🟢 健康 |
| read_email_recent | 59 | 0 | 0 | 0 | 🔴 零调用白交税 |
| search_emails | 59 | 0 | 0 | 0 | 🔴 零调用白交税 |
| classify_confirm | 57 | 0 | 0 | 0 | 🔴 零调用白交税 |
| create_calendar_event | 57 | 0 | 0 | 0 | 🔴 零调用白交税 |
| write_clipboard | 56 | 0 | 0 | 0 | 🔴 零调用白交税 |
| search_memory | 54 | 23 | 0 | 0 | 🟢 健康 |
| open_url | 52 | 0 | 0 | 0 | 🔴 零调用白交税 |
| read_clipboard | 46 | 0 | 0 | 0 | 🔴 零调用白交税 |
| render | 45 | 0 | 0 | 0 | 🔴 零调用白交税 |
| github_check_auth | 44 | 0 | 0 | 0 | 🔴 零调用白交税 |
| wiki_rebuild | 43 | 0 | 0 | 0 | 🔴 零调用白交税 |
| list_reminders | 39 | 0 | 0 | 0 | 🔴 零调用白交税 |

**零调用工具 51 个**：api_register, code_to_obsidian, review_to_obsidian, cross_project_search, github_pr_comment, set_reminder, discuss_with_pi, browser_open, notion_create_page, index_project, restore_checkpoint, github_create_repo, move_note, notion_append, copy_to_notion, delete_folder, copy_to_obsidian, batch_copy_notes, github_create_pr, move_to_folder, rename_note, batch_move_notes, github_pr_diff, save_skill, github_setup, notion_setup, browser_get_title, batch_delete_notes, notion_search, read_email_content, read_recent, delete_note, create_folder, notion_read_page, classify_analyze, web_extract, send_notification, web_fetch_markdown, list_calendar_events, analyze_emails, read_email_recent, search_emails, classify_confirm, create_calendar_event, write_clipboard, open_url, read_clipboard, render, github_check_auth, wiki_rebuild, list_reminders
**极低频（<5 次）工具 8 个**：spawn_worker, bobo_schedule, bobo_config, api_call, append_obsidian, web_search, read_worker_result, cross_search

## 亲缘工具合并候选（人工标注，待沙盒验证）

- file 写系：edit_file / file_operation / file_writer
- obsidian 系（13 个）：write/append/read/search/copy_to/code_to/review_to/move/rename/delete/list_folder/create_folder/batch_*
- notion 系（6 个）：create_page/append/read_page/search/copy_to/setup
- email 系（4 个）：read_content/read_recent/search/analyze
- github 系（6 个）：create_pr/pr_diff/pr_comment/create_repo/setup/check_auth
- web 系（5 个）：search/fetch/fetch_markdown/extract/open_url
- 剪贴板：write_clipboard / read_clipboard
- 提醒日历：set_reminder/list_reminders/create_calendar_event/list_calendar_events