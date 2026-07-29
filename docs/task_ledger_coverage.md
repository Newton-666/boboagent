# 测试覆盖普查 — 任务台账

**创建**: 2026-07-29
**状态**: ✅ 完成 — 报告已写入 docs/coverage-gaps.md

## 扫描清单

### Core 模块（24 个）
- [x] 全部扫描完成 → 13 绿 / 7 黄 / 4 红
  - 🔴 零测试: ~~tracer.py, code_checks.py, diff_utils.py, duo_orchestrator.py~~ ✅ 已全部补齐（44 条新测试）
  - 🟡 部分: skill_manager.py, context.py, engine_adapter.py, llm_caller.py, tool_runner.py
  - 🟢 充分: engine, event_bus, injector, provider, proactive, command_safety, file_safety, verifier, round_tracker, checkpoint, session_manager, skill_loader, emoji_cleaner, tracer, code_checks, diff_utils, duo_orchestrator

### Tools 模块（79 个）
- [x] 全部扫描完成 → 30 绿 / 15 黄 / 33 红
  - 🟢 充分: _url_safety, file_operation, read_local_file, edit_file, code_execution, write_obsidian, append_obsidian, refactor, spawn_worker, task_ledger, load_result, obsidian_tools, batch_copy_notes, copy_to_notion, review_to_obsidian, grep_code, list_directory, web_search, web_extract, web_fetch, github_check_auth, github_setup, github_create_repo, github_create_pr, github_pr_diff, github_pr_comment, get_current_time, git_status, open_url, restore_checkpoint
  - 🟡 间接: execute_terminal, github_*, v5_memory, file_writer, 独立 obsidian 胶水工具
  - 🔴 零测试: index_project, read_obsidian, read_recent, search_obsidian, run_tests, save_skill, review_diff, render, browser, clipboard, notification, reminder, wiki_rebuild, notion_*, bobo_config, bobo_schedule, classify_note, code_to_obsidian, cross_*, calendar_*, email_*, api_*, crawler, copy_to_obsidian, move_to_folder

### 报告
- [x] 已输出: docs/coverage-gaps.md（162 行, 含完整统计与建议优先级）
