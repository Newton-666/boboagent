# 测试覆盖缺口报告

**生成日期**: 2026-07-29
**扫描范围**: `core/*.py` (24 模块) + `tools/*.py` (79 文件)
**方法**: 逐个文件提取公开函数/类 → 对照 tests/ 目录引用 → 判定覆盖状态
**风险等级**: 🔴 高（引擎链路核心，零测试）| 🟡 中（重要模块，覆盖不完整）| 🟢 低（间接覆盖或有兜底）

---

## 一、Core 引擎链路（高优先级，按风险排序）

### ~~🔴 高 — 零测试~~ ✅ 已补齐

| 文件 | 函数/类 | 状态 | 测试数 |
|------|---------|------|--------|
| `core/tracer.py` | `Tracer` 类, `get_tracer()`, `trace()` | ✅ `test_tracer.py` | 12 |
| `core/code_checks.py` | `py_compile_check(path)` | ✅ `test_code_checks.py` | 8 |
| `core/diff_utils.py` | `make_inline_diff(old, new, path_hint)` | ✅ `test_diff_utils.py` | 11 |
| `core/duo_orchestrator.py` | `run_deliberation(question, emit, sid)` | ✅ `test_duo_orchestrator.py` | 13 |

### 🟡 中 — 部分覆盖

| 文件 | 函数/类 | 风险 | 说明 |
|------|---------|------|------|
| `core/skill_manager.py` | `SkillManager`, `get_skill_manager()` | 🟡 | test_injector.py 中有 MockSkillManager，但 SkillManager 自身（技能发现、加载、匹配）无直接单元测试 |
| `core/context.py` | `ContextMixin` 类（完整类） | 🟡 | test_context.py 覆盖 query_classification / tool_filtering / history_compression，但 ContextMixin._compress_context / _mark_result 等内部方法无白盒测试 |
| `core/engine_adapter.py` | `cancel(sid)`, `is_running(sid)`, `run_engine(...)` | 🟡 | test_tui_status_light.py 覆盖 emit 序列验证，但 run_engine 的完整路径（含 Llama 端错误/断线重连）无集成测试 |
| `core/llm_caller.py` | `HeadersStallError`, `create_llm_caller(...)` | 🟡 | test_llm_caller.py 覆盖 message_building/streaming/error_handling，但 HeadersStallError 触发路径无测试 |
| `core/tool_runner.py` | `ToolRunnerMixin` 类 | 🟡 | test_batch1_fixes.py 测试 `_format_final_output`，test_command_safety.py 测试硬拒绝路径，但完整 `run_tool` 流程无白盒测试 |

### 🟢 低 — 充分覆盖

| 文件 | 覆盖情况 |
|------|---------|
| `core/engine.py` | test_engine_e2e.py (25) + test_engine_core.py (24) — 充分 |
| `core/event_bus.py` | test_event_bus.py (16) — 充分 |
| `core/injector.py` | test_injector.py (9) — 充分 |
| `core/provider.py` | test_provider.py (19) — 充分 |
| `core/proactive.py` | test_proactive.py (13) — 充分 |
| `core/command_safety.py` | test_command_safety.py (58) — 充分 |
| `core/file_safety.py` | test_bugfixes.py Phase 2 — 充分 |
| `core/verifier.py` | test_verifier.py (4) — 充分 |
| `core/round_tracker.py` | test_round_tracker.py (9) — 充分 |
| `core/checkpoint.py` | test_checkpoint.py (9) — 充分 |
| `core/session_manager.py` | test_session_manager.py (25) — 充分 |
| `core/skill_loader.py` | test_skill_loader.py (6) — 充分 |
| `core/emoji_cleaner.py` | test_emoji_cleaner.py (4) — 充分 |

---

## 二、Tools 工具层（按使用频率排序）

### 🔴 高 — 零测试（execute() 无直接覆盖）

