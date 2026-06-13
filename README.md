# Bobo Agent
<img width="785" height="315" alt="截屏2026-06-05 22 58 35" src="https://github.com/user-attachments/assets/7dba3e2a-37e9-455c-92d9-44f313d85f54" />


<p align="center">
  <b>A personal AI agent that lives across your knowledge</b><br>
  Obsidian · Notion · Email · GitHub · Any API
</p>

<p align="center">
  <a href="https://github.com/Newton-666/BOBO_Project_Backup/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/status-active-brightgreen.svg" alt="Status: Active"></a>
</p>

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/Newton-666/BOBO_Project_Backup.git
cd BOBO_Project_Backup
```

### 2. Install Python dependencies

```bash
# Using venv (recommended)
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

pip install -e .
```

### 3. Configure your API key

Create `~/.bobo/.env`:

```bash
mkdir -p ~/.bobo
echo "DEEPSEEK_API_KEY=sk-your-key-here" > ~/.bobo/.env
```

### 4. Run

```bash
bobo
```

On first run, Bobo detects no API key and shows a setup screen automatically:

```
┌─────────────────────────────────────────────┐
│           ⚙ Setup Required                  │
│                                             │
│   Provider: [DeepSeek        ▾]             │
│   API Key:  [___________________________]   │
│                                             │
│   [Submit]                                  │
└─────────────────────────────────────────────┘
```

Select your provider, paste your API key, and click Submit. Bobo saves it to `~/.bobo/.env` and you're ready to chat.

> Get a DeepSeek API key at https://platform.deepseek.com/api-keys
> Or set `BOBO_PROVIDER=openai` in `~/.bobo/.env` to use OpenAI instead.

### Optional: Configure services

```bash
# Obsidian vault
echo "OBSIDIAN_VAULT=/path/to/your/vault" >> ~/.bobo/.env

# Notion — just say "connect Notion" in chat
# GitHub — just say "connect GitHub" in chat

# Email
cat > ~/.bobo/mail.json << 'EOF'
{
  "server": "imap.gmail.com",
  "port": 993,
  "username": "you@gmail.com",
  "password": "your-app-password"
}
EOF
```

### Uninstall

```bash
pip uninstall bobo-agent
rm -rf ~/.bobo ~/.bobo_v2
```

---

## What Makes Bobo Unique

### 1. Cross-Platform Knowledge

Bobo is the only agent that searches, reads, writes, and links across multiple platforms simultaneously:

```
You: "find everything about API redesign"
Bobo: cross_search("API redesign")
  → [Obsidian] Projects/API-redesign.md
  → [Notion] Q1 Planning
  → [Email] "Re: API redesign feedback"
  → "Found 5 items across 3 platforms"
```

| Tool | What it does |
|------|-------------|
| `cross_search(query)` | Search Obsidian + Notion + email at once |
| `copy_to_obsidian(page_id)` | Copy a Notion page to Obsidian as markdown |
| `copy_to_notion(filepath)` | Copy an Obsidian note to Notion |
| `wiki_rebuild()` | Auto-generate a Knowledge Hub with cross-links |

### 2. Connect Any Service Without Code

Register any REST API in one command — no Python required:

```
You: "connect my Jira"
Bobo: api_register(
        name="jira", base_url="https://company.atlassian.net/rest/api/3",
        auth_type="bearer", auth_key="xxx",
        endpoints='[{"name":"search","method":"GET","path":"/search?jql={query}"}]'
      )

