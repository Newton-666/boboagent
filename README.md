# Bobo Agent

A personal AI agent for your terminal. Bobo reads your Obsidian notes, manages your email, searches the web, runs terminal commands, and more — all through a single chat interface.

## Quick Start

```bash
# Install
pip install bobo-agent

# Or from source
git clone <your-repo-url>
cd bobo-agent && pip install -e .

# Configure your API key
mkdir -p ~/.bobo
echo "DEEPSEEK_API_KEY=sk-your-key-here" > ~/.bobo/.env

# Run
bobo
```

Bobo starts a TUI (terminal user interface) — type a message and press Enter to begin.

## Configuration

### API Key (required)

Bobo currently supports DeepSeek. Add your key to `~/.bobo/.env`:

```
DEEPSEEK_API_KEY=sk-your-deepseek-key
```

### Obsidian Vault (optional)

Set the path to your Obsidian vault to enable note-reading tools:

```
OBSIDIAN_VAULT=/path/to/your/vault
```

### Email (optional)

Create `~/.bobo/mail.json` with your IMAP settings:

```json
{
  "server": "imap.gmail.com",
  "port": 993,
  "username": "you@gmail.com",
  "password": "your-app-password"
}
```

## Features

### Built-in tools (27+)

| Category | Tools |
|----------|-------|
| Web | `web_search`, `web_fetch`, `web_extract` |
| Files | `read_local_file`, `list_directory`, `file_operation` |
| Code | `code_execution`, `search_code`, `refactor`, `file_writer` |
| Terminal | `execute_terminal`, `open_url` |
| Memory | `save_memory`, `search_memory` |
| Obsidian | `read_obsidian`, `write_obsidian`, `search_obsidian`, and 14 more |
| Email | `search_emails`, `read_email_content`, `analyze_emails` |
| macOS | `send_notification`, `read_clipboard`, `write_clipboard`, `set_reminder` |
| Calendar | `create_calendar_event`, `list_calendar_events` |
| Project | `project_info`, `save_skill` |

Tools that require configuration (Obsidian, email, macOS-specific) are automatically disabled when their prerequisites are missing.

### Architecture

```
bobo (CLI entry point)
  └── ui-tui/              Hermes TUI frontend (React/Ink/TypeScript)
        └── spawns python -m bobo_tui_gateway.entry
              └── bobo_tui_gateway/    JSON-RPC gateway (stdin/stdout)
                    ├── entry.py       Main loop + signal handling
                    ├── server.py      RPC method handlers + engine dispatch
                    └── transport.py   Thread-safe stdout writer
              └── core/     Agent engine
                    ├── engine.py          Conversation loop, tool dispatch, streaming
                    ├── llm_caller.py      API caller with streaming + retry
                    ├── session_manager.py Session persistence with atomic writes
                    ├── tool_executor.py   Tool sandbox with timeout
                    ├── skill_manager.py   Skill loading
                    └── skill_executor.py  Skill execution
              └── tools/    46 tool plugins (auto-discovered)
                    └── __init__.py       Auto-discovery with prerequisite gating
```

### Security

- **Secret redaction**: Tool output is scanned for API keys, tokens, passwords, and private keys before reaching the LLM. Matched patterns are replaced with `[REDACTED]`.
- **Tool gating**: Tools with unmet prerequisites (e.g., email without mail config) are excluded from the LLM's tool list entirely.
- **Approval prompts**: Terminal commands and destructive file operations require user confirmation.
- **Atomic session writes**: Session files are written to a `.tmp` file first, then atomically renamed. A `.bak` copy is kept for recovery.

### Streaming

Responses appear token-by-token as the LLM generates them, not as a single block after 20 seconds.

## Adding a Tool

Create a new file in `tools/` with a `register()` function:

```python
"""Say hello to the user"""

TOOL_NAME = "say_hello"

def execute(name: str) -> str:
    return f"Hello, {name}!"

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "Greet someone by name",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
```

To gate the tool behind a prerequisite, add a `check_fn`:

```python
    _check = lambda: bool(__import__('os').environ.get('MY_CONFIG', ''))

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA, check_fn=_check)
```

## Project Status

Bobo is under active development. The existing codebase focuses on macOS, but the architecture is cross-platform ready. Linux and Windows support can be added by gating platform-specific tools.

## License

MIT