| 文件 | 公开函数 | 风险 | 建议方向 |
|------|---------|------|---------|
| `tools/get_current_time.py` | `execute`, `register` | ~~🔴~~ ✅ `test_misc_tools.py` | 6 tests, 含 full/date/time/weekday/默认值/schema |
| `tools/git_status.py` | `execute`, `register` | ~~🔴~~ ✅ `test_misc_tools.py` | 5 tests, mock subprocess, 含分支变更/干净/非git仓库/自定义路径/schema |
| `tools/grep_code.py` | `execute`, `register`, `_search_python`, `_search_ripgrep` | ~~🔴~~ ✅ `test_grep_code.py` | 18 tests, 含临时文件树夹具/正则/文件类型过滤/context/隐藏文件/回退路径/注册表 |
| `tools/index_project.py` | `execute`, `register` | 🔴 | 写集成测试：在临时目录中验证索引 JSON 结构 |
| `tools/list_directory.py` | `execute`, `is_sensitive_path`, `register` | ~~🔴~~ ✅ `test_list_directory.py` | 19 tests, 含敏感路径检测/目录列表/hidden/max_items/错误路径/注册表 |
| `tools/open_url.py` | `execute`, `register` | ~~🔴~~ ✅ `test_misc_tools.py` | 6 tests, mock subprocess, 含成功/失败/超时/FileNotFound/异常/schema |
| `tools/read_obsidian.py` | `execute`, `register` | 🔴 | 写单元测试：在临时 Obsidian vault 中验证读取内容 |
| `tools/read_recent.py` | `execute`, `register` | 🔴 | 写单元测试：Mock os.walk，验证按 mtime 排序逻辑 |
| `tools/search_obsidian.py` | `execute`, `register` | 🔴 | 写集成测试：在临时 vault 中验证关键词匹配 |
| `tools/run_tests.py` | `execute`, `register` | 🔴 | 写集成测试：验证 pytest 调用和结果解析 |
| `tools/save_skill.py` | `execute`, `register`, `set_engine` | 🔴 | 写单元测试：mock 文件写入验证 skill 保存 |
| `tools/review_diff.py` | `execute`, `register` | 🔴 | 写单元测试：在临时 git 仓库中验证 diff 输出 |
| `tools/restore_checkpoint.py` | `register` 等 | ~~🔴~~ ✅ `test_misc_tools.py` | 3 tests, 含 TOOL_NAME常量/TOOL_FUNC=None/schema |
| `tools/render.py` | `execute`, `register`, `latex_to_unicode`, `remove_tables`, `render_markdown` | 🔴 | 写单元测试：验证 LaTeX→Unicode、表格删除、markdown 渲染 |
| `tools/browser.py` | `open_url`, `get_page_title`, `register` | 🔴 | 写单元测试（mock selenium）：验证 URL 打开和标题获取 |
| `tools/clipboard.py` | `read`, `write`, `register` | 🔴 | 写单元测试（mock pyperclip）：验证读写一致性 |
| `tools/notification.py` | `send`, `register` | 🔴 | 写单元测试：验证通知格式和参数传递 |
| `tools/reminder.py` | `execute`, `list_reminders`, `parse_time`, `register` | 🔴 | 写单元测试：验证 parse_time 对 5分钟/3小时 等自然语言解析 |
| `tools/web_search.py` | `execute`, `register` | ~~🔴~~ ✅ `test_web_tools.py` | 4 tests, mock crawler.web_search, 含参数传递/默认值/空查询/schema |
| `tools/web_extract.py` | `execute`, `register` | ~~🔴~~ ✅ `test_web_tools.py` | 3 tests, mock crawler.web_fetch_markdown, 含 URL 传递/空 URL/schema |
| `tools/web_fetch.py` | `execute`, `register` | ~~🔴~~ ✅ `test_web_tools.py` | 2 tests, mock crawler.web_fetch, 含 URL 传递/schema |
| `tools/wiki_rebuild.py` | `execute`, `register` | 🔴 | 写集成测试：在临时 vault 中验证交叉链接发现 |
| `tools/notion_setup.py` | `execute`, `register` | 🔴 | 写单元测试（mock API）：验证 token 配置和验证 |
| `tools/bobo_config.py` | `execute`, `register` | 🔴 | 写单元测试：验证 view/set 动作，环境变量读写 |
| `tools/bobo_schedule.py` | `execute`, `register` | 🔴 | 写单元测试（mock cron）：验证 create/list/delete 调度 |
| `tools/classify_note.py` | `analyze`, `confirm_move`, `register` | 🔴 | 写单元测试：验证分析逻辑和移动确认流程 |
| `tools/code_to_obsidian.py` | `execute`, `register` | 🔴 | 写单元测试：验证代码文件复制到 vault |
| `tools/cross_project_search.py` | `execute`, `register` | 🔴 | 写集成测试：验证跨目录搜索结果聚合 |
| `tools/cross_search.py` | `register` | 🔴 | 写集成测试：验证多数据源搜索结果合并 |
| `tools/create_calendar_event.py` | `execute`, `register` | 🔴 | 写单元测试（mock 日历API）：验证事件创建参数 |
| `tools/list_calendar_events.py` | `execute`, `register` | 🔴 | 写单元测试（mock 日历API）：验证事件列表过滤 |
| `tools/email_module.py` | `analyze_emails_tool`, `is_sensitive_email`, `process_emails_with_privacy`, `read_email_content_tool`, `read_recent_tool`, `search_emails_tool`, `register` | 🔴 | 写单元测试：Mock 邮件 API，验证敏感检测、隐私处理、搜索 |
| `tools/analyze_emails.py` | `execute`, `register` | 🔴 | 写单元测试（mock 邮件 API）：验证分析结果格式 |
| `tools/read_email_content.py` | `execute`, `register` | 🔴 | 写单元测试（mock 邮件 API）：验证邮件内容读取 |
| `tools/search_emails.py` | `execute`, `register` | 🔴 | 写单元测试（mock 邮件 API）：验证搜索过滤和分页 |
| `tools/api_call.py` | `execute`, `register` | 🔴 | 写单元测试（mock requests）：验证 API 调用和参数传递 |
| `tools/api_register.py` | `execute`, `register` | 🔴 | 写单元测试：验证 API 注册和端点存储 |
| `tools/crawler.py` | `web_fetch`, `web_fetch_markdown`, `web_search`, `register` | 🔴 | 写单元测试（mock 请求）：验证抓取和 Markdown 转换 |
| `tools/copy_to_obsidian.py` | `execute`, `register` | 🔴 | 写单元测试：Mock Notion API 和 vault 写入 |
| `tools/notion_append.py` | `execute`, `register` | 🔴 | 写单元测试（mock Notion API）：验证追加块 |
| `tools/notion_create_page.py` | `execute`, `register` | 🔴 | 写单元测试（mock Notion API）：验证页面创建 |
| `tools/notion_read_page.py` | `execute`, `register` | 🔴 | 写单元测试（mock Notion API）：验证页面内容读取 |
| `tools/notion_search.py` | `execute`, `register` | 🔴 | 写单元测试（mock Notion API）：验证搜索逻辑 |
| `tools/move_to_folder.py` | `execute`, `register` | 🔴 | 写单元测试：验证文件夹移动逻辑 |