You: "find my open tickets"
Bobo: api_call(api="jira", endpoint="search", params='{"query":"status=Open"}')
```

All registered APIs are automatically advertised to the LLM on every call.

### 3. Autonomous Coding

- **Auto-run**: After writing a `.py` file, Bobo runs it and reports output/errors immediately
- **Error enrichment**: Tracebacks become `[TypeError] main.py:42` — the LLM sees the problem instantly
- **Auto-diff**: Git diff is captured after every file write and injected into the next LLM call
- **Parallel execution**: Independent tools run simultaneously, not sequentially
- **GitHub integration**: Create repos, push code, open PRs, review diffs

### 4. Privacy & Security

- **Secret redaction**: API keys, tokens, passwords are replaced with `[REDACTED]` before reaching the LLM
- **Tool gating**: Tools with unmet prerequisites are invisible — no Obsidian tools if no vault configured
- **Blocked folders**: `Private/`, `Archive/` folders are never read, written, or searched
- **Atomic session writes**: `tmp → rename → bak` — session files never corrupt on crash
- **No telemetry**: Zero data leaves your machine except the LLM API calls you configure

### 5. Memory That Works

Save facts once, Bobo remembers them automatically:

```
You: "my favorite color is blue"
Bobo: save_memory("my favorite color is blue")

(next session)
You: "what color do I like?"
Bobo: [Memory injected automatically] → "You told me your favorite color is blue!"
```

No need to ask Bobo to "remember" — relevant memories are injected before every LLM call at ~0ms overhead.

### 6. Scheduled Tasks

Set recurring tasks with natural language:

```
You: "rebuild the knowledge hub every morning at 7"
Bobo: bobo_schedule(action="create", name="wiki-daily", 
        task="运行 wiki_rebuild 更新知识图谱",
        time="07:00", repeat="daily")

You: "cancel the morning task"
Bobo: bobo_schedule(action="delete", name="wiki-daily")
```

Uses cron under the hood. List, create, delete from the chat.

---

## Configuration

### Providers

Bobo supports 7 providers out of the box. Set `BOBO_PROVIDER` in `~/.bobo/.env`:

```
# DeepSeek (default)
BOBO_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...

# OpenAI
BOBO_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Local (Ollama)
BOBO_PROVIDER=ollama
```

Or run `/settings` in the TUI to see current config, or just tell Bobo "switch to OpenAI."

### Obsidian Vault

```bash
echo "OBSIDIAN_VAULT=/path/to/your/vault" >> ~/.bobo/.env
```

17 tools for reading, writing, searching, classifying, and organizing notes.

### Notion

```
You: "connect my Notion"
Bobo: "请提供 Notion API Key"
You: paste the key
Bobo: "Notion 已连接"
```

### Email (IMAP)

Create `~/.bobo/mail.json`:

```json
{
  "server": "imap.gmail.com",
  "port": 993,
  "username": "you@gmail.com",
  "password": "your-app-password"
}
```

### GitHub

```
You: "connect GitHub"
Bobo: "请提供 GitHub Personal Access Token"
You: paste the token
Bobo: "GitHub 已配置"
```

---

## All Commands

```
/help      — Show available commands
/settings  — Show current provider, model, and API key status
/tools     — List all available tools
/clear     — Clear the current conversation
```

Settings can also be changed naturally: "use gpt-4o," "switch to OpenAI."

---

## Tools (68 total)

| Category | Tools |
|----------|-------|
| **General** | `cross_search`, `bobo_config`, `bobo_schedule`, `wiki_rebuild`, `api_register`, `api_call`, `get_current_time`, `save_memory`, `search_memory`, `save_skill`, `project_info`, `render`, `notion_setup` |
| **Knowledge** | `search_obsidian`, `read_obsidian`, `write_obsidian`, `append_obsidian`, `notion_search`, `notion_read_page`, `notion_create_page`, `notion_append`, `search_emails`, `read_email_content`, `analyze_emails` |
| **Code** | `code_execution`, `file_writer`, `execute_terminal`, `search_code`, `refactor`, `git_status`, `github_create_repo`, `github_create_pr`, `github_pr_diff`, `github_pr_comment`, `github_check_auth`, `github_setup` |
| **Files** | `read_local_file`, `list_directory`, `file_operation`, `restore_checkpoint` |
| **Web** | `web_search`, `web_fetch`, `web_extract`, `browser_open`, `browser_get_title`, `open_url` |
| **macOS** | `send_notification`, `read_clipboard`, `write_clipboard`, `set_reminder`, `list_reminders`, `create_calendar_event`, `list_calendar_events` |
| **Obsidian** | `read_obsidian`, `write_obsidian`, `search_obsidian`, `append_obsidian`, `classify_note`, `batch_copy_notes`, `batch_delete_notes`, `batch_move_notes`, `create_folder`, `delete_folder`, `delete_note`, `list_folder`, `move_note`, `move_to_folder`, `rename_note`, `read_recent` |
| **Skills** | `skill_coding_master`, `skill_Python__` (auto-registered from YAML files) |

---

## Example Workflows

```
# Research → Note → Link
"Research transformer architectures and save to Obsidian"
  → web_search("transformer architectures 2026")
  → write_obsidian("transformers.md", "...")
  → wiki_rebuild()

