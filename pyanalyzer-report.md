# PyAnalyzer 代码分析报告

- **生成时间**: 2026-07-19 18:19:03
- **分析文件数**: 142
- **检测到异味**: 669
- **CI 模式**: 关闭
- **Diff 模式**: 关闭

## 配置阈值

| 指标 | 阈值 |
|------|------|
| 最大参数数 | 5 |
| 最大函数长度 | 50 行 |
| 最大圈复杂度 | 10 |
| 最大嵌套深度 | 4 |

## 检测到的代码异味

| 类型 | 严重程度 | 文件 | 行号 | 描述 |
|------|----------|------|------|------|
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 3 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 4 | 未使用的导入: logging (来自 logging) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 5 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 6 | 未使用的导入: signal (来自 signal) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 7 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 13 | 未使用的导入: dispatch (来自 bobo_tui_gateway.server) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 14 | 未使用的导入: write_json (来自 bobo_tui_gateway.transport) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 21 | 未使用的导入: shutdown_sessions (来自 bobo_tui_gateway.server) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 59 | 未使用的导入: signal (来自 signal) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 60 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 61 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 62 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 106 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 128 | 未使用的导入: signal (来自 signal) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 142 | 未使用的导入: API_KEY (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 182 | 未使用的导入: shutdown_sessions (来自 bobo_tui_gateway.server) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 192 | 未使用的导入: _load_schedules (来自 tools.bobo_schedule) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 198 | 未使用的导入: API_KEY (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 198 | 未使用的导入: API_BASE_URL (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 198 | 未使用的导入: API_MODEL_NAME (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 199 | 未使用的导入: create_llm_caller (来自 core.llm_caller) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 200 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 201 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 202 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py | 103 | 函数过长: _run_backend (67 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 3 | 未使用的导入: annotations (来自 __future__) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 5 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 6 | 未使用的导入: logging (来自 logging) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 7 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 8 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 9 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 10 | 未使用的导入: uuid (来自 uuid) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 11 | 未使用的导入: threading (来自 threading) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 12 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 13 | 未使用的导入: Any (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 19 | 未使用的导入: write_json (来自 bobo_tui_gateway.transport) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 149 | 未使用的导入: API_MODEL_NAME (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 149 | 未使用的导入: ACTIVE_PROVIDER (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 150 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 151 | 未使用的导入: ContextMixin (来自 core.context) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 152 | 未使用的导入: get_skill_manager (来自 core.skill_manager) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 194 | 未使用的导入: API_KEY (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 194 | 未使用的导入: ACTIVE_PROVIDER (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 213 | 未使用的导入: get_provider (来自 core.provider) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 457 | 未使用的导入: _run_engine_adapter (来自 core.engine_adapter) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 482 | 未使用的导入: API_MODEL_NAME (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 508 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 601 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 42 | 未使用的导入: resolve_provider (来自 core.provider) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 83 | 未使用的导入: SessionManager (来自 core.session_manager) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 84 | 未使用的导入: SESSION_DIR (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 113 | 未使用的导入: create_llm_caller (来自 core.llm_caller) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 114 | 未使用的导入: API_KEY (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 114 | 未使用的导入: API_BASE_URL (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 114 | 未使用的导入: API_MODEL_NAME (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 115 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 409 | 未使用的导入: cancel (来自 core.engine_adapter) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 730 | 未使用的导入: read_file (来自 tools.read_local_file) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 555 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 570 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 574 | 未使用的导入: API_MODEL_NAME (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 574 | 未使用的导入: ACTIVE_PROVIDER (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 544 | 未使用的导入: os (来自 os) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 518 | 函数过长: handle_slash_exec (72 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py | 518 | 嵌套过深: handle_slash_exec (深度=7, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/transport.py | 3 | 未使用的导入: annotations (来自 __future__) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/transport.py | 5 | 未使用的导入: errno (来自 errno) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/transport.py | 6 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/transport.py | 7 | 未使用的导入: logging (来自 logging) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/transport.py | 8 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/transport.py | 9 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/transport.py | 10 | 未使用的导入: threading (来自 threading) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/transport.py | 11 | 未使用的导入: Any (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/transport.py | 11 | 未使用的导入: Callable (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/config.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/config.py | 4 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/config.py | 5 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/config.py | 6 | 未使用的导入: load_dotenv (来自 dotenv) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/config.py | 41 | 未使用的导入: resolve_provider (来自 core.provider) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/config.py | 65 | 未使用的导入: getpass (来自 getpass) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/__init__.py | 1 | 未使用的导入: Engine (来自 engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/context.py | 3 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/context.py | 4 | 未使用的导入: Optional (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/context.py | 195 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/context.py | 73 | 函数过长: _compress_history (99 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/context.py | 73 | 嵌套过深: _compress_history (深度=5, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 3 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 4 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 5 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 6 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 7 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 8 | 未使用的导入: threading (来自 threading) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 9 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 10 | 未使用的导入: Dict (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 10 | 未使用的导入: Any (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 10 | 未使用的导入: List (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 10 | 未使用的导入: Optional (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 10 | 未使用的导入: Callable (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 10 | 未使用的导入: Tuple (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 15 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 16 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 17 | 未使用的导入: get_skill_manager (来自 core.skill_manager) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 18 | 未使用的导入: get_skill_executor (来自 core.skill_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 19 | 未使用的导入: ContextMixin (来自 core.context) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 20 | 未使用的导入: ToolRunnerMixin (来自 core.tool_runner) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 360 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 368 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 414 | 未使用的导入: copy (来自 copy) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 414 | 未使用的导入: _os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 466 | 未使用的导入: _os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 805 | 未使用的导入: _re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 1088 | 未使用的导入: clear_cache (来自 tools.file_operation) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 303 | 未使用的导入: _jl (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 562 | 未使用的导入: _skill_mgr (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 630 | 未使用的导入: format_user_profile (来自 tools.v5_memory) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 630 | 未使用的导入: format_all_memory (来自 tools.v5_memory) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 650 | 未使用的导入: _os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 1006 | 未使用的导入: _je (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 1024 | 未使用的导入: _j (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 964 | 未使用的导入: _je (来自 json) |
| too-many-params | error | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 33 | 参数过多: __init__ (6 个参数, 阈值=5) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 89 | 函数过长: _build_system_prompt (119 行, 阈值=50) |
| too-many-params | error | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 233 | 参数过多: _record_message (6 个参数, 阈值=5) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 286 | 函数过长: _check_guards (59 行, 阈值=50) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 491 | 函数过长: _call_llm (202 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 491 | 嵌套过深: _call_llm (深度=8, 阈值=4) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 911 | 函数过长: _step (140 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py | 911 | 嵌套过深: _step (深度=9, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine_adapter.py | 6 | 未使用的导入: threading (来自 threading) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine_adapter.py | 46 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine_adapter.py | 47 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine_adapter.py | 159 | 未使用的导入: set_worker_event_emitter (来自 tools.spawn_worker) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine_adapter.py | 204 | 未使用的导入: logging (来自 logging) |
| too-many-params | error | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine_adapter.py | 27 | 参数过多: run_engine (15 个参数, 阈值=5) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine_adapter.py | 27 | 函数过长: run_engine (171 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine_adapter.py | 27 | 嵌套过深: run_engine (深度=10, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/file_safety.py | 7 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/file_safety.py | 8 | 未使用的导入: struct (来自 struct) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/file_safety.py | 9 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/file_safety.py | 10 | 未使用的导入: Optional (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/file_safety.py | 10 | 未使用的导入: Set (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/llm_caller.py | 5 | 未使用的导入: requests (来自 requests) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/llm_caller.py | 6 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/llm_caller.py | 7 | 未使用的导入: time (来自 time) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/llm_caller.py | 10 | 函数过长: _classify_error (54 行, 阈值=50) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/llm_caller.py | 80 | 函数过长: create_llm_caller (131 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/llm_caller.py | 80 | 嵌套过深: create_llm_caller (深度=6, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/provider.py | 75 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/provider.py | 78 | 未使用的导入: load_dotenv (来自 dotenv) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/session_manager.py | 5 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/session_manager.py | 6 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/session_manager.py | 7 | 未使用的导入: getpass (来自 getpass) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/session_manager.py | 8 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/session_manager.py | 9 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_executor.py | 3 | 未使用的导入: yaml (来自 yaml) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_executor.py | 4 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_executor.py | 5 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_executor.py | 6 | 未使用的导入: List (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_executor.py | 6 | 未使用的导入: Dict (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_executor.py | 63 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_executor.py | 88 | 未使用的导入: get_skill_manager (来自 core.skill_manager) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_manager.py | 3 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_manager.py | 4 | 未使用的导入: yaml (来自 yaml) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_manager.py | 5 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_manager.py | 6 | 未使用的导入: Optional (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_manager.py | 73 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_manager.py | 16 | 嵌套过深: _load_all (深度=5, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_executor.py | 5 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_executor.py | 6 | 未使用的导入: ThreadPoolExecutor (来自 concurrent.futures) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_executor.py | 6 | 未使用的导入: TimeoutError (来自 concurrent.futures) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_executor.py | 7 | 未使用的导入: TOOL_FUNCTIONS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 3 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 4 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 5 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 6 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 7 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 8 | 未使用的导入: ThreadPoolExecutor (来自 concurrent.futures) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 8 | 未使用的导入: as_completed (来自 concurrent.futures) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 48 | 未使用的导入: _execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 49 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 344 | 未使用的导入: Counter (来自 collections) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 383 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 443 | 未使用的导入: _os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 393 | 未使用的导入: _list_trash (来自 tools.obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 449 | 未使用的导入: OBSIDIAN_VAULT (来自 tools.obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 449 | 未使用的导入: BLOCKED_FOLDERS (来自 tools.obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 452 | 未使用的导入: search_obsidian_notes (来自 tools.obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 479 | 未使用的导入: _req (来自 requests) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 522 | 未使用的导入: EmailModule (来自 tools.email_module) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 416 | 未使用的导入: shutil (来自 shutil) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 502 | 未使用的导入: _dt (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 532 | 未使用的导入: parsedate_to_datetime (来自 email.utils) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 47 | 函数过长: _execute_tool_loop (294 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 47 | 嵌套过深: _execute_tool_loop (深度=10, 阈值=4) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 428 | 函数过长: _handle_cross_search (166 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py | 428 | 嵌套过深: _handle_cross_search (深度=8, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tracer.py | 3 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tracer.py | 4 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tracer.py | 5 | 未使用的导入: wraps (来自 functools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/skills/ai_startup_collector.py | 7 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/skills/ai_startup_collector.py | 8 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/skills/ai_startup_collector.py | 9 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/skills/ai_startup_collector.py | 10 | 未使用的导入: hashlib (来自 hashlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/skills/ai_startup_collector.py | 11 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/conftest.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/conftest.py | 4 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/conftest.py | 5 | 未使用的导入: tempfile (来自 tempfile) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/conftest.py | 6 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/conftest.py | 7 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/conftest.py | 52 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/conftest.py | 53 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/conftest.py | 54 | 未使用的导入: MockLLMCaller (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/conftest.py | 54 | 未使用的导入: text_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/mock_llm.py | 42 | 未使用的导入: time (来自 time) |
| too-many-params | error | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/mock_llm.py | 21 | 参数过多: __call__ (6 个参数, 阈值=5) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 4 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 5 | 未使用的导入: tempfile (来自 tempfile) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 6 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 7 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 19 | 未使用的导入: gh_execute (来自 tools.github_create_repo) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 23 | 未使用的导入: inspect (来自 inspect) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 32 | 未使用的导入: inspect (来自 inspect) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 33 | 未使用的导入: gh_execute (来自 tools.github_create_repo) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 48 | 未使用的导入: execute (来自 tools.file_operation) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 63 | 未使用的导入: execute (来自 tools.file_operation) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 77 | 未使用的导入: execute (来自 tools.file_operation) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 90 | 未使用的导入: SKIP_DIRS (来自 tools.search_code) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 95 | 未使用的导入: SKIP_DIRS (来自 tools.search_code) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 101 | 未使用的导入: _should_skip (来自 tools.search_code) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 117 | 未使用的导入: execute (来自 tools.file_operation) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 130 | 未使用的导入: execute (来自 tools.file_operation) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 146 | 未使用的导入: execute (来自 tools.file_operation) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 162 | 未使用的导入: SEARCH_SKIP (来自 tools.search_code) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 163 | 未使用的导入: grep_exec (来自 tools.grep_code) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 178 | 未使用的导入: MAX_OUTPUT_CHARS (来自 tools.code_execution) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 183 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 183 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 184 | 未使用的导入: _run_python (来自 tools.code_execution) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 190 | 未使用的导入: tempfile (来自 tempfile) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 198 | 未使用的导入: _run_python (来自 tools.code_execution) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 215 | 未使用的导入: execute (来自 tools.read_local_file) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 227 | 未使用的导入: execute (来自 tools.read_local_file) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 240 | 未使用的导入: execute (来自 tools.read_local_file) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 255 | 未使用的导入: _find_similar_lines (来自 tools.edit_file) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 265 | 未使用的导入: _find_similar_lines (来自 tools.edit_file) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 278 | 未使用的导入: _find_similar_lines (来自 tools.edit_file) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 293 | 未使用的导入: execute (来自 tools.edit_file) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 313 | 未使用的导入: execute (来自 tools.refactor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 323 | 未使用的导入: execute (来自 tools.refactor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 343 | 未使用的导入: execute (来自 tools.refactor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 361 | 未使用的导入: execute (来自 tools.refactor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 378 | 未使用的导入: TOOL_SCHEMA (来自 tools.refactor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 395 | 未使用的导入: is_write_denied (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 400 | 未使用的导入: is_write_denied (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 401 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 406 | 未使用的导入: is_write_denied (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 407 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 412 | 未使用的导入: is_write_denied (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 419 | 未使用的导入: execute (来自 tools.file_operation) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 425 | 未使用的导入: execute (来自 tools.edit_file) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 434 | 未使用的导入: is_binary_file (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 442 | 未使用的导入: is_binary_file (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 449 | 未使用的导入: is_binary_file (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 460 | 未使用的导入: sanitize_env (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 468 | 未使用的导入: sanitize_env (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 475 | 未使用的导入: sanitize_env (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 489 | 未使用的导入: execute (来自 tools.code_execution) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 498 | 未使用的导入: execute (来自 tools.code_execution) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 506 | 未使用的导入: TOOL_SCHEMA (来自 tools.code_execution) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 514 | 未使用的导入: tempfile (来自 tempfile) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 514 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 515 | 未使用的导入: _save_code (来自 tools.code_execution) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py | 517 | 未使用的导入: PROJECTS_DIR (来自 tools.code_execution) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_command_safety.py | 9 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_command_safety.py | 10 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_command_safety.py | 11 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_command_safety.py | 17 | 未使用的导入: MockLLMCaller (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_command_safety.py | 17 | 未使用的导入: text_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py | 4 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py | 5 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py | 9 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py | 10 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py | 15 | 未使用的导入: MockLLMCaller (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py | 15 | 未使用的导入: text_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py | 133 | 未使用的导入: ContextMixin (来自 core.context) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py | 139 | 未使用的导入: ContextMixin (来自 core.context) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py | 144 | 未使用的导入: Counter (来自 collections) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_engine_core.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_engine_core.py | 4 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_engine_core.py | 5 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_engine_core.py | 6 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_engine_core.py | 10 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_engine_core.py | 11 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_engine_core.py | 12 | 未使用的导入: MockLLMCaller (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_engine_core.py | 12 | 未使用的导入: text_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_engine_core.py | 12 | 未使用的导入: tool_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_llm_caller.py | 7 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_llm_caller.py | 8 | 未使用的导入: requests (来自 requests) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_llm_caller.py | 9 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_llm_caller.py | 10 | 未使用的导入: _classify_error (来自 core.llm_caller) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_mock_engine.py | 3 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_mock_engine.py | 6 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_mock_engine.py | 7 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_mock_engine.py | 8 | 未使用的导入: MockLLMCaller (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_mock_engine.py | 8 | 未使用的导入: text_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_mock_engine.py | 8 | 未使用的导入: tool_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 4 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 5 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 6 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 17 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 18 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 19 | 未使用的导入: MockLLMCaller (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 19 | 未使用的导入: text_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 19 | 未使用的导入: tool_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 37 | 未使用的导入: execute (来自 tools.code_execution) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 50 | 未使用的导入: execute (来自 tools.code_execution) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 68 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 69 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 70 | 未使用的导入: MockLLMCaller (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 70 | 未使用的导入: text_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 84 | 未使用的导入: is_dangerous (来自 tools.execute_terminal) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 93 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 94 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 95 | 未使用的导入: MockLLMCaller (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 95 | 未使用的导入: text_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 96 | 未使用的导入: is_dangerous (来自 tools.execute_terminal) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 121 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 122 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 123 | 未使用的导入: MockLLMCaller (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 123 | 未使用的导入: text_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 123 | 未使用的导入: tool_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 192 | 未使用的导入: TOOL_FUNCTIONS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 197 | 未使用的导入: TOOL_FUNCTIONS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 202 | 未使用的导入: TOOL_FUNCTIONS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 207 | 未使用的导入: TOOL_FUNCTIONS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 213 | 未使用的导入: TOOL_FUNCTIONS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py | 213 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_provider.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_provider.py | 4 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_provider.py | 5 | 未使用的导入: get_provider (来自 core.provider) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_provider.py | 5 | 未使用的导入: list_providers (来自 core.provider) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_provider.py | 5 | 未使用的导入: resolve_provider (来自 core.provider) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_provider.py | 5 | 未使用的导入: PROVIDERS (来自 core.provider) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_secret_redaction.py | 7 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_secret_redaction.py | 8 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_secret_redaction.py | 9 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_secret_redaction.py | 14 | 未使用的导入: MockLLMCaller (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_secret_redaction.py | 14 | 未使用的导入: text_response (来自 tests.mock_llm) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_session_manager.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_session_manager.py | 4 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_session_manager.py | 5 | 未使用的导入: tempfile (来自 tempfile) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_session_manager.py | 6 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_session_manager.py | 7 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_session_manager.py | 9 | 未使用的导入: SessionManager (来自 core.session_manager) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_session_manager.py | 85 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_session_manager.py | 99 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_session_manager.py | 225 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 4 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 5 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 6 | 未使用的导入: pytest (来自 pytest) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 16 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 20 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 24 | 未使用的导入: TOOL_FUNCTIONS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 29 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 41 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 51 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 83 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 99 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 114 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 129 | 未使用的导入: register_tool (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 129 | 未使用的导入: TOOL_FUNCTIONS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 129 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 154 | 未使用的导入: TOOL_CHECKS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 158 | 未使用的导入: TOOL_FUNCTIONS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py | 172 | 未使用的导入: TOOL_CHECKS (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/__init__.py | 3 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/__init__.py | 4 | 未使用的导入: importlib.util (来自 importlib.util) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/__init__.py | 5 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/__init__.py | 6 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/__init__.py | 83 | 未使用的导入: get_skill_manager (来自 core.skill_manager) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/analyze_emails.py | 6 | 未使用的导入: EmailModule (来自 email_module) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/api_call.py | 3 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/api_call.py | 4 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/api_call.py | 5 | 未使用的导入: requests (来自 requests) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/api_call.py | 10 | 函数过长: execute (60 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/api_call.py | 10 | 嵌套过深: execute (深度=5, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/api_register.py | 3 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/api_register.py | 4 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/append_obsidian.py | 6 | 未使用的导入: append_obsidian (来自 file_writer) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/batch_copy_notes.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/batch_copy_notes.py | 4 | 未使用的导入: shutil (来自 shutil) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/batch_delete_notes.py | 6 | 未使用的导入: delete_note (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/batch_move_notes.py | 7 | 未使用的导入: move_note (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_config.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_config.py | 4 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_config.py | 18 | 未使用的导入: resolve_provider (来自 core.provider) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_config.py | 9 | 函数过长: execute (53 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_config.py | 9 | 嵌套过深: execute (深度=5, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_schedule.py | 3 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_schedule.py | 4 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_schedule.py | 5 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_schedule.py | 160 | 未使用的导入: sys (来自 sys) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_schedule.py | 96 | 函数过长: execute (55 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/browser.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/browser.py | 4 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/browser.py | 5 | 未使用的导入: Optional (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/browser.py | 22 | 未使用的导入: requests (来自 requests) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/browser.py | 23 | 未使用的导入: BeautifulSoup (来自 bs4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/classify_note.py | 3 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/classify_note.py | 33 | 未使用的导入: read_note (来自 tools.read_obsidian) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/classify_note.py | 70 | 未使用的导入: move_note (来自 tools.move_note) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/classify_note.py | 75 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/clipboard.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 4 | 未使用的导入: tempfile (来自 tempfile) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 5 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 6 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 7 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 8 | 未使用的导入: sanitize_env (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 13 | 未使用的导入: _CONFIG_PROJECTS_DIR (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 162 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 185 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 107 | 未使用的导入: ast (来自 ast) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 482 | 未使用的导入: ast (来自 ast) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py | 265 | 嵌套过深: _run_code (深度=5, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_to_obsidian.py | 7 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_to_obsidian.py | 8 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_to_obsidian.py | 9 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_to_obsidian.py | 10 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_to_obsidian.py | 74 | 未使用的导入: rebuild (来自 tools.wiki_rebuild) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/copy_to_notion.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/copy_to_notion.py | 41 | 未使用的导入: notion_create (来自 tools.notion_create_page) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/copy_to_obsidian.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/copy_to_obsidian.py | 11 | 未使用的导入: notion_read (来自 tools.notion_read_page) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/copy_to_obsidian.py | 23 | 未使用的导入: write_obsidian (来自 tools.file_writer) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/crawler.py | 5 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/crawler.py | 6 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/crawler.py | 7 | 未使用的导入: requests (来自 requests) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/crawler.py | 8 | 未使用的导入: BeautifulSoup (来自 bs4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/crawler.py | 45 | 未使用的导入: DDGS (来自 ddgs) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/create_calendar_event.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/create_calendar_event.py | 4 | 未使用的导入: shlex (来自 shlex) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/create_folder.py | 6 | 未使用的导入: create_folder (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/cross_project_search.py | 6 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/cross_project_search.py | 7 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/cross_project_search.py | 8 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/cross_project_search.py | 9 | 未使用的导入: Optional (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/cross_project_search.py | 117 | 未使用的导入: defaultdict (来自 collections) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/cross_project_search.py | 34 | 函数过长: execute (81 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/cross_project_search.py | 34 | 嵌套过深: execute (深度=8, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/delete_folder.py | 6 | 未使用的导入: delete_folder (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/delete_note.py | 6 | 未使用的导入: delete_note (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/edit_file.py | 14 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/edit_file.py | 15 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/edit_file.py | 16 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/edit_file.py | 17 | 未使用的导入: is_write_denied (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/edit_file.py | 65 | 未使用的导入: re (来自 re) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/edit_file.py | 81 | 函数过长: execute (70 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 6 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 7 | 未使用的导入: imaplib (来自 imaplib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 8 | 未使用的导入: email (来自 email) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 9 | 未使用的导入: decode_header (来自 email.header) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 10 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 11 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 12 | 未使用的导入: Counter (来自 collections) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 13 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 13 | 未使用的导入: timedelta (来自 datetime) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 82 | 函数过长: read_email_content (58 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 82 | 嵌套过深: read_email_content (深度=5, 阈值=4) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py | 317 | 嵌套过深: process_emails_with_privacy (深度=5, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/execute_terminal.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/execute_terminal.py | 4 | 未使用的导入: shlex (来自 shlex) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/execute_terminal.py | 5 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/execute_terminal.py | 6 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/execute_terminal.py | 7 | 未使用的导入: sanitize_env (来自 core.file_safety) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/execute_terminal.py | 54 | 函数过长: execute (54 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_operation.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_operation.py | 4 | 未使用的导入: hashlib (来自 hashlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_operation.py | 5 | 未使用的导入: shutil (来自 shutil) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_operation.py | 6 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_operation.py | 7 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_operation.py | 8 | 未使用的导入: is_write_denied (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_operation.py | 8 | 未使用的导入: safe_read_check (来自 core.file_safety) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_operation.py | 55 | 函数过长: execute (63 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_operation.py | 55 | 嵌套过深: execute (深度=5, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py | 6 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py | 7 | 未使用的导入: shutil (来自 shutil) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py | 8 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py | 9 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py | 10 | 未使用的导入: Optional (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py | 12 | 未使用的导入: OBSIDIAN_VAULT (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py | 12 | 未使用的导入: BOBO_FOLDER (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py | 12 | 未使用的导入: BLOCKED_FOLDERS (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py | 13 | 未使用的导入: _normalize_path (来自 obsidian_tools) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py | 99 | 函数过长: append_obsidian (58 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/get_current_time.py | 3 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/git_status.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/git_status.py | 4 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_check_auth.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_create_pr.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_create_repo.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_create_repo.py | 4 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_pr_comment.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_pr_comment.py | 4 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_pr_diff.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_setup.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_setup.py | 4 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_setup.py | 27 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/grep_code.py | 14 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/grep_code.py | 15 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/grep_code.py | 16 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/grep_code.py | 17 | 未使用的导入: Path (来自 pathlib) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/grep_code.py | 69 | 函数过长: _search_ripgrep (59 行, 阈值=50) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/grep_code.py | 132 | 函数过长: execute (52 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/index_project.py | 6 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/index_project.py | 7 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/index_project.py | 8 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/index_project.py | 9 | 未使用的导入: Optional (来自 typing) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/index_project.py | 435 | 未使用的导入: save_to_knowledge_base (来自 tools.v5_memory) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/index_project.py | 30 | 函数过长: _extract_summary (59 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/index_project.py | 30 | 嵌套过深: _extract_summary (深度=7, 阈值=4) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/index_project.py | 97 | 嵌套过深: _extract_imports (深度=8, 阈值=4) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/index_project.py | 357 | 函数过长: execute (78 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/list_calendar_events.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/list_directory.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/list_directory.py | 4 | 未使用的导入: Path (来自 pathlib) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/list_directory.py | 22 | 嵌套过深: execute (深度=5, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/list_folder.py | 6 | 未使用的导入: list_folder (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/move_note.py | 6 | 未使用的导入: move_note (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/move_to_folder.py | 6 | 未使用的导入: move_to_folder (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notification.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_append.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_append.py | 4 | 未使用的导入: requests (来自 requests) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_create_page.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_create_page.py | 4 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_create_page.py | 5 | 未使用的导入: requests (来自 requests) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_read_page.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_read_page.py | 4 | 未使用的导入: requests (来自 requests) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_read_page.py | 13 | 函数过长: execute (51 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_read_page.py | 13 | 嵌套过深: execute (深度=5, 阈值=4) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_read_page.py | 69 | 嵌套过深: _extract_block_text (深度=10, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_search.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_search.py | 4 | 未使用的导入: requests (来自 requests) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_search.py | 13 | 嵌套过深: execute (深度=6, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_setup.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_setup.py | 4 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_setup.py | 35 | 未使用的导入: requests (来自 requests) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 5 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 6 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 7 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 8 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 9 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 10 | 未使用的导入: OBSIDIAN_VAULT (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 10 | 未使用的导入: BOBO_FOLDER (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 10 | 未使用的导入: BLOCKED_FOLDERS (来自 config) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 278 | 未使用的导入: write_obsidian (来自 file_writer) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 283 | 未使用的导入: append_obsidian (来自 file_writer) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 452 | 未使用的导入: list_folder_func (来自 list_folder) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 452 | 未使用的导入: list_folder_name (来自 list_folder) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 453 | 未使用的导入: search_obsidian_func (来自 search_obsidian) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 453 | 未使用的导入: search_obsidian_name (来自 search_obsidian) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 454 | 未使用的导入: read_obsidian_func (来自 read_obsidian) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 454 | 未使用的导入: read_obsidian_name (来自 read_obsidian) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 455 | 未使用的导入: write_obsidian_func (来自 write_obsidian) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 455 | 未使用的导入: write_obsidian_name (来自 write_obsidian) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 456 | 未使用的导入: move_note_func (来自 move_note) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 456 | 未使用的导入: move_note_name (来自 move_note) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 457 | 未使用的导入: delete_note_func (来自 delete_note) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 457 | 未使用的导入: delete_note_name (来自 delete_note) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 304 | 未使用的导入: shutil (来自 shutil) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 323 | 未使用的导入: shutil (来自 shutil) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 418 | 未使用的导入: shutil (来自 shutil) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 13 | 函数过长: _normalize_path (61 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 13 | 嵌套过深: _normalize_path (深度=5, 阈值=4) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 101 | 函数过长: search_obsidian_notes (55 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 101 | 嵌套过深: search_obsidian_notes (深度=7, 阈值=4) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py | 166 | 函数过长: read_obsidian_note (52 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/open_url.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/project_info.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/project_info.py | 4 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_email_content.py | 6 | 未使用的导入: EmailModule (来自 email_module) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py | 4 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py | 5 | 未使用的导入: safe_read_check (来自 core.file_safety) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py | 33 | 未使用的导入: pypdf (来自 pypdf) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py | 41 | 未使用的导入: docx (来自 docx) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py | 49 | 未使用的导入: Presentation (来自 pptx) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py | 62 | 未使用的导入: openpyxl (来自 openpyxl) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py | 13 | 函数过长: _read_single_file (86 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py | 13 | 嵌套过深: _read_single_file (深度=9, 阈值=4) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py | 106 | 嵌套过深: _read_directory (深度=5, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_obsidian.py | 6 | 未使用的导入: read_obsidian_note (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_recent.py | 6 | 未使用的导入: EmailModule (来自 email_module) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/refactor.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/refactor.py | 4 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/refactor.py | 5 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/refactor.py | 123 | 未使用的导入: edit_one (来自 tools.edit_file) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/refactor.py | 145 | 未使用的导入: _find_similar_lines (来自 tools.edit_file) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/refactor.py | 29 | 嵌套过深: _search_files (深度=7, 阈值=4) |
| too-many-params | error | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/refactor.py | 83 | 参数过多: execute (8 个参数, 阈值=5) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/refactor.py | 83 | 函数过长: execute (101 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/refactor.py | 83 | 嵌套过深: execute (深度=6, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/reminder.py | 3 | 未使用的导入: threading (来自 threading) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/reminder.py | 4 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/reminder.py | 5 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/reminder.py | 6 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/reminder.py | 6 | 未使用的导入: timedelta (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/reminder.py | 63 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/rename_note.py | 6 | 未使用的导入: rename_note (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/render.py | 3 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/render.py | 4 | 未使用的导入: time (来自 time) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/render.py | 5 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_diff.py | 3 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_diff.py | 4 | 未使用的导入: os (来自 os) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_diff.py | 9 | 函数过长: execute (54 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_to_obsidian.py | 7 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_to_obsidian.py | 8 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_to_obsidian.py | 9 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_to_obsidian.py | 10 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_to_obsidian.py | 78 | 未使用的导入: rebuild (来自 tools.wiki_rebuild) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_to_obsidian.py | 17 | 函数过长: execute (55 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/run_tests.py | 13 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/run_tests.py | 14 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/run_tests.py | 15 | 未使用的导入: subprocess (来自 subprocess) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/run_tests.py | 16 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/run_tests.py | 37 | 未使用的导入: json (来自 json) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/run_tests.py | 55 | 嵌套过深: _run_pytest (深度=5, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/save_memory.py | 3 | 未使用的导入: sys (来自 sys) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/save_memory.py | 4 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/save_memory.py | 10 | 未使用的导入: save_to_knowledge_base (来自 tools.v5_memory) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/save_skill.py | 3 | 未使用的导入: get_skill_manager (来自 core.skill_manager) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_code.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_code.py | 4 | 未使用的导入: re (来自 re) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_code.py | 30 | 函数过长: execute (56 行, 阈值=50) |
| deep-nesting | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_code.py | 30 | 嵌套过深: execute (深度=7, 阈值=4) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_emails.py | 6 | 未使用的导入: EmailModule (来自 email_module) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_memory.py | 6 | 未使用的导入: search_knowledge_base (来自 v5_memory) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_obsidian.py | 6 | 未使用的导入: search_obsidian_notes (来自 obsidian_tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 8 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 9 | 未使用的导入: threading (来自 threading) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 10 | 未使用的导入: ThreadPoolExecutor (来自 concurrent.futures) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 10 | 未使用的导入: TimeoutError (来自 concurrent.futures) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 93 | 未使用的导入: create_llm_caller (来自 core.llm_caller) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 94 | 未使用的导入: resolve_provider (来自 core.provider) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 95 | 未使用的导入: TOOLS_SCHEMA (来自 tools) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 108 | 未使用的导入: ThreadPoolExecutor (来自 concurrent.futures) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 108 | 未使用的导入: _FutTimeout (来自 concurrent.futures) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 175 | 未使用的导入: Engine (来自 core.engine) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 176 | 未使用的导入: execute_tool (来自 core.tool_executor) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 147 | 未使用的导入: _re (来自 re) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py | 161 | 函数过长: execute (95 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/v5_memory.py | 4 | 未使用的导入: json (来自 json) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/v5_memory.py | 5 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/v5_memory.py | 6 | 未使用的导入: tempfile (来自 tempfile) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/v5_memory.py | 7 | 未使用的导入: shutil (来自 shutil) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/v5_memory.py | 8 | 未使用的导入: datetime (来自 datetime) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/v5_memory.py | 9 | 未使用的导入: Path (来自 pathlib) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/web_extract.py | 6 | 未使用的导入: web_fetch_markdown (来自 crawler) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/web_fetch.py | 6 | 未使用的导入: web_fetch (来自 crawler) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/web_search.py | 6 | 未使用的导入: web_search (来自 crawler) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/wiki_rebuild.py | 3 | 未使用的导入: os (来自 os) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/wiki_rebuild.py | 4 | 未使用的导入: re (来自 re) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/wiki_rebuild.py | 89 | 未使用的导入: notion_search (来自 tools.notion_search) |
| too-long | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/wiki_rebuild.py | 9 | 函数过长: execute (114 行, 阈值=50) |
| unused-import | warning | /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/write_obsidian.py | 6 | 未使用的导入: write_obsidian (来自 file_writer) |

## 文件详情

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/__init__.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/entry.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_shutdown` | 19 | 2 | 4 | 1 | 0 | - |
| `resolve_skin` | 30 | 0 | 24 | 1 | 0 | - |
| `main` | 57 | 0 | 35 | 5 | 2 | - |
| `_run_backend` | 103 | 0 | 67 | 18 | 4 | - |

**导入:**
- `import json` → json
- `import logging` → logging
- `import os` → os
- `import signal` → signal
- `import sys` → sys
- `from bobo_tui_gateway.server` → dispatch
- `from bobo_tui_gateway.transport` → write_json
- `from bobo_tui_gateway.server` → shutdown_sessions
- `import signal` → signal
- `import subprocess` → subprocess
- `import sys` → sys
- `from pathlib` → Path
- `from pathlib` → Path
- `import signal` → signal
- `from config` → API_KEY
- `from bobo_tui_gateway.server` → shutdown_sessions
- `from tools.bobo_schedule` → _load_schedules
- `from config` → API_KEY, API_BASE_URL, API_MODEL_NAME
- `from core.llm_caller` → create_llm_caller
- `from core.tool_executor` → execute_tool
- `from core.engine` → Engine
- `from tools` → TOOLS_SCHEMA

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/server.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_get_context_length` | 37 | 0 | 9 | 3 | 1 | - |
| `register_engine_thread` | 61 | 1 | 2 | 1 | 1 | - |
| `shutdown_sessions` | 66 | 0 | 8 | 3 | 2 | - |
| `_get_session_mgr` | 80 | 0 | 6 | 2 | 1 | - |
| `method` | 89 | 1 | 4 | 1 | 0 | - |
| `_ok` | 96 | 2 | 1 | 1 | 0 | - |
| `_err` | 100 | 3 | 1 | 1 | 0 | - |
| `_emit` | 104 | 3 | 4 | 2 | 0 | - |
| `_get_llm_caller` | 111 | 0 | 6 | 2 | 1 | - |
| `_save_session_to_disk` | 120 | 1 | 24 | 3 | 1 | - |
| `_build_session_info` | 148 | 1 | 33 | 9 | 3 | - |
| `handle_setup_status` | 193 | 2 | 6 | 1 | 0 | - |
| `handle_setup_submit` | 203 | 2 | 44 | 13 | 4 | - |
| `handle_session_create` | 256 | 2 | 16 | 1 | 1 | - |
| `handle_session_title` | 279 | 2 | 8 | 3 | 1 | - |
| `handle_session_list` | 291 | 2 | 25 | 5 | 4 | - |
| `handle_session_resume` | 320 | 2 | 41 | 8 | 4 | - |
| `handle_session_close` | 370 | 2 | 5 | 1 | 1 | - |
| `handle_session_delete` | 379 | 2 | 11 | 3 | 1 | - |
| `handle_session_rename` | 394 | 2 | 8 | 3 | 1 | - |
| `handle_session_interrupt` | 406 | 2 | 7 | 2 | 1 | - |
| `handle_session_steer` | 417 | 2 | 1 | 1 | 0 | - |
| `handle_approval_respond` | 422 | 2 | 17 | 4 | 4 | - |
| `handle_prompt_submit` | 445 | 2 | 26 | 3 | 1 | - |
| `handle_config_get` | 480 | 2 | 4 | 1 | 0 | - |
| `handle_config_set` | 488 | 2 | 1 | 1 | 0 | - |
| `handle_config_full` | 493 | 2 | 10 | 1 | 0 | - |
| `handle_tools_list` | 507 | 2 | 6 | 2 | 1 | - |
| `handle_slash_exec` | 518 | 2 | 72 | 16 | 7 | - |
| `handle_command_dispatch` | 594 | 2 | 2 | 1 | 0 | - |
| `handle_shell_exec` | 600 | 2 | 9 | 4 | 1 | - |
| `handle_image_attach` | 613 | 2 | 1 | 1 | 0 | - |
| `handle_paste_collapse` | 618 | 2 | 1 | 1 | 0 | - |
| `handle_terminal_resize` | 623 | 2 | 1 | 1 | 0 | - |
| `handle_session_active_list` | 628 | 2 | 10 | 2 | 2 | - |
| `handle_session_activate` | 642 | 2 | 22 | 5 | 3 | - |
| `handle_input_detect_drop` | 668 | 2 | 1 | 1 | 0 | - |
| `handle_commands_catalog` | 673 | 2 | 2 | 1 | 0 | - |
| `handle_project_set_root` | 679 | 2 | 16 | 6 | 3 | - |
| `_scan_directory` | 699 | 2 | 21 | 8 | 4 | - |
| `handle_file_read` | 724 | 2 | 10 | 3 | 1 | - |
| `handle_completion` | 738 | 2 | 2 | 1 | 0 | - |
| `dispatch` | 745 | 1 | 11 | 4 | 1 | - |

**导入:**
- `from __future__` → annotations
- `import json` → json
- `import logging` → logging
- `import os` → os
- `import sys` → sys
- `import time` → time
- `import uuid` → uuid
- `import threading` → threading
- `from datetime` → datetime
- `from typing` → Any
- `from bobo_tui_gateway.transport` → write_json
- `from config` → API_MODEL_NAME, ACTIVE_PROVIDER
- `from tools` → TOOLS_SCHEMA
- `from core.context` → ContextMixin
- `from core.skill_manager` → get_skill_manager
- `from config` → API_KEY, ACTIVE_PROVIDER
- `from core.provider` → get_provider
- `from core.engine_adapter` → _run_engine_adapter
- `from config` → API_MODEL_NAME
- `from tools` → TOOLS_SCHEMA
- `import subprocess` → subprocess
- `from core.provider` → resolve_provider
- `from core.session_manager` → SessionManager
- `from config` → SESSION_DIR
- `from core.llm_caller` → create_llm_caller
- `from config` → API_KEY, API_BASE_URL, API_MODEL_NAME
- `from tools` → TOOLS_SCHEMA
- `from core.engine_adapter` → cancel
- `from tools.read_local_file` → read_file
- `import os` → os
- `from tools` → TOOLS_SCHEMA
- `from config` → API_MODEL_NAME, ACTIVE_PROVIDER
- `import os` → os

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/static/__init__.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/bobo_tui_gateway/transport.py

**类:**
- `StdioTransport` (行 23) — 方法: __init__, write, close

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `__init__` | 26 | 1 | 1 | 1 | 0 | StdioTransport |
| `write` | 29 | 2 | 10 | 3 | 2 | StdioTransport |
| `close` | 41 | 1 | 1 | 1 | 0 | StdioTransport |
| `write_json` | 49 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from __future__` → annotations
- `import errno` → errno
- `import json` → json
- `import logging` → logging
- `import os` → os
- `import sys` → sys
- `import threading` → threading
- `from typing` → Any, Callable

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/config.py

**导入:**
- `import os` → os
- `import sys` → sys
- `from pathlib` → Path
- `from dotenv` → load_dotenv
- `from core.provider` → resolve_provider
- `import getpass` → getpass

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/__init__.py

**导入:**
- `from engine` → Engine

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/context.py

**类:**
- `ContextMixin` (行 7) — 方法: _compress_history, _classify_query, _get_filtered_tools

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_compress_history` | 73 | 1 | 99 | 40 | 5 | ContextMixin |
| `_classify_query` | 182 | 1 | 9 | 6 | 3 | ContextMixin |
| `_get_filtered_tools` | 193 | 2 | 27 | 19 | 3 | ContextMixin |

**导入:**
- `import re` → re
- `from typing` → Optional
- `from tools` → TOOLS_SCHEMA

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine.py

**类:**
- `Engine` (行 23) — 方法: __init__, _notify, _confirm, _build_system_prompt, _handle_teaching_mode, _record_message, _check_skill_match, _handle_pre_input, _compress_changelog, _check_guards, _is_phase_complete, _extract_phase_summary, _handle_phase_transition, _save_checkpoint, _find_checkpoint, _do_undo, _call_llm, _append_to_history, _classify_command, _is_high_risk_tool, _remove_emojis, _needs_verification, _append_verification_note, _extract_response, _step, run, reset

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `__init__` | 33 | 6 | 33 | 3 | 0 | Engine |
| `_notify` | 72 | 3 | 2 | 2 | 1 | Engine |
| `_confirm` | 76 | 4 | 11 | 5 | 2 | Engine |
| `_build_system_prompt` | 89 | 1 | 119 | 1 | 0 | Engine |
| `_handle_teaching_mode` | 212 | 2 | 19 | 6 | 2 | Engine |
| `_record_message` | 233 | 6 | 11 | 5 | 1 | Engine |
| `_check_skill_match` | 246 | 2 | 2 | 1 | 0 | Engine |
| `_handle_pre_input` | 250 | 2 | 20 | 8 | 2 | Engine |
| `_compress_changelog` | 273 | 1 | 11 | 6 | 1 | Engine |
| `_check_guards` | 286 | 1 | 59 | 18 | 4 | Engine |
| `_is_phase_complete` | 358 | 2 | 6 | 3 | 2 | Engine |
| `_extract_phase_summary` | 366 | 2 | 7 | 3 | 0 | Engine |
| `_handle_phase_transition` | 378 | 1 | 20 | 9 | 3 | Engine |
| `_save_checkpoint` | 412 | 2 | 19 | 6 | 4 | Engine |
| `_find_checkpoint` | 434 | 2 | 15 | 6 | 2 | Engine |
| `_do_undo` | 453 | 2 | 30 | 7 | 3 | Engine |
| `_call_llm` | 491 | 1 | 202 | 58 | 8 | Engine |
| `_append_to_history` | 722 | 5 | 18 | 8 | 4 | Engine |
| `_classify_command` | 790 | 2 | 36 | 14 | 4 | Engine |
| `_is_high_risk_tool` | 840 | 3 | 18 | 7 | 2 | Engine |
| `_remove_emojis` | 864 | 2 | 4 | 2 | 1 | Engine |
| `_needs_verification` | 870 | 2 | 10 | 3 | 2 | Engine |
| `_append_verification_note` | 884 | 1 | 8 | 1 | 0 | Engine |
| `_extract_response` | 894 | 2 | 15 | 7 | 2 | Engine |
| `_step` | 911 | 1 | 140 | 51 | 9 | Engine |
| `run` | 1055 | 5 | 27 | 10 | 2 | Engine |
| `reset` | 1086 | 1 | 21 | 1 | 0 | Engine |

**导入:**
- `import sys` → sys
- `import os` → os
- `import json` → json
- `import re` → re
- `import time` → time
- `import threading` → threading
- `from pathlib` → Path
- `from typing` → Dict, Any, List, Optional, Callable, Tuple
- `from tools` → TOOLS_SCHEMA
- `from core.tool_executor` → execute_tool
- `from core.skill_manager` → get_skill_manager
- `from core.skill_executor` → get_skill_executor
- `from core.context` → ContextMixin
- `from core.tool_runner` → ToolRunnerMixin
- `import re` → re
- `import re` → re
- `import copy` → copy
- `import os` → _os
- `import os` → _os
- `import re` → _re
- `from tools.file_operation` → clear_cache
- `import json` → _jl
- `from tools` → _skill_mgr
- `from tools.v5_memory` → format_user_profile, format_all_memory
- `import os` → _os
- `import json` → _je
- `import json` → _j
- `import json` → _je

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/engine_adapter.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `cancel` | 13 | 1 | 5 | 2 | 1 | - |
| `is_running` | 21 | 1 | 3 | 1 | 1 | - |
| `run_engine` | 27 | 15 | 171 | 23 | 10 | - |

**导入:**
- `import threading` → threading
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tools.spawn_worker` → set_worker_event_emitter
- `import logging` → logging

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/file_safety.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `is_write_denied` | 85 | 1 | 19 | 8 | 3 | - |
| `is_binary_file` | 151 | 1 | 22 | 8 | 2 | - |
| `safe_read_check` | 187 | 1 | 13 | 4 | 2 | - |
| `sanitize_env` | 245 | 1 | 27 | 11 | 3 | - |

**导入:**
- `import os` → os
- `import struct` → struct
- `from pathlib` → Path
- `from typing` → Optional, Set

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/llm_caller.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_classify_error` | 10 | 2 | 54 | 12 | 2 | - |
| `create_llm_caller` | 80 | 4 | 131 | 32 | 6 | - |

**导入:**
- `import requests` → requests
- `import json` → json
- `import time` → time

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/provider.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `get_provider` | 55 | 1 | 2 | 1 | 0 | - |
| `list_providers` | 60 | 0 | 2 | 1 | 0 | - |
| `resolve_provider` | 65 | 2 | 37 | 11 | 2 | - |

**导入:**
- `import os` → os
- `from dotenv` → load_dotenv

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/session_manager.py

**类:**
- `SessionManager` (行 14) — 方法: __init__, new_session, rename_session, list_sessions, load_session, add_message, add_system_message, get_message_count, get_new_messages, reload_session, _migrate_session, _write_atomic, _save

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `__init__` | 15 | 3 | 10 | 3 | 1 | SessionManager |
| `new_session` | 27 | 2 | 15 | 2 | 0 | SessionManager |
| `rename_session` | 44 | 2 | 4 | 2 | 1 | SessionManager |
| `list_sessions` | 50 | 2 | 15 | 3 | 3 | SessionManager |
| `load_session` | 67 | 2 | 9 | 2 | 1 | SessionManager |
| `add_message` | 78 | 3 | 13 | 5 | 2 | SessionManager |
| `add_system_message` | 93 | 2 | 8 | 2 | 1 | SessionManager |
| `get_message_count` | 103 | 1 | 3 | 2 | 1 | SessionManager |
| `get_new_messages` | 108 | 2 | 6 | 3 | 1 | SessionManager |
| `reload_session` | 116 | 1 | 5 | 3 | 3 | SessionManager |
| `_migrate_session` | 123 | 2 | 11 | 4 | 2 | SessionManager |
| `_write_atomic` | 136 | 3 | 20 | 4 | 2 | SessionManager |
| `_save` | 159 | 1 | 6 | 3 | 1 | SessionManager |

**导入:**
- `import json` → json
- `import os` → os
- `import getpass` → getpass
- `from datetime` → datetime
- `from pathlib` → Path

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_executor.py

**类:**
- `SkillExecutor` (行 26) — 方法: __init__, save_from_recording, load_skill, execute_skill

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_auto_triggers` | 9 | 2 | 12 | 6 | 2 | - |
| `__init__` | 27 | 2 | 2 | 1 | 0 | SkillExecutor |
| `save_from_recording` | 31 | 4 | 40 | 9 | 4 | SkillExecutor |
| `load_skill` | 79 | 2 | 5 | 2 | 1 | SkillExecutor |
| `execute_skill` | 86 | 3 | 3 | 1 | 0 | SkillExecutor |
| `get_skill_executor` | 95 | 0 | 4 | 2 | 1 | - |

**导入:**
- `import yaml` → yaml
- `import re` → re
- `from pathlib` → Path
- `from typing` → List, Dict
- `import json` → json
- `from core.skill_manager` → get_skill_manager

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/skill_manager.py

**类:**
- `SkillManager` (行 9) — 方法: __init__, _load_all, list_skills, get_skill, get_skill_tools, execute_skill, add_skill, _resolve_vars

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `__init__` | 10 | 2 | 4 | 1 | 0 | SkillManager |
| `_load_all` | 16 | 1 | 23 | 9 | 5 | SkillManager |
| `list_skills` | 42 | 1 | 1 | 1 | 0 | SkillManager |
| `get_skill` | 45 | 2 | 1 | 1 | 0 | SkillManager |
| `get_skill_tools` | 48 | 1 | 21 | 3 | 2 | SkillManager |
| `execute_skill` | 71 | 3 | 24 | 11 | 4 | SkillManager |
| `add_skill` | 100 | 2 | 6 | 1 | 1 | SkillManager |
| `_resolve_vars` | 108 | 3 | 9 | 5 | 2 | SkillManager |
| `get_skill_manager` | 123 | 0 | 4 | 2 | 1 | - |

**导入:**
- `import json` → json
- `import yaml` → yaml
- `from pathlib` → Path
- `from typing` → Optional
- `from core.tool_executor` → execute_tool

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_executor.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute_tool` | 17 | 2 | 43 | 15 | 4 | - |

**导入:**
- `import time` → time
- `from concurrent.futures` → ThreadPoolExecutor, TimeoutError
- `from tools` → TOOL_FUNCTIONS

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tool_runner.py

**类:**
- `ToolRunnerMixin` (行 11) — 方法: _redact_secrets, _format_final_output, _execute_tool_loop, _restore_checkpoint, _handle_restore_checkpoint, _handle_cross_search

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_redact_secrets` | 27 | 2 | 3 | 2 | 1 | ToolRunnerMixin |
| `_format_final_output` | 32 | 2 | 13 | 6 | 3 | ToolRunnerMixin |
| `_execute_tool_loop` | 47 | 2 | 294 | 79 | 10 | ToolRunnerMixin |
| `_restore_checkpoint` | 360 | 2 | 18 | 6 | 2 | ToolRunnerMixin |
| `_handle_restore_checkpoint` | 380 | 3 | 43 | 11 | 4 | ToolRunnerMixin |
| `_handle_cross_search` | 428 | 3 | 166 | 46 | 8 | ToolRunnerMixin |

**导入:**
- `import json` → json
- `import os` → os
- `import re` → re
- `import subprocess` → subprocess
- `import time` → time
- `from concurrent.futures` → ThreadPoolExecutor, as_completed
- `from core.tool_executor` → _execute_tool
- `from tools` → TOOLS_SCHEMA
- `from collections` → Counter
- `import os` → os
- `import os` → _os
- `from tools.obsidian_tools` → _list_trash
- `from tools.obsidian_tools` → OBSIDIAN_VAULT, BLOCKED_FOLDERS
- `from tools.obsidian_tools` → search_obsidian_notes
- `import requests` → _req
- `from tools.email_module` → EmailModule
- `import shutil` → shutil
- `from datetime` → _dt
- `from email.utils` → parsedate_to_datetime

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/core/tracer.py

**类:**
- `Tracer` (行 7) — 方法: __init__, start, end, report, clear

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `__init__` | 8 | 1 | 2 | 1 | 0 | Tracer |
| `start` | 12 | 2 | 7 | 2 | 1 | Tracer |
| `end` | 21 | 2 | 10 | 7 | 3 | Tracer |
| `report` | 33 | 1 | 15 | 4 | 2 | Tracer |
| `clear` | 51 | 1 | 1 | 1 | 0 | Tracer |
| `get_tracer` | 57 | 0 | 4 | 2 | 1 | - |
| `trace` | 63 | 1 | 15 | 2 | 1 | - |

**导入:**
- `import time` → time
- `from datetime` → datetime
- `from functools` → wraps

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_152830/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_152850/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_153416/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_153443/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_153444/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_153455/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_154222/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_154256/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_154321/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_154813/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_155112/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_155137/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_155529/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_155941/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_161213/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_161315/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_161843/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_162320/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_163620/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_164934/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_165303/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_165639/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_170621/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_173948/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_180607/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260616_181605/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260617_140335/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260618_124805/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260618_124822/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260618_203157/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/projects/code_20260618_203202/main.py

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/skills/ai_startup_collector.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `read_existing_entries` | 30 | 0 | 7 | 2 | 1 | - |
| `format_entry` | 41 | 1 | 14 | 1 | 0 | - |
| `append_to_note` | 58 | 1 | 10 | 2 | 1 | - |
| `extract_structured` | 75 | 2 | 27 | 1 | 0 | - |
| `main` | 107 | 0 | 6 | 1 | 0 | - |

**导入:**
- `import json` → json
- `import os` → os
- `import re` → re
- `import hashlib` → hashlib
- `from datetime` → datetime

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/conftest.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `project_root` | 19 | 0 | 2 | 1 | 0 | - |
| `temp_dir` | 25 | 0 | 3 | 1 | 1 | - |
| `temp_vault` | 32 | 1 | 11 | 1 | 1 | - |
| `engine` | 50 | 0 | 7 | 1 | 0 | - |
| `mock_engine` | 62 | 1 | 2 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import sys` → sys
- `import tempfile` → tempfile
- `from pathlib` → Path
- `import pytest` → pytest
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tests.mock_llm` → MockLLMCaller, text_response

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/mock_llm.py

**类:**
- `MockLLMCaller` (行 4) — 方法: __init__, __call__, add_response

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `__init__` | 17 | 2 | 2 | 1 | 0 | MockLLMCaller |
| `__call__` | 21 | 6 | 18 | 6 | 4 | MockLLMCaller |
| `add_response` | 46 | 2 | 2 | 1 | 0 | MockLLMCaller |
| `create_mock_caller` | 51 | 1 | 2 | 2 | 0 | - |
| `text_response` | 57 | 1 | 1 | 1 | 0 | - |
| `tool_response` | 61 | 2 | 6 | 2 | 0 | - |

**导入:**
- `import time` → time

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_bugfixes.py

**类:**
- `TestGitHubCreateRepo` (行 14) — 方法: test_description_included_in_command, test_description_param_has_default
- `TestFileOperationBackup` (行 40) — 方法: test_write_backs_up_existing_file, test_delete_backs_up_file, test_write_new_file_no_backup_needed
- `TestSearchCodeSkipDirs` (行 86) — 方法: test_venv_skipped, test_no_duplicate_dirs, test_skip_dirs_includes_virtual_env
- `TestFileOperationCache` (行 110) — 方法: test_cache_reads_file, test_write_invalidates_cache, test_delete_invalidates_cache
- `TestSearchCodeVsGrepCode` (行 157) — 方法: test_common_skip_dirs_match
- `TestCodeExecutionOutput` (行 174) — 方法: test_output_limit_50k, test_temp_file_cleanup_on_success, test_temp_file_cleanup_on_error
- `TestReadLocalFilePagination` (行 207) — 方法: test_offset_only, test_offset_plus_limit, test_no_offset_no_limit_full_read
- `TestEditFileContextAware` (行 250) — 方法: test_find_similar_lines_substring_match, test_find_similar_lines_keyword_match, test_find_similar_lines_no_match, test_edit_file_error_includes_hints
- `TestRefactorInterface` (行 306) — 方法: test_search_only_returns_matches, test_dry_run_preview_all_matches, test_dry_run_detects_mismatch, test_actual_replace_works, test_changes_interface_accepted
- `TestWriteDenied` (行 391) — 方法: test_blocks_etc_passwd, test_blocks_ssh_key, test_blocks_aws_credentials, test_allows_normal_file, test_file_operation_blocks_write, test_edit_file_blocks_write
- `TestBinaryDetection` (行 430) — 方法: test_png_detected, test_py_not_detected, test_extension_fast_path
- `TestEnvIsolation` (行 456) — 方法: test_strips_api_keys, test_keeps_safe_vars, test_strips_token_vars
- `TestMultiLanguageSupport` (行 485) — 方法: test_go_hello_world, test_rust_hello_world, test_language_enum_includes_go_rust, test_ext_map_includes_go_rust

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `test_description_included_in_command` | 17 | 1 | 8 | 4 | 0 | TestGitHubCreateRepo |
| `test_description_param_has_default` | 30 | 1 | 5 | 2 | 0 | TestGitHubCreateRepo |
| `test_write_backs_up_existing_file` | 43 | 2 | 9 | 3 | 0 | TestFileOperationBackup |
| `test_delete_backs_up_file` | 58 | 2 | 10 | 4 | 0 | TestFileOperationBackup |
| `test_write_new_file_no_backup_needed` | 74 | 2 | 6 | 3 | 0 | TestFileOperationBackup |
| `test_venv_skipped` | 89 | 1 | 3 | 3 | 1 | TestSearchCodeSkipDirs |
| `test_no_duplicate_dirs` | 94 | 1 | 2 | 2 | 0 | TestSearchCodeSkipDirs |
| `test_skip_dirs_includes_virtual_env` | 99 | 1 | 4 | 3 | 0 | TestSearchCodeSkipDirs |
| `test_cache_reads_file` | 113 | 2 | 7 | 3 | 0 | TestFileOperationCache |
| `test_write_invalidates_cache` | 126 | 2 | 8 | 3 | 0 | TestFileOperationCache |
| `test_delete_invalidates_cache` | 142 | 2 | 7 | 2 | 0 | TestFileOperationCache |
| `test_common_skip_dirs_match` | 160 | 1 | 6 | 2 | 0 | TestSearchCodeVsGrepCode |
| `test_output_limit_50k` | 177 | 1 | 2 | 2 | 0 | TestCodeExecutionOutput |
| `test_temp_file_cleanup_on_success` | 181 | 2 | 8 | 4 | 1 | TestCodeExecutionOutput |
| `test_temp_file_cleanup_on_error` | 196 | 1 | 4 | 3 | 0 | TestCodeExecutionOutput |
| `test_offset_only` | 210 | 2 | 9 | 5 | 1 | TestReadLocalFilePagination |
| `test_offset_plus_limit` | 222 | 2 | 10 | 6 | 1 | TestReadLocalFilePagination |
| `test_no_offset_no_limit_full_read` | 235 | 2 | 9 | 5 | 0 | TestReadLocalFilePagination |
| `test_find_similar_lines_substring_match` | 253 | 1 | 7 | 3 | 0 | TestEditFileContextAware |
| `test_find_similar_lines_keyword_match` | 263 | 1 | 7 | 3 | 0 | TestEditFileContextAware |
| `test_find_similar_lines_no_match` | 276 | 1 | 6 | 2 | 0 | TestEditFileContextAware |
| `test_edit_file_error_includes_hints` | 285 | 2 | 15 | 4 | 0 | TestEditFileContextAware |
| `test_search_only_returns_matches` | 309 | 2 | 7 | 4 | 0 | TestRefactorInterface |
| `test_dry_run_preview_all_matches` | 319 | 2 | 17 | 4 | 0 | TestRefactorInterface |
| `test_dry_run_detects_mismatch` | 339 | 2 | 15 | 3 | 0 | TestRefactorInterface |
| `test_actual_replace_works` | 357 | 2 | 16 | 3 | 0 | TestRefactorInterface |
| `test_changes_interface_accepted` | 376 | 1 | 9 | 6 | 0 | TestRefactorInterface |
| `test_blocks_etc_passwd` | 394 | 1 | 3 | 2 | 0 | TestWriteDenied |
| `test_blocks_ssh_key` | 399 | 1 | 4 | 2 | 0 | TestWriteDenied |
| `test_blocks_aws_credentials` | 405 | 1 | 4 | 2 | 0 | TestWriteDenied |
| `test_allows_normal_file` | 411 | 2 | 4 | 2 | 0 | TestWriteDenied |
| `test_file_operation_blocks_write` | 417 | 2 | 4 | 2 | 0 | TestWriteDenied |
| `test_edit_file_blocks_write` | 423 | 2 | 4 | 2 | 0 | TestWriteDenied |
| `test_png_detected` | 433 | 2 | 5 | 2 | 0 | TestBinaryDetection |
| `test_py_not_detected` | 441 | 2 | 5 | 2 | 0 | TestBinaryDetection |
| `test_extension_fast_path` | 448 | 1 | 4 | 3 | 0 | TestBinaryDetection |
| `test_strips_api_keys` | 459 | 1 | 6 | 4 | 0 | TestEnvIsolation |
| `test_keeps_safe_vars` | 467 | 1 | 5 | 3 | 1 | TestEnvIsolation |
| `test_strips_token_vars` | 474 | 1 | 6 | 4 | 0 | TestEnvIsolation |
| `test_go_hello_world` | 488 | 1 | 6 | 4 | 0 | TestMultiLanguageSupport |
| `test_rust_hello_world` | 497 | 1 | 6 | 5 | 0 | TestMultiLanguageSupport |
| `test_language_enum_includes_go_rust` | 505 | 1 | 6 | 5 | 0 | TestMultiLanguageSupport |
| `test_ext_map_includes_go_rust` | 513 | 1 | 7 | 3 | 0 | TestMultiLanguageSupport |

**导入:**
- `import os` → os
- `import sys` → sys
- `import tempfile` → tempfile
- `from pathlib` → Path
- `import pytest` → pytest
- `from tools.github_create_repo` → gh_execute
- `import inspect` → inspect
- `import inspect` → inspect
- `from tools.github_create_repo` → gh_execute
- `from tools.file_operation` → execute
- `from tools.file_operation` → execute
- `from tools.file_operation` → execute
- `from tools.search_code` → SKIP_DIRS
- `from tools.search_code` → SKIP_DIRS
- `from tools.search_code` → _should_skip
- `from tools.file_operation` → execute
- `from tools.file_operation` → execute
- `from tools.file_operation` → execute
- `from tools.search_code` → SEARCH_SKIP
- `from tools.grep_code` → grep_exec
- `from tools.code_execution` → MAX_OUTPUT_CHARS
- `import subprocess` → subprocess
- `import os` → os
- `from tools.code_execution` → _run_python
- `import tempfile` → tempfile
- `from tools.code_execution` → _run_python
- `from tools.read_local_file` → execute
- `from tools.read_local_file` → execute
- `from tools.read_local_file` → execute
- `from tools.edit_file` → _find_similar_lines
- `from tools.edit_file` → _find_similar_lines
- `from tools.edit_file` → _find_similar_lines
- `from tools.edit_file` → execute
- `from tools.refactor` → execute
- `from tools.refactor` → execute
- `from tools.refactor` → execute
- `from tools.refactor` → execute
- `from tools.refactor` → TOOL_SCHEMA
- `from core.file_safety` → is_write_denied
- `from core.file_safety` → is_write_denied
- `from pathlib` → Path
- `from core.file_safety` → is_write_denied
- `from pathlib` → Path
- `from core.file_safety` → is_write_denied
- `from tools.file_operation` → execute
- `from tools.edit_file` → execute
- `from core.file_safety` → is_binary_file
- `from core.file_safety` → is_binary_file
- `from core.file_safety` → is_binary_file
- `from core.file_safety` → sanitize_env
- `from core.file_safety` → sanitize_env
- `from core.file_safety` → sanitize_env
- `from tools.code_execution` → execute
- `from tools.code_execution` → execute
- `from tools.code_execution` → TOOL_SCHEMA
- `import tempfile` → tempfile
- `import os` → os
- `from tools.code_execution` → _save_code
- `from tools.code_execution` → PROJECTS_DIR

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_command_safety.py

**类:**
- `TestSafeCommands` (行 22) — 方法: test_safe_command
- `TestDangerousCommands` (行 105) — 方法: test_dangerous_command
- `TestGrayCommands` (行 158) — 方法: test_gray_command
- `TestEdgeCases` (行 185) — 方法: test_empty_command, test_whitespace_only, test_pipe_with_all_safe_commands, test_pipe_with_one_unknown_makes_gray, test_pipe_whitelist_prefix_does_not_bypass_gray, test_pipe_dangerous_after_safe_is_caught
- `TestHighRiskTool` (行 221) — 方法: test_safe_terminal_not_high_risk, test_dangerous_terminal_is_high_risk, test_gray_terminal_is_high_risk, test_file_operations_always_high_risk, test_shell_exec_is_always_high_risk

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `engine` | 15 | 0 | 4 | 1 | 0 | - |
| `test_safe_command` | 100 | 3 | 2 | 2 | 0 | TestSafeCommands |
| `test_dangerous_command` | 149 | 4 | 5 | 3 | 0 | TestDangerousCommands |
| `test_gray_command` | 180 | 3 | 2 | 2 | 0 | TestGrayCommands |
| `test_empty_command` | 188 | 2 | 2 | 2 | 0 | TestEdgeCases |
| `test_whitespace_only` | 192 | 2 | 2 | 2 | 0 | TestEdgeCases |
| `test_pipe_with_all_safe_commands` | 196 | 2 | 2 | 2 | 0 | TestEdgeCases |
| `test_pipe_with_one_unknown_makes_gray` | 200 | 2 | 2 | 2 | 0 | TestEdgeCases |
| `test_pipe_whitelist_prefix_does_not_bypass_gray` | 207 | 2 | 4 | 2 | 0 | TestEdgeCases |
| `test_pipe_dangerous_after_safe_is_caught` | 214 | 2 | 4 | 2 | 0 | TestEdgeCases |
| `test_safe_terminal_not_high_risk` | 224 | 2 | 2 | 2 | 0 | TestHighRiskTool |
| `test_dangerous_terminal_is_high_risk` | 228 | 2 | 3 | 3 | 0 | TestHighRiskTool |
| `test_gray_terminal_is_high_risk` | 233 | 2 | 2 | 2 | 0 | TestHighRiskTool |
| `test_file_operations_always_high_risk` | 237 | 2 | 3 | 3 | 1 | TestHighRiskTool |
| `test_shell_exec_is_always_high_risk` | 242 | 2 | 2 | 2 | 0 | TestHighRiskTool |

**导入:**
- `import pytest` → pytest
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tests.mock_llm` → MockLLMCaller, text_response

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_context.py

**类:**
- `TestQueryClassification` (行 20) — 方法: test_obsidian_keyword_matches, test_notion_keyword_matches, test_code_keyword_matches, test_file_keyword_matches, test_email_keyword_matches, test_macos_keyword_matches, test_web_keyword_matches, test_english_keywords, test_unknown_query_returns_none, test_empty_input_returns_none
- `TestToolFiltering` (行 74) — 方法: test_web_query_filters_to_web_tools, test_code_query_filters_to_code_tools, test_macos_query_filters_to_macos_tools, test_obsidian_query_does_not_filter, test_notion_query_does_not_filter, test_email_query_does_not_filter, test_unknown_query_returns_none
- `TestToolCategories` (行 129) — 方法: test_all_categories_have_lists, test_no_category_overlaps
- `TestHistoryCompression` (行 153) — 方法: test_no_compression_with_few_messages, test_compression_flag_is_set_during_compression, test_keep_exchanges_preserved

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `engine` | 14 | 0 | 3 | 1 | 0 | - |
| `test_obsidian_keyword_matches` | 23 | 2 | 3 | 2 | 0 | TestQueryClassification |
| `test_notion_keyword_matches` | 28 | 2 | 3 | 2 | 0 | TestQueryClassification |
| `test_code_keyword_matches` | 33 | 2 | 3 | 2 | 0 | TestQueryClassification |
| `test_file_keyword_matches` | 38 | 2 | 3 | 2 | 0 | TestQueryClassification |
| `test_email_keyword_matches` | 43 | 2 | 3 | 2 | 0 | TestQueryClassification |
| `test_macos_keyword_matches` | 48 | 2 | 3 | 2 | 0 | TestQueryClassification |
| `test_web_keyword_matches` | 53 | 2 | 3 | 2 | 0 | TestQueryClassification |
| `test_english_keywords` | 58 | 2 | 3 | 2 | 0 | TestQueryClassification |
| `test_unknown_query_returns_none` | 63 | 2 | 3 | 2 | 0 | TestQueryClassification |
| `test_empty_input_returns_none` | 68 | 2 | 3 | 2 | 0 | TestQueryClassification |
| `test_web_query_filters_to_web_tools` | 77 | 2 | 8 | 4 | 2 | TestToolFiltering |
| `test_code_query_filters_to_code_tools` | 87 | 2 | 11 | 4 | 2 | TestToolFiltering |
| `test_macos_query_filters_to_macos_tools` | 100 | 2 | 5 | 3 | 2 | TestToolFiltering |
| `test_obsidian_query_does_not_filter` | 107 | 2 | 3 | 2 | 0 | TestToolFiltering |
| `test_notion_query_does_not_filter` | 113 | 2 | 3 | 2 | 0 | TestToolFiltering |
| `test_email_query_does_not_filter` | 118 | 2 | 3 | 2 | 0 | TestToolFiltering |
| `test_unknown_query_returns_none` | 123 | 2 | 3 | 2 | 0 | TestToolFiltering |
| `test_all_categories_have_lists` | 132 | 1 | 4 | 4 | 1 | TestToolCategories |
| `test_no_category_overlaps` | 138 | 1 | 9 | 4 | 1 | TestToolCategories |
| `test_no_compression_with_few_messages` | 156 | 2 | 7 | 2 | 0 | TestHistoryCompression |
| `test_compression_flag_is_set_during_compression` | 166 | 2 | 6 | 3 | 1 | TestHistoryCompression |
| `test_keep_exchanges_preserved` | 177 | 2 | 8 | 3 | 1 | TestHistoryCompression |

**导入:**
- `import os` → os
- `import sys` → sys
- `import pytest` → pytest
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tests.mock_llm` → MockLLMCaller, text_response
- `from core.context` → ContextMixin
- `from core.context` → ContextMixin
- `from collections` → Counter

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_engine_core.py

**类:**
- `TestEngineBasicFlow` (行 15) — 方法: test_simple_text_response, test_tool_call_then_text, test_max_steps_termination, test_history_preserved_across_multiple_runs, test_reset_clears_history
- `TestTeachingMode` (行 68) — 方法: test_enter_teaching_mode, test_cancel_teaching_mode, test_save_skill_without_name, test_save_skill_with_name
- `TestUndoCheckpoint` (行 112) — 方法: test_save_checkpoint_adds_to_list, test_checkpoint_stores_history, test_max_checkpoints_limit, test_find_checkpoint_by_label, test_find_checkpoint_by_number, test_find_checkpoint_not_found, test_do_undo_restores_history, test_do_undo_with_no_checkpoints
- `TestMessageRecording` (行 174) — 方法: test_record_user_message, test_record_tool_call, test_no_recording_when_not_teaching
- `TestHandlers` (行 197) — 方法: test_restore_checkpoint_list_empty
- `TestStateTransitions` (行 205) — 方法: test_initial_state_is_idle, test_after_reset_state_is_idle, test_run_sets_to_done

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `test_simple_text_response` | 18 | 1 | 6 | 4 | 1 | TestEngineBasicFlow |
| `test_tool_call_then_text` | 26 | 1 | 9 | 3 | 0 | TestEngineBasicFlow |
| `test_max_steps_termination` | 38 | 1 | 8 | 3 | 1 | TestEngineBasicFlow |
| `test_history_preserved_across_multiple_runs` | 48 | 1 | 8 | 2 | 0 | TestEngineBasicFlow |
| `test_reset_clears_history` | 59 | 1 | 6 | 3 | 0 | TestEngineBasicFlow |
| `test_enter_teaching_mode` | 71 | 2 | 4 | 4 | 0 | TestTeachingMode |
| `test_cancel_teaching_mode` | 77 | 2 | 6 | 4 | 0 | TestTeachingMode |
| `test_save_skill_without_name` | 85 | 2 | 5 | 3 | 0 | TestTeachingMode |
| `test_save_skill_with_name` | 92 | 4 | 12 | 4 | 0 | TestTeachingMode |
| `test_save_checkpoint_adds_to_list` | 115 | 2 | 3 | 2 | 0 | TestUndoCheckpoint |
| `test_checkpoint_stores_history` | 120 | 2 | 9 | 4 | 0 | TestUndoCheckpoint |
| `test_max_checkpoints_limit` | 131 | 2 | 3 | 3 | 1 | TestUndoCheckpoint |
| `test_find_checkpoint_by_label` | 136 | 2 | 3 | 2 | 0 | TestUndoCheckpoint |
| `test_find_checkpoint_by_number` | 141 | 2 | 5 | 2 | 0 | TestUndoCheckpoint |
| `test_find_checkpoint_not_found` | 149 | 2 | 2 | 2 | 0 | TestUndoCheckpoint |
| `test_do_undo_restores_history` | 153 | 2 | 11 | 3 | 0 | TestUndoCheckpoint |
| `test_do_undo_with_no_checkpoints` | 169 | 2 | 2 | 2 | 0 | TestUndoCheckpoint |
| `test_record_user_message` | 177 | 2 | 5 | 4 | 0 | TestMessageRecording |
| `test_record_tool_call` | 184 | 2 | 5 | 3 | 0 | TestMessageRecording |
| `test_no_recording_when_not_teaching` | 191 | 2 | 3 | 2 | 0 | TestMessageRecording |
| `test_restore_checkpoint_list_empty` | 200 | 2 | 2 | 2 | 0 | TestHandlers |
| `test_initial_state_is_idle` | 208 | 2 | 1 | 2 | 0 | TestStateTransitions |
| `test_after_reset_state_is_idle` | 211 | 2 | 3 | 2 | 0 | TestStateTransitions |
| `test_run_sets_to_done` | 216 | 2 | 4 | 2 | 0 | TestStateTransitions |

**导入:**
- `import os` → os
- `import sys` → sys
- `import json` → json
- `import pytest` → pytest
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tests.mock_llm` → MockLLMCaller, text_response, tool_response

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_llm_caller.py

**类:**
- `TestHTTPStatusCodeClassification` (行 13) — 方法: test_200_is_not_an_error, test_401_auth_error_not_retryable, test_403_permission_error_not_retryable, test_429_rate_limit_is_retryable, test_500_server_error_is_retryable, test_502_bad_gateway_is_retryable, test_503_service_unavailable_is_retryable, test_504_gateway_timeout_is_retryable, test_400_bad_request_not_retryable, test_404_not_found_not_retryable, test_422_unprocessable_not_retryable
- `TestExceptionClassification` (行 73) — 方法: test_timeout_is_retryable, test_connection_error_is_retryable, test_http_error_is_retryable, test_json_decode_error_not_retryable, test_value_error_not_retryable, test_generic_exception_not_retryable
- `TestPriorityOrder` (行 113) — 方法: test_exception_wins_over_status
- `TestMessageContent` (行 122) — 方法: test_all_messages_are_non_empty, test_all_exception_messages_are_non_empty

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `test_200_is_not_an_error` | 16 | 1 | 1 | 1 | 0 | TestHTTPStatusCodeClassification |
| `test_401_auth_error_not_retryable` | 21 | 1 | 4 | 5 | 0 | TestHTTPStatusCodeClassification |
| `test_403_permission_error_not_retryable` | 27 | 1 | 3 | 3 | 0 | TestHTTPStatusCodeClassification |
| `test_429_rate_limit_is_retryable` | 32 | 1 | 3 | 3 | 0 | TestHTTPStatusCodeClassification |
| `test_500_server_error_is_retryable` | 37 | 1 | 3 | 3 | 0 | TestHTTPStatusCodeClassification |
| `test_502_bad_gateway_is_retryable` | 42 | 1 | 3 | 3 | 0 | TestHTTPStatusCodeClassification |
| `test_503_service_unavailable_is_retryable` | 47 | 1 | 3 | 3 | 0 | TestHTTPStatusCodeClassification |
| `test_504_gateway_timeout_is_retryable` | 52 | 1 | 3 | 3 | 0 | TestHTTPStatusCodeClassification |
| `test_400_bad_request_not_retryable` | 57 | 1 | 3 | 3 | 0 | TestHTTPStatusCodeClassification |
| `test_404_not_found_not_retryable` | 62 | 1 | 3 | 3 | 0 | TestHTTPStatusCodeClassification |
| `test_422_unprocessable_not_retryable` | 67 | 1 | 3 | 3 | 0 | TestHTTPStatusCodeClassification |
| `test_timeout_is_retryable` | 76 | 1 | 4 | 3 | 0 | TestExceptionClassification |
| `test_connection_error_is_retryable` | 82 | 1 | 4 | 3 | 0 | TestExceptionClassification |
| `test_http_error_is_retryable` | 88 | 1 | 4 | 3 | 0 | TestExceptionClassification |
| `test_json_decode_error_not_retryable` | 94 | 1 | 4 | 3 | 0 | TestExceptionClassification |
| `test_value_error_not_retryable` | 100 | 1 | 4 | 3 | 0 | TestExceptionClassification |
| `test_generic_exception_not_retryable` | 106 | 1 | 4 | 3 | 0 | TestExceptionClassification |
| `test_exception_wins_over_status` | 116 | 1 | 3 | 2 | 0 | TestPriorityOrder |
| `test_all_messages_are_non_empty` | 125 | 1 | 3 | 3 | 1 | TestMessageContent |
| `test_all_exception_messages_are_non_empty` | 130 | 1 | 10 | 3 | 1 | TestMessageContent |

**导入:**
- `import pytest` → pytest
- `import requests` → requests
- `import json` → json
- `from core.llm_caller` → _classify_error

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_mock_engine.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `test_simple_text_response` | 11 | 0 | 7 | 3 | 1 | - |
| `test_tool_call_then_text` | 21 | 0 | 9 | 2 | 0 | - |
| `test_max_steps_termination` | 33 | 0 | 10 | 3 | 1 | - |
| `test_context_compression` | 46 | 0 | 10 | 1 | 0 | - |
| `test_tool_failure_loop_breaker` | 59 | 0 | 9 | 1 | 0 | - |

**导入:**
- `import sys` → sys
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tests.mock_llm` → MockLLMCaller, text_response, tool_response

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_p0_fixes.py

**类:**
- `TestCodeExecutionSelfRepair` (行 11) — 方法: test_llm_caller_injected_via_tool_runner, test_code_execution_accepts_llm_caller_param, test_code_execution_llm_caller_takes_priority
- `TestUnifiedSafetyPatterns` (行 63) — 方法: test_command_substitution_blocked_by_engine, test_execute_terminal_also_blocks_command_substitution, test_dangerous_patterns_are_consistent_between_layers
- `TestToolResultDisplay` (行 115) — 方法: test_tool_result_notification_has_result_field, test_tool_complete_event_includes_result_text, test_long_result_not_truncated_too_early, test_successful_tool_has_empty_error
- `TestToolRegistryP0` (行 188) — 方法: test_code_execution_registered, test_grep_code_registered, test_edit_file_registered, test_run_tests_registered, test_all_code_tools_registered

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `test_llm_caller_injected_via_tool_runner` | 14 | 1 | 15 | 3 | 0 | TestCodeExecutionSelfRepair |
| `test_code_execution_accepts_llm_caller_param` | 35 | 1 | 9 | 3 | 0 | TestCodeExecutionSelfRepair |
| `test_code_execution_llm_caller_takes_priority` | 48 | 1 | 10 | 3 | 0 | TestCodeExecutionSelfRepair |
| `test_command_substitution_blocked_by_engine` | 66 | 1 | 10 | 3 | 0 | TestUnifiedSafetyPatterns |
| `test_execute_terminal_also_blocks_command_substitution` | 82 | 1 | 5 | 4 | 0 | TestUnifiedSafetyPatterns |
| `test_dangerous_patterns_are_consistent_between_layers` | 91 | 1 | 19 | 4 | 1 | TestUnifiedSafetyPatterns |
| `test_tool_result_notification_has_result_field` | 118 | 1 | 19 | 5 | 1 | TestToolResultDisplay |
| `test_tool_complete_event_includes_result_text` | 144 | 1 | 19 | 4 | 0 | TestToolResultDisplay |
| `test_long_result_not_truncated_too_early` | 167 | 1 | 4 | 2 | 0 | TestToolResultDisplay |
| `test_successful_tool_has_empty_error` | 175 | 1 | 10 | 3 | 0 | TestToolResultDisplay |
| `test_code_execution_registered` | 191 | 1 | 3 | 3 | 0 | TestToolRegistryP0 |
| `test_grep_code_registered` | 196 | 1 | 3 | 3 | 0 | TestToolRegistryP0 |
| `test_edit_file_registered` | 201 | 1 | 3 | 3 | 0 | TestToolRegistryP0 |
| `test_run_tests_registered` | 206 | 1 | 3 | 3 | 0 | TestToolRegistryP0 |
| `test_all_code_tools_registered` | 211 | 1 | 14 | 3 | 1 | TestToolRegistryP0 |

**导入:**
- `import os` → os
- `import sys` → sys
- `import json` → json
- `import pytest` → pytest
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tests.mock_llm` → MockLLMCaller, text_response, tool_response
- `from tools.code_execution` → execute
- `from tools.code_execution` → execute
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tests.mock_llm` → MockLLMCaller, text_response
- `from tools.execute_terminal` → is_dangerous
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tests.mock_llm` → MockLLMCaller, text_response
- `from tools.execute_terminal` → is_dangerous
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tests.mock_llm` → MockLLMCaller, text_response, tool_response
- `from tools` → TOOL_FUNCTIONS
- `from tools` → TOOL_FUNCTIONS
- `from tools` → TOOL_FUNCTIONS
- `from tools` → TOOL_FUNCTIONS
- `from tools` → TOOL_FUNCTIONS, TOOLS_SCHEMA

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_provider.py

**类:**
- `TestGetProvider` (行 8) — 方法: test_known_provider_deepseek, test_known_provider_openai, test_known_provider_anthropic, test_known_provider_ollama, test_unknown_provider_returns_none, test_case_insensitive
- `TestListProviders` (行 44) — 方法: test_returns_all_known_providers, test_returns_list
- `TestResolveProvider` (行 62) — 方法: test_defaults_to_deepseek, test_explicit_name_overrides_env, test_env_var_selection, test_model_env_override, test_base_url_env_override, test_api_key_from_env, test_fallback_to_deepseek_on_unknown, test_custom_provider_prefix, test_context_length_included, test_ollama_no_api_key_needed, test_google_provider

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `test_known_provider_deepseek` | 11 | 1 | 5 | 5 | 0 | TestGetProvider |
| `test_known_provider_openai` | 18 | 1 | 4 | 4 | 0 | TestGetProvider |
| `test_known_provider_anthropic` | 24 | 1 | 4 | 4 | 1 | TestGetProvider |
| `test_known_provider_ollama` | 30 | 1 | 4 | 4 | 0 | TestGetProvider |
| `test_unknown_provider_returns_none` | 36 | 1 | 1 | 2 | 0 | TestGetProvider |
| `test_case_insensitive` | 39 | 1 | 1 | 2 | 0 | TestGetProvider |
| `test_returns_all_known_providers` | 47 | 1 | 9 | 9 | 0 | TestListProviders |
| `test_returns_list` | 58 | 1 | 1 | 2 | 0 | TestListProviders |
| `test_defaults_to_deepseek` | 65 | 2 | 9 | 5 | 0 | TestResolveProvider |
| `test_explicit_name_overrides_env` | 78 | 2 | 3 | 2 | 0 | TestResolveProvider |
| `test_env_var_selection` | 83 | 2 | 5 | 3 | 0 | TestResolveProvider |
| `test_model_env_override` | 90 | 2 | 5 | 2 | 0 | TestResolveProvider |
| `test_base_url_env_override` | 97 | 2 | 3 | 2 | 0 | TestResolveProvider |
| `test_api_key_from_env` | 102 | 2 | 3 | 2 | 0 | TestResolveProvider |
| `test_fallback_to_deepseek_on_unknown` | 107 | 2 | 3 | 2 | 0 | TestResolveProvider |
| `test_custom_provider_prefix` | 112 | 2 | 6 | 2 | 0 | TestResolveProvider |
| `test_context_length_included` | 120 | 1 | 3 | 3 | 0 | TestResolveProvider |
| `test_ollama_no_api_key_needed` | 125 | 2 | 3 | 2 | 0 | TestResolveProvider |
| `test_google_provider` | 130 | 2 | 6 | 4 | 0 | TestResolveProvider |

**导入:**
- `import os` → os
- `import pytest` → pytest
- `from core.provider` → get_provider, list_providers, resolve_provider, PROVIDERS

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_secret_redaction.py

**类:**
- `TestRedactionPatterns` (行 19) — 方法: test_deepseek_key, test_anthropic_key, test_github_pat_ghp, test_github_pat_gho, test_github_pat_ghs, test_github_pat_ghu, test_github_pat_ghf, test_aws_access_key, test_private_key_block, test_private_key_dsa, test_private_key_openssh, test_env_var_style_snake_case, test_env_var_style_secret, test_env_var_style_password, test_bearer_token, test_password_colon_style, test_pwd_equals_style, test_multiple_secrets_in_one_string
- `TestNoFalsePositives` (行 106) — 方法: test_normal_text_passes_through, test_code_snippet_not_redacted, test_short_values_not_falsely_redacted, test_partial_match_not_overly_greedy

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `engine` | 13 | 0 | 3 | 1 | 0 | - |
| `test_deepseek_key` | 22 | 2 | 3 | 3 | 0 | TestRedactionPatterns |
| `test_anthropic_key` | 27 | 2 | 3 | 3 | 0 | TestRedactionPatterns |
| `test_github_pat_ghp` | 32 | 2 | 3 | 3 | 0 | TestRedactionPatterns |
| `test_github_pat_gho` | 37 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_github_pat_ghs` | 41 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_github_pat_ghu` | 45 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_github_pat_ghf` | 49 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_aws_access_key` | 53 | 2 | 3 | 3 | 0 | TestRedactionPatterns |
| `test_private_key_block` | 58 | 2 | 5 | 2 | 0 | TestRedactionPatterns |
| `test_private_key_dsa` | 65 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_private_key_openssh` | 69 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_env_var_style_snake_case` | 73 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_env_var_style_secret` | 77 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_env_var_style_password` | 81 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_bearer_token` | 85 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_password_colon_style` | 89 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_pwd_equals_style` | 93 | 2 | 2 | 2 | 0 | TestRedactionPatterns |
| `test_multiple_secrets_in_one_string` | 97 | 2 | 5 | 4 | 0 | TestRedactionPatterns |
| `test_normal_text_passes_through` | 109 | 2 | 2 | 2 | 0 | TestNoFalsePositives |
| `test_code_snippet_not_redacted` | 113 | 2 | 9 | 3 | 0 | TestNoFalsePositives |
| `test_short_values_not_falsely_redacted` | 124 | 2 | 3 | 2 | 0 | TestNoFalsePositives |
| `test_partial_match_not_overly_greedy` | 130 | 2 | 3 | 2 | 0 | TestNoFalsePositives |

**导入:**
- `import pytest` → pytest
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `from tests.mock_llm` → MockLLMCaller, text_response

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_session_manager.py

**类:**
- `TestSessionCreation` (行 25) — 方法: test_new_session_creates_id, test_new_session_creates_file, test_new_session_has_correct_structure, test_new_session_adds_join_message, test_current_session_id_is_set, test_title_set_from_first_user_message, test_default_title_when_no_title_given
- `TestSessionList` (行 76) — 方法: test_list_empty_when_no_sessions, test_list_returns_recent_sessions, test_list_respects_limit, test_list_sorted_most_recent_first
- `TestSessionLoadResume` (行 107) — 方法: test_load_existing_session, test_load_nonexistent_returns_none, test_resume_sets_current_session
- `TestAddMessage` (行 130) — 方法: test_add_user_message, test_add_assistant_message, test_add_system_message, test_message_has_timestamp, test_message_has_author, test_get_message_count_no_session
- `TestSessionRename` (行 170) — 方法: test_rename_session, test_rename_truncates_long_titles
- `TestSessionDelete` (行 185) — 方法: test_delete_removes_session_from_disk
- `TestSessionReload` (行 203) — 方法: test_reload_reflects_disk_changes
- `TestAtomicWrite` (行 220) — 方法: test_atomic_write_does_not_corrupt_on_crash_simulation

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `session_dir` | 13 | 0 | 3 | 1 | 1 | - |
| `mgr` | 20 | 1 | 2 | 1 | 0 | - |
| `test_new_session_creates_id` | 28 | 2 | 4 | 4 | 0 | TestSessionCreation |
| `test_new_session_creates_file` | 35 | 2 | 3 | 2 | 0 | TestSessionCreation |
| `test_new_session_has_correct_structure` | 40 | 2 | 8 | 5 | 1 | TestSessionCreation |
| `test_new_session_adds_join_message` | 50 | 2 | 8 | 5 | 1 | TestSessionCreation |
| `test_current_session_id_is_set` | 60 | 2 | 2 | 2 | 0 | TestSessionCreation |
| `test_title_set_from_first_user_message` | 64 | 2 | 4 | 3 | 0 | TestSessionCreation |
| `test_default_title_when_no_title_given` | 71 | 2 | 2 | 2 | 0 | TestSessionCreation |
| `test_list_empty_when_no_sessions` | 79 | 2 | 2 | 2 | 0 | TestSessionList |
| `test_list_returns_recent_sessions` | 83 | 2 | 6 | 2 | 0 | TestSessionList |
| `test_list_respects_limit` | 91 | 2 | 4 | 3 | 1 | TestSessionList |
| `test_list_sorted_most_recent_first` | 97 | 2 | 6 | 2 | 0 | TestSessionList |
| `test_load_existing_session` | 110 | 2 | 6 | 4 | 0 | TestSessionLoadResume |
| `test_load_nonexistent_returns_none` | 119 | 2 | 2 | 2 | 0 | TestSessionLoadResume |
| `test_resume_sets_current_session` | 123 | 2 | 4 | 2 | 0 | TestSessionLoadResume |
| `test_add_user_message` | 133 | 2 | 3 | 2 | 0 | TestAddMessage |
| `test_add_assistant_message` | 138 | 2 | 4 | 2 | 0 | TestAddMessage |
| `test_add_system_message` | 144 | 2 | 4 | 2 | 1 | TestAddMessage |
| `test_message_has_timestamp` | 150 | 2 | 6 | 4 | 1 | TestAddMessage |
| `test_message_has_author` | 158 | 2 | 5 | 3 | 1 | TestAddMessage |
| `test_get_message_count_no_session` | 165 | 1 | 2 | 2 | 0 | TestAddMessage |
| `test_rename_session` | 173 | 2 | 3 | 2 | 0 | TestSessionRename |
| `test_rename_truncates_long_titles` | 178 | 2 | 4 | 2 | 0 | TestSessionRename |
| `test_delete_removes_session_from_disk` | 188 | 2 | 9 | 5 | 1 | TestSessionDelete |
| `test_reload_reflects_disk_changes` | 206 | 2 | 9 | 2 | 1 | TestSessionReload |
| `test_atomic_write_does_not_corrupt_on_crash_simulation` | 223 | 2 | 7 | 4 | 0 | TestAtomicWrite |

**导入:**
- `import os` → os
- `import json` → json
- `import tempfile` → tempfile
- `from pathlib` → Path
- `import pytest` → pytest
- `from core.session_manager` → SessionManager
- `import time` → time
- `import time` → time
- `import time` → time

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tests/test_tool_registry.py

**类:**
- `TestToolRegistry` (行 12) — 方法: test_tools_schema_is_list, test_tools_schema_not_empty, test_tool_functions_dict_populated, test_all_schemas_have_required_fields, test_no_duplicate_tool_names, test_core_tools_present, test_obsidian_tools_registered, test_github_tools_registered, test_macos_tools_registered, test_register_tool_adds_to_both_dict_and_schema, test_tool_checks_are_registered, test_each_registered_function_is_callable
- `TestToolGating` (行 165) — 方法: test_gating_skips_unavailable_tools

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `test_tools_schema_is_list` | 15 | 1 | 2 | 2 | 0 | TestToolRegistry |
| `test_tools_schema_not_empty` | 19 | 1 | 2 | 2 | 0 | TestToolRegistry |
| `test_tool_functions_dict_populated` | 23 | 1 | 3 | 3 | 0 | TestToolRegistry |
| `test_all_schemas_have_required_fields` | 28 | 1 | 10 | 7 | 1 | TestToolRegistry |
| `test_no_duplicate_tool_names` | 40 | 1 | 7 | 4 | 1 | TestToolRegistry |
| `test_core_tools_present` | 49 | 1 | 30 | 4 | 1 | TestToolRegistry |
| `test_obsidian_tools_registered` | 82 | 1 | 13 | 4 | 1 | TestToolRegistry |
| `test_github_tools_registered` | 98 | 1 | 12 | 4 | 1 | TestToolRegistry |
| `test_macos_tools_registered` | 113 | 1 | 12 | 4 | 1 | TestToolRegistry |
| `test_register_tool_adds_to_both_dict_and_schema` | 128 | 1 | 14 | 2 | 0 | TestToolRegistry |
| `test_tool_checks_are_registered` | 153 | 1 | 2 | 2 | 0 | TestToolRegistry |
| `test_each_registered_function_is_callable` | 157 | 1 | 5 | 4 | 2 | TestToolRegistry |
| `test_gating_skips_unavailable_tools` | 168 | 2 | 4 | 3 | 1 | TestToolGating |

**导入:**
- `import os` → os
- `import sys` → sys
- `import json` → json
- `import pytest` → pytest
- `from tools` → TOOLS_SCHEMA
- `from tools` → TOOLS_SCHEMA
- `from tools` → TOOL_FUNCTIONS
- `from tools` → TOOLS_SCHEMA
- `from tools` → TOOLS_SCHEMA
- `from tools` → TOOLS_SCHEMA
- `from tools` → TOOLS_SCHEMA
- `from tools` → TOOLS_SCHEMA
- `from tools` → TOOLS_SCHEMA
- `from tools` → register_tool, TOOL_FUNCTIONS, TOOLS_SCHEMA
- `from tools` → TOOL_CHECKS
- `from tools` → TOOL_FUNCTIONS
- `from tools` → TOOL_CHECKS

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/__init__.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `register_tool` | 12 | 4 | 4 | 2 | 1 | - |
| `discover_tools` | 18 | 0 | 16 | 8 | 4 | - |

**导入:**
- `import sys` → sys
- `import importlib.util` → importlib.util
- `import re` → re
- `from pathlib` → Path
- `from core.skill_manager` → get_skill_manager

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/analyze_emails.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 21 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from email_module` → EmailModule

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/api_call.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 10 | 4 | 60 | 24 | 5 | - |
| `_list_apis` | 89 | 0 | 8 | 3 | 1 | - |
| `register` | 122 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import json` → json
- `import os` → os
- `import requests` → requests

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/api_register.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 9 | 5 | 32 | 7 | 2 | - |
| `register` | 94 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import json` → json
- `import os` → os

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/append_obsidian.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 2 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from file_writer` → append_obsidian

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/batch_copy_notes.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 9 | 2 | 29 | 8 | 2 | - |
| `register` | 62 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import shutil` → shutil

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/batch_delete_notes.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 13 | 3 | 2 | - |
| `register` | 33 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → delete_note

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/batch_move_notes.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 6 | 2 | 15 | 4 | 2 | - |
| `register` | 45 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → move_note

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_config.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 9 | 3 | 53 | 16 | 5 | - |
| `register` | 87 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re
- `from core.provider` → resolve_provider

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/bobo_schedule.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_load_schedules` | 11 | 0 | 7 | 3 | 2 | - |
| `_save_schedules` | 21 | 1 | 3 | 1 | 1 | - |
| `_install_cron` | 27 | 2 | 28 | 8 | 3 | - |
| `_remove_cron` | 59 | 1 | 20 | 8 | 3 | - |
| `_cron_expr` | 82 | 2 | 11 | 6 | 3 | - |
| `execute` | 96 | 5 | 55 | 13 | 2 | - |
| `register` | 195 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import json` → json
- `import os` → os
- `import subprocess` → subprocess
- `import sys` → sys

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/browser.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `open_url` | 10 | 1 | 6 | 2 | 1 | - |
| `get_page_title` | 19 | 2 | 12 | 3 | 1 | - |
| `register` | 34 | 1 | 32 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess
- `import time` → time
- `from typing` → Optional
- `import requests` → requests
- `from bs4` → BeautifulSoup

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/classify_note.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `analyze` | 31 | 2 | 27 | 7 | 2 | - |
| `confirm_move` | 68 | 2 | 17 | 4 | 2 | - |
| `register` | 93 | 1 | 22 | 1 | 0 | - |

**导入:**
- `import re` → re
- `from tools.read_obsidian` → read_note
- `from tools.move_note` → move_note
- `import re` → re

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/clipboard.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `read` | 7 | 0 | 6 | 3 | 1 | - |
| `write` | 15 | 1 | 7 | 2 | 1 | - |
| `register` | 26 | 1 | 16 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_execution.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_ensure_projects_dir` | 20 | 0 | 2 | 1 | 0 | - |
| `_save_code` | 25 | 4 | 20 | 2 | 1 | - |
| `_save_run_log` | 53 | 3 | 6 | 1 | 1 | - |
| `_build_fix_prompt` | 62 | 3 | 17 | 1 | 0 | - |
| `_build_test_prompt` | 82 | 2 | 15 | 1 | 0 | - |
| `_check_syntax` | 100 | 2 | 42 | 10 | 3 | - |
| `_call_llm_for_fix` | 148 | 4 | 18 | 6 | 2 | - |
| `_call_llm_for_test` | 171 | 3 | 18 | 6 | 2 | - |
| `_run_test_file` | 194 | 2 | 35 | 11 | 3 | - |
| `execute` | 232 | 3 | 16 | 3 | 2 | - |
| `_is_error_result` | 253 | 1 | 9 | 3 | 2 | - |
| `_run_code` | 265 | 2 | 12 | 6 | 5 | - |
| `_run_python` | 282 | 1 | 34 | 10 | 3 | - |
| `_run_javascript` | 319 | 1 | 36 | 11 | 3 | - |
| `_run_bash` | 358 | 1 | 35 | 10 | 3 | - |
| `_run_go` | 396 | 1 | 33 | 11 | 3 | - |
| `_run_rust` | 432 | 1 | 43 | 13 | 4 | - |
| `_lint_code` | 479 | 2 | 12 | 5 | 2 | - |
| `register` | 513 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess
- `import tempfile` → tempfile
- `import os` → os
- `import time` → time
- `from pathlib` → Path
- `from core.file_safety` → sanitize_env
- `from config` → _CONFIG_PROJECTS_DIR
- `import re` → re
- `import re` → re
- `import ast` → ast
- `import ast` → ast

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/code_to_obsidian.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_sanitize_filename` | 18 | 1 | 4 | 1 | 0 | - |
| `execute` | 25 | 5 | 46 | 6 | 1 | - |
| `register` | 126 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re
- `from datetime` → datetime
- `from pathlib` → Path
- `from tools.wiki_rebuild` → rebuild

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/copy_to_notion.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 8 | 2 | 28 | 11 | 3 | - |
| `register` | 66 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `from tools.notion_create_page` → notion_create

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/copy_to_obsidian.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 8 | 2 | 13 | 6 | 1 | - |
| `register` | 48 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `from tools.notion_read_page` → notion_read
- `from tools.file_writer` → write_obsidian

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/crawler.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_cache_get` | 19 | 1 | 4 | 3 | 1 | - |
| `_cache_set` | 26 | 3 | 5 | 3 | 2 | - |
| `web_search` | 39 | 2 | 29 | 8 | 4 | - |
| `_search_lite` | 74 | 2 | 21 | 7 | 3 | - |
| `_fetch_page` | 103 | 1 | 44 | 12 | 4 | - |
| `web_fetch` | 152 | 1 | 5 | 2 | 1 | - |
| `web_fetch_markdown` | 160 | 1 | 7 | 3 | 1 | - |
| `_extract_domain` | 170 | 1 | 2 | 2 | 0 | - |
| `_clean_text` | 175 | 2 | 5 | 3 | 1 | - |
| `register` | 183 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import re` → re
- `import time` → time
- `import requests` → requests
- `from bs4` → BeautifulSoup
- `from ddgs` → DDGS

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/create_calendar_event.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 9 | 3 | 14 | 4 | 2 | - |
| `register` | 45 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess
- `import shlex` → shlex

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/create_folder.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 21 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → create_folder

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/cross_project_search.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 34 | 4 | 81 | 25 | 8 | - |
| `register` | 169 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re
- `from pathlib` → Path
- `from typing` → Optional
- `from collections` → defaultdict

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/cross_search.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `register` | 26 | 1 | 1 | 1 | 0 | - |

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/delete_folder.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 2 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → delete_folder

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/delete_note.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → delete_note

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/edit_file.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_backup` | 23 | 1 | 12 | 3 | 1 | - |
| `_find_similar_lines` | 38 | 3 | 33 | 11 | 4 | - |
| `execute` | 81 | 3 | 70 | 16 | 4 | - |
| `register` | 171 | 1 | 29 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import time` → time
- `from pathlib` → Path
- `from core.file_safety` → is_write_denied
- `import re` → re

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/email_module.py

**类:**
- `EmailModule` (行 16) — 方法: __init__, _load_config, _connect_imap, read_recent, read_email_content, search_emails, analyze_recent, health_check

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `__init__` | 17 | 1 | 2 | 1 | 0 | EmailModule |
| `_load_config` | 21 | 1 | 8 | 3 | 2 | EmailModule |
| `_connect_imap` | 31 | 1 | 5 | 2 | 1 | EmailModule |
| `read_recent` | 38 | 2 | 41 | 8 | 4 | EmailModule |
| `read_email_content` | 82 | 2 | 58 | 11 | 5 | EmailModule |
| `search_emails` | 143 | 3 | 44 | 8 | 4 | EmailModule |
| `analyze_recent` | 190 | 2 | 48 | 10 | 4 | EmailModule |
| `health_check` | 241 | 1 | 10 | 3 | 1 | EmailModule |
| `read_recent_tool` | 255 | 1 | 2 | 1 | 0 | - |
| `read_email_content_tool` | 260 | 1 | 2 | 1 | 0 | - |
| `search_emails_tool` | 265 | 1 | 2 | 1 | 0 | - |
| `analyze_emails_tool` | 270 | 1 | 2 | 1 | 0 | - |
| `is_sensitive_email` | 297 | 1 | 12 | 5 | 2 | - |
| `process_emails_with_privacy` | 317 | 1 | 30 | 9 | 5 | - |
| `register` | 353 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import json` → json
- `import imaplib` → imaplib
- `import email` → email
- `from email.header` → decode_header
- `import os` → os
- `import re` → re
- `from collections` → Counter
- `from datetime` → datetime, timedelta

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/execute_terminal.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `is_dangerous` | 35 | 1 | 10 | 6 | 2 | - |
| `execute` | 54 | 2 | 54 | 15 | 3 | - |
| `register` | 138 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess
- `import shlex` → shlex
- `import re` → re
- `import os` → os
- `from core.file_safety` → sanitize_env

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_operation.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_backup` | 19 | 1 | 11 | 3 | 1 | - |
| `_get_file_hash` | 32 | 1 | 6 | 2 | 2 | - |
| `_write_single_file` | 40 | 2 | 13 | 3 | 2 | - |
| `execute` | 55 | 4 | 63 | 19 | 5 | - |
| `register` | 150 | 1 | 1 | 1 | 0 | - |
| `clear_cache` | 153 | 0 | 2 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import hashlib` → hashlib
- `import shutil` → shutil
- `import time` → time
- `from pathlib` → Path
- `from core.file_safety` → is_write_denied, safe_read_check

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/file_writer.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_ensure_dir` | 19 | 1 | 6 | 3 | 1 | - |
| `_create_backup` | 28 | 1 | 13 | 3 | 1 | - |
| `write_obsidian` | 51 | 3 | 43 | 11 | 3 | - |
| `append_obsidian` | 99 | 3 | 58 | 18 | 3 | - |
| `read_file` | 160 | 1 | 12 | 3 | 2 | - |
| `register` | 220 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import shutil` → shutil
- `import time` → time
- `from datetime` → datetime
- `from typing` → Optional
- `from config` → OBSIDIAN_VAULT, BOBO_FOLDER, BLOCKED_FOLDERS
- `from obsidian_tools` → _normalize_path

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/get_current_time.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 7 | 1 | 9 | 4 | 3 | - |
| `register` | 29 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from datetime` → datetime

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/git_status.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 8 | 1 | 34 | 13 | 3 | - |
| `register` | 68 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess
- `import os` → os

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_check_auth.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 7 | 0 | 22 | 5 | 2 | - |
| `register` | 42 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_create_pr.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 7 | 3 | 15 | 6 | 2 | - |
| `register` | 43 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_create_repo.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 8 | 3 | 20 | 7 | 2 | - |
| `register` | 49 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess
- `import os` → os

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_pr_comment.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 8 | 5 | 22 | 7 | 2 | - |
| `register` | 53 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess
- `import json` → json

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_pr_diff.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 7 | 2 | 20 | 10 | 3 | - |
| `register` | 47 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/github_setup.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 8 | 1 | 46 | 10 | 3 | - |
| `register` | 81 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import subprocess` → subprocess
- `import re` → re

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/grep_code.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_search_python` | 24 | 4 | 40 | 15 | 4 | - |
| `_search_ripgrep` | 69 | 4 | 59 | 17 | 4 | - |
| `execute` | 132 | 4 | 52 | 18 | 2 | - |
| `register` | 200 | 1 | 33 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re
- `import subprocess` → subprocess
- `from pathlib` → Path

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/index_project.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_extract_summary` | 30 | 2 | 59 | 34 | 7 | - |
| `_extract_imports` | 97 | 2 | 36 | 15 | 8 | - |
| `_extract_python` | 138 | 1 | 19 | 6 | 2 | - |
| `_extract_javascript` | 160 | 1 | 24 | 7 | 2 | - |
| `_extract_go` | 187 | 1 | 16 | 6 | 2 | - |
| `_extract_rust` | 206 | 1 | 15 | 5 | 2 | - |
| `_extract_c` | 224 | 1 | 23 | 7 | 2 | - |
| `_extract_java` | 250 | 1 | 17 | 6 | 2 | - |
| `_extract_ruby` | 270 | 1 | 16 | 6 | 2 | - |
| `_extract_swift` | 289 | 1 | 13 | 4 | 2 | - |
| `_extract_kotlin` | 305 | 1 | 13 | 4 | 2 | - |
| `_extract_shell` | 321 | 1 | 13 | 5 | 2 | - |
| `execute` | 357 | 2 | 78 | 19 | 4 | - |
| `register` | 476 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re
- `from pathlib` → Path
- `from typing` → Optional
- `from tools.v5_memory` → save_to_knowledge_base

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/list_calendar_events.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 8 | 1 | 24 | 5 | 3 | - |
| `register` | 52 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/list_directory.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `is_sensitive_path` | 14 | 1 | 6 | 3 | 2 | - |
| `execute` | 22 | 3 | 50 | 13 | 5 | - |
| `register` | 105 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `from pathlib` → Path

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/list_folder.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 21 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → list_folder

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/move_note.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 2 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → move_note

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/move_to_folder.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 2 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → move_to_folder

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notification.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `send` | 9 | 2 | 16 | 3 | 1 | - |
| `register` | 29 | 1 | 8 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_append.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 13 | 2 | 36 | 7 | 2 | - |
| `register` | 76 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import requests` → requests

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_create_page.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 14 | 3 | 47 | 9 | 3 | - |
| `register` | 88 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import json` → json
- `import requests` → requests

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_read_page.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 13 | 1 | 51 | 10 | 5 | - |
| `_extract_block_text` | 69 | 1 | 32 | 13 | 10 | - |
| `register` | 122 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import requests` → requests

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_search.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 13 | 2 | 50 | 11 | 6 | - |
| `register` | 87 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import requests` → requests

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/notion_setup.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 9 | 1 | 34 | 8 | 3 | - |
| `register` | 70 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re
- `import requests` → requests

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/obsidian_tools.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_normalize_path` | 13 | 3 | 61 | 25 | 5 | - |
| `_is_blocked_path` | 94 | 1 | 4 | 3 | 2 | - |
| `search_obsidian_notes` | 101 | 1 | 55 | 22 | 7 | - |
| `read_obsidian_note` | 166 | 2 | 52 | 22 | 4 | - |
| `list_folder` | 233 | 1 | 34 | 15 | 3 | - |
| `write_obsidian_note` | 277 | 2 | 2 | 1 | 0 | - |
| `append_obsidian_note` | 282 | 2 | 2 | 1 | 0 | - |
| `move_note` | 287 | 2 | 18 | 7 | 1 | - |
| `_trash_file` | 314 | 1 | 13 | 3 | 1 | - |
| `_list_trash` | 330 | 0 | 10 | 4 | 2 | - |
| `_cleanup_trash` | 343 | 1 | 11 | 6 | 3 | - |
| `delete_note` | 357 | 1 | 12 | 4 | 1 | - |
| `rename_note` | 375 | 2 | 13 | 4 | 1 | - |
| `create_folder` | 394 | 1 | 8 | 3 | 1 | - |
| `delete_folder` | 407 | 2 | 14 | 5 | 2 | - |
| `move_to_folder` | 427 | 2 | 1 | 1 | 0 | - |
| `register` | 451 | 1 | 12 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re
- `import time` → time
- `import subprocess` → subprocess
- `from pathlib` → Path
- `from config` → OBSIDIAN_VAULT, BOBO_FOLDER, BLOCKED_FOLDERS
- `from file_writer` → write_obsidian
- `from file_writer` → append_obsidian
- `from list_folder` → list_folder_func, list_folder_name
- `from search_obsidian` → search_obsidian_func, search_obsidian_name
- `from read_obsidian` → read_obsidian_func, read_obsidian_name
- `from write_obsidian` → write_obsidian_func, write_obsidian_name
- `from move_note` → move_note_func, move_note_name
- `from delete_note` → delete_note_func, delete_note_name
- `import shutil` → shutil
- `import shutil` → shutil
- `import shutil` → shutil

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/open_url.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 7 | 1 | 6 | 2 | 1 | - |
| `register` | 15 | 1 | 8 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/project_info.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 8 | 3 | 16 | 4 | 2 | - |
| `_get_directory_structure` | 28 | 4 | 20 | 10 | 4 | - |
| `_get_file_list` | 51 | 1 | 9 | 7 | 3 | - |
| `_get_project_summary` | 63 | 1 | 23 | 8 | 3 | - |
| `register` | 110 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `from pathlib` → Path

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_email_content.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from email_module` → EmailModule

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_local_file.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_read_single_file` | 13 | 4 | 86 | 33 | 9 | - |
| `_read_directory` | 106 | 1 | 37 | 13 | 5 | - |
| `execute` | 153 | 4 | 19 | 5 | 2 | - |
| `register` | 194 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `from pathlib` → Path
- `from core.file_safety` → safe_read_check
- `import pypdf` → pypdf
- `import docx` → docx
- `from pptx` → Presentation
- `import openpyxl` → openpyxl

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_obsidian.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 2 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → read_obsidian_note

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/read_recent.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from email_module` → EmailModule

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/refactor.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_should_skip` | 17 | 1 | 9 | 4 | 1 | - |
| `_search_files` | 29 | 4 | 29 | 13 | 7 | - |
| `_read_file_content` | 62 | 1 | 6 | 2 | 2 | - |
| `_write_file` | 71 | 2 | 9 | 2 | 2 | - |
| `execute` | 83 | 8 | 101 | 22 | 6 | - |
| `register` | 245 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re
- `from pathlib` → Path
- `from tools.edit_file` → edit_one
- `from tools.edit_file` → _find_similar_lines

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/reminder.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_escape_applescript` | 13 | 1 | 2 | 1 | 0 | - |
| `parse_time` | 18 | 1 | 29 | 7 | 2 | - |
| `execute` | 55 | 1 | 19 | 2 | 1 | - |
| `list_reminders` | 80 | 0 | 6 | 3 | 1 | - |
| `register` | 91 | 1 | 26 | 1 | 0 | - |

**导入:**
- `import threading` → threading
- `import time` → time
- `import re` → re
- `from datetime` → datetime, timedelta
- `import subprocess` → subprocess

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/rename_note.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 2 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → rename_note

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/render.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `latex_to_unicode` | 20 | 1 | 7 | 2 | 1 | - |
| `render_markdown` | 30 | 1 | 6 | 1 | 0 | - |
| `execute` | 39 | 1 | 20 | 5 | 2 | - |
| `register` | 64 | 1 | 8 | 1 | 0 | - |
| `remove_tables` | 74 | 1 | 14 | 7 | 2 | - |
| `render_markdown` | 92 | 1 | 2 | 1 | 0 | - |

**导入:**
- `import sys` → sys
- `import time` → time
- `import re` → re

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/restore_checkpoint.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `register` | 29 | 1 | 1 | 1 | 0 | - |

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_diff.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 9 | 2 | 54 | 14 | 3 | - |
| `register` | 100 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import subprocess` → subprocess
- `import os` → os

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/review_to_obsidian.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 17 | 5 | 55 | 9 | 3 | - |
| `register` | 130 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import subprocess` → subprocess
- `from datetime` → datetime
- `from pathlib` → Path
- `from tools.wiki_rebuild` → rebuild

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/run_tests.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_detect_framework` | 22 | 1 | 21 | 10 | 3 | - |
| `_run_pytest` | 55 | 1 | 49 | 17 | 5 | - |
| `_run_jest` | 116 | 1 | 17 | 6 | 1 | - |
| `_run_go_test` | 139 | 1 | 13 | 4 | 1 | - |
| `execute` | 156 | 2 | 31 | 9 | 3 | - |
| `register` | 192 | 1 | 25 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re
- `import subprocess` → subprocess
- `from pathlib` → Path
- `import json` → json

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/save_memory.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 9 | 2 | 2 | 1 | 0 | - |
| `register` | 36 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import sys` → sys
- `import os` → os
- `from tools.v5_memory` → save_to_knowledge_base

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/save_skill.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `set_engine` | 10 | 1 | 2 | 1 | 0 | - |
| `execute` | 14 | 2 | 9 | 4 | 1 | - |
| `register` | 39 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from core.skill_manager` → get_skill_manager

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_code.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_should_skip` | 17 | 1 | 10 | 4 | 1 | - |
| `execute` | 30 | 4 | 56 | 18 | 7 | - |
| `register` | 120 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_emails.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 21 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from email_module` → EmailModule

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_memory.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 19 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from v5_memory` → search_knowledge_base

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/search_obsidian.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from obsidian_tools` → search_obsidian_notes

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/spawn_worker.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_build_worker_prompt` | 21 | 2 | 22 | 2 | 0 | - |
| `set_worker_event_emitter` | 60 | 1 | 3 | 1 | 0 | - |
| `_make_worker_callback` | 66 | 1 | 19 | 6 | 3 | - |
| `_get_llm_caller` | 88 | 0 | 15 | 2 | 1 | - |
| `_run_worker_with_timeout` | 106 | 3 | 11 | 4 | 3 | - |
| `_extract_worker_result` | 120 | 1 | 8 | 5 | 3 | - |
| `_extract_tool_log` | 131 | 1 | 27 | 12 | 4 | - |
| `execute` | 161 | 3 | 95 | 17 | 3 | - |
| `execute_read_worker_result` | 321 | 1 | 6 | 3 | 1 | - |
| `register` | 353 | 1 | 2 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import threading` → threading
- `from concurrent.futures` → ThreadPoolExecutor, TimeoutError
- `from core.llm_caller` → create_llm_caller
- `from core.provider` → resolve_provider
- `from tools` → TOOLS_SCHEMA
- `from concurrent.futures` → ThreadPoolExecutor, _FutTimeout
- `from core.engine` → Engine
- `from core.tool_executor` → execute_tool
- `import re` → _re

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/v5_memory.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `_atomic_save` | 20 | 1 | 15 | 5 | 2 | - |
| `_load` | 39 | 0 | 10 | 4 | 4 | - |
| `_get_total_chars` | 52 | 1 | 5 | 2 | 1 | - |
| `_save` | 60 | 1 | 1 | 1 | 0 | - |
| `add_entry` | 64 | 4 | 29 | 8 | 2 | - |
| `delete_entry` | 105 | 2 | 12 | 4 | 2 | - |
| `get_memory_stats` | 123 | 0 | 11 | 2 | 0 | - |
| `get_all` | 137 | 0 | 1 | 1 | 0 | - |
| `get_entries` | 141 | 0 | 1 | 1 | 0 | - |
| `get_folders` | 145 | 0 | 1 | 1 | 0 | - |
| `add_folder` | 149 | 1 | 5 | 2 | 1 | - |
| `rename_folder` | 157 | 2 | 9 | 4 | 2 | - |
| `delete_folder` | 169 | 1 | 7 | 4 | 2 | - |
| `move_to_folder` | 179 | 2 | 7 | 3 | 2 | - |
| `update_entry` | 189 | 2 | 20 | 5 | 3 | - |
| `search_knowledge_base` | 214 | 1 | 16 | 5 | 2 | - |
| `save_to_knowledge_base` | 236 | 2 | 5 | 2 | 1 | - |
| `save_user_profile` | 244 | 2 | 7 | 2 | 1 | - |
| `get_user_profile` | 254 | 0 | 3 | 1 | 0 | - |
| `format_user_profile` | 260 | 0 | 8 | 3 | 1 | - |
| `format_all_memory` | 271 | 1 | 24 | 7 | 2 | - |
| `register` | 299 | 1 | 28 | 1 | 0 | - |

**导入:**
- `import json` → json
- `import os` → os
- `import tempfile` → tempfile
- `import shutil` → shutil
- `from datetime` → datetime
- `from pathlib` → Path

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/web_extract.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 18 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from crawler` → web_fetch_markdown

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/web_fetch.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 1 | 2 | 1 | 0 | - |
| `register` | 20 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from crawler` → web_fetch

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/web_search.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 2 | 2 | 1 | 0 | - |
| `register` | 27 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from crawler` → web_search

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/wiki_rebuild.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 9 | 0 | 114 | 41 | 4 | - |
| `register` | 151 | 1 | 1 | 1 | 0 | - |

**导入:**
- `import os` → os
- `import re` → re
- `from tools.notion_search` → notion_search

### /Users/niuqingwei/Desktop/BOBO_Project_Backup/tools/write_obsidian.py

**函数:**

| 名称 | 行号 | 参数数 | 行数 | 圈复杂度 | 嵌套深度 | 所属类 |
|------|------|--------|------|----------|----------|--------|
| `execute` | 5 | 2 | 2 | 1 | 0 | - |
| `register` | 22 | 1 | 1 | 1 | 0 | - |

**导入:**
- `from file_writer` → write_obsidian