### 🟡 中 — 间接覆盖或部分覆盖

| 文件 | 覆盖情况 | 缺口 |
|------|---------|------|
| `tools/execute_terminal.py` | 🟡 `is_dangerous` 在 test_p0_fixes.py 中测试 | `execute()`（命令执行/超时/白名单）无直接测试 |
| `tools/github_create_repo.py` | ~~🟡~~ ✅ test_github_tools.py | 6 tests, mock subprocess, 含 public/private/description/gh未安装/超时 |
| `tools/github_check_auth.py` | ~~🟡~~ ✅ test_github_tools.py | 5 tests, mock subprocess, 含已登录/未登录/未安装/异常 |
| `tools/github_create_pr.py` | ~~🟡~~ ✅ test_github_tools.py | 5 tests, mock subprocess, 含 title/body/base/失败 |
| `tools/github_pr_comment.py` | ~~🟡~~ ✅ test_github_tools.py | 5 tests, mock subprocess, 含普通评论/inline/失败/超时 |
| `tools/github_pr_diff.py` | ~~🟡~~ ✅ test_github_tools.py | 6 tests, mock subprocess, 含 pr_num/repo/空diff/截断/失败 |
| `tools/github_setup.py` | ~~🟡~~ ✅ test_github_tools.py | 4 tests, mock subprocess+open, 含 token 校验/保存/gh未安装仍保存 |
| `tools/v5_memory.py` | 🟡 test_p1_memory.py 覆盖基本 CRUD | `get_memory_stats`, `format_user_profile` 等辅助函数无测试 |
| `tools/file_writer.py` | 🟡 test_p0_path_traversal.py 覆盖路径安全 | `write_obsidian`/`append_obsidian`/`read_file` 自身功能无白盒测试 |
| `tools/create_folder.py` | 🟡 obsidian_tools.create_folder 间接测试 | 独立 create_folder 工具的 execute() 无测试 |
| `tools/delete_folder.py` | 🟡 obsidian_tools.delete_folder 间接测试 | 独立 delete_folder 工具的 execute() 无测试 |
| `tools/delete_note.py` | 🟡 obsidian_tools.delete_note 间接测试 | 独立 delete_note 工具的 execute() 无测试 |
| `tools/list_folder.py` | 🟡 obsidian_tools.list_folder 间接测试 | 独立 list_folder 工具的 execute() 无测试 |
| `tools/move_note.py` | 🟡 obsidian_tools.move_note 间接测试 | 独立 move_note 工具的 execute() 无测试 |
| `tools/rename_note.py` | 🟡 obsidian_tools.rename_note 间接测试 | 独立 rename_note 工具的 execute() 无测试 |