# Code → Test → Ship
"Create a Python script to sort my Downloads folder, push to GitHub"
  → file_writer("sort_downloads.py", "...")
  → [auto-run] python3 sort_downloads.py
  → github_create_repo("file-sorter")
  → github_create_pr(title="Add file sorter")

# Multi-platform search → Copy
"Find the Q4 planning doc, copy it to Obsidian"
  → cross_search("Q4 planning")
  → notion_read_page("page-id-123")
  → copy_to_obsidian("page-id-123")

# Daily automation
"Rebuild my knowledge hub every morning"
  → wiki_rebuild()
  → bobo_schedule(action="create", name="daily-hub",
      task="运行 wiki_rebuild", time="07:00", repeat="daily")
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| TUI shows no response | Check API key in `~/.bobo/.env`. Run `/settings`. |
| "Tool name must be unique" | Skills with Chinese names get sanitized. Rename skill files. |
| Obsidian tools missing | Set `OBSIDIAN_VAULT` in `.env`. |
| Notion tools missing | Run `notion_setup` with your API key. |
| GitHub push fails | Run `gh auth login` or `github_setup`. |
| Chinese input crashes TUI | Compact mode enabled. Use single-line input. |
| Session can't be deleted | Fixed in latest version. Ensure `session.delete` handler exists. |

---

## Architecture

```
bobo (CLI)
  └── ui-tui/              Hermes TUI frontend (React/Ink/TypeScript)
        └── spawns python -m bobo_tui_gateway.entry
              └── bobo_tui_gateway/    JSON-RPC gateway (stdin/stdout)
                    ├── entry.py       Main loop + signal handling + setup wizard + cron scheduler
                    ├── server.py      30+ RPC method handlers
                    └── transport.py   Thread-safe stdout writer
              └── core/               Agent engine (~340 LOC each)
                    ├── engine.py      Conversation loop, state machine
                    ├── context.py     History compression, query classification
                    ├── tool_runner.py Tool execution, error enrichment, rollback
                    ├── llm_caller.py  API caller with streaming + retry (3 attempts)
                    ├── provider.py    7 built-in providers
                    └── session_manager.py  Atomic session persistence
              └── tools/              68 tools, auto-discovered with gating
                    └── __init__.py    Auto-discovery + skill-as-tool registration
              └── ~/.bobo/             User config directory
                    ├── .env          Provider keys, vault paths
                    ├── apis/         Registered custom APIs
                    └── schedules.json Scheduled tasks
```

---

## Development

```bash
# Set up
git clone <repo>
cd bobo-agent && pip install -e .

# Run tests (no API key needed)
python3 tests/test_mock_engine.py

# Add a tool
# Create tools/my_tool.py with register(reg) function:
def register(reg):
    reg("my_tool", execute_func, schema, check_fn=optional_check)
```

To gate a tool behind a prerequisite:

```python
_check = lambda: bool(os.environ.get("MY_CONFIG", ""))

def register(reg):
    reg("my_tool", execute_func, schema, check_fn=_check)
```

---

## Acknowledgements

The TUI frontend (`ui-tui/`) is based on [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research (MIT). Hermes Ink is a fork of [Ink](https://github.com/vadimdemedes/ink) by Vadim Demedes.

See `NOTICE.md` for full details.

---

## License

MIT