### 🟢 低 — 充分覆盖

| 文件 | 覆盖情况 |
|------|---------|
| `tools/_url_safety.py` | test_url_safety.py (7) — 充分 |
| `tools/file_operation.py` | test_bugfixes.py 10+ 用例 + test_p0_path_traversal.py — 充分 |
| `tools/read_local_file.py` | test_bugfixes.py (offset/limit/cache/truncate) — 充分 |
| `tools/edit_file.py` | test_bugfixes.py (find/execute/diff/py_compile) — 充分 |
| `tools/code_execution.py` | test_bugfixes.py + test_p0_fixes.py — 充分 |
| `tools/write_obsidian.py` | test_bugfixes.py — 充分 |
| `tools/append_obsidian.py` | test_bugfixes.py — 充分 |
| `tools/refactor.py` | test_bugfixes.py (dry_run/search/replace) — 充分 |
| `tools/spawn_worker.py` | test_spawn_worker.py (10) + test_bugfixes.py — 充分 |
| `tools/task_ledger.py` | test_task_ledger.py (29) — 充分 |
| `tools/load_result.py` | test_context_marking.py — 充分 |
| `tools/obsidian_tools.py` | test_p0_path_traversal.py (路径安全) — 充分 |
| `tools/batch_copy_notes.py` | test_p0_path_traversal.py — 充分 |
| `tools/copy_to_notion.py` | test_p0_path_traversal.py — 充分 |
| `tools/review_to_obsidian.py` | test_p0_path_traversal.py — 充分 |

---

## 三、汇总统计

| 类别 | 总数 | 充分覆盖 (🟢) | 部分/间接 (🟡) | 零测试 (🔴) |
|------|------|-------------|---------------|------------|
| Core 模块 | 24 | 13 | 7 | 4 |
| Tools 文件 | 79 | 15 | 22 | 42 |

**核心发现**：
1. **tracer.py** 是唯一的零测试 Core 基础设施模块（trace 装饰器贯穿引擎流程）
2. **diff_utils.py** 和 **code_checks.py** 是零测试的工具函数，被 edit_file/file_operation 依赖，属于级联风险
3. **Tools 层 42 个零测试文件**中，多数是简单胶水工具（读/写/搜索/日历），每个只需 1-2 个测试即可覆盖主要路径
4. GitHub 工具族（6 个文件）集体缺乏测试，皆因需要 mock gh CLI
5. Web 工具族缺乏测试（需 mock 网络请求），但 web_search/web_fetch/web_extract 是用户高频调用

**建议修复优先级**：
1. **P0**: core/tracer.py + core/diff_utils.py + core/code_checks.py（引擎链路依赖）
2. **P1**: tools/grep_code.py + tools/list_directory.py（高频工具，逻辑独立）
3. **P2**: tools/ web 三件套 + GitHub 六件套（需 mock 外部依赖）
4. **P3**: 其余 30+ 工具（每件 5-10 行胶水，低风险）
