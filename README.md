# Bobo Agent

<p align="center">
  <b>A personal AI agent that lives across your knowledge</b><br>
  Obsidian · Notion · Email · GitHub · Any API
</p>

<p align="center">
  <a href="https://github.com/Newton-666/boboagent/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/tests-709%20passed-brightgreen.svg" alt="709 Tests Passed"></a>
</p>

---

## Quick Start

```bash
curl -sSL https://raw.githubusercontent.com/Newton-666/boboagent/main/install.sh | bash
```

Then:

```bash
bobo
```

On first launch, the TUI setup wizard walks you through selecting a provider (DeepSeek, OpenAI, Anthropic, Kimi, Gemini, Ollama…) and entering your API key — no manual `.env` editing needed. Your key goes directly to disk, never through the LLM.

**Prerequisites**: Python 3.10+ and Node.js v18+. The installer checks both and gives clear guidance if something is missing.

---

## What Makes Bobo Unique

### Skill System — Teach Once, Use Forever

Bobo's preset workflow standards (`data/skill-standards/`) are hard constraints injected automatically when you trigger them:

| Skill | Trigger | What it enforces |
|-------|---------|------------------|
| **Code Fix** | Bug reports, compile errors | 5-phase state machine: locate → read → diagnose → fix → verify. No editing unread files, no claiming "fixed" without tests. |
| **Web Design** | Landing pages, websites | Morandi color system, 3-layer visual hierarchy, no emoji, no gradient, SVG logo, CSS as separate file. 3-step workflow: exploration → spec → full page. |
| **Note Taking** | Save to Obsidian | Search-before-write, auto-folder matching, mandatory frontmatter, write-then-verify. |
| **Git Workflow** | Git operations | Branch → commit → tag → merge → push. Rollback tags on every merge. |
| **Research** | Searches, comparisons | Multi-source cross-verification (≥2 searches, ≥2 sources), contradiction reporting, source attribution. |
| **Duo** | `/duo` commands | Dual-agent debate for architectural decisions. A/B opposing perspectives with decision checklist. |
| **Self-Hosting** | bobo self-modification | Branch-based task system: feat/ branches, task tickets, graduated authority. Never touch main. |

Add your own: create `data/skill-standards/<name>/standard.md` with a `keywords:` line and it auto-discovers. No code changes needed.

### Cross-Platform Knowledge

```
You: "find everything about API redesign"
Bobo: cross_search("API redesign")
  → [Obsidian] Projects/API-redesign.md
  → [Notion] Q1 Planning
  → [Email] "Re: API redesign feedback"
```

### Interactive Model Switching

Type `/model` in the TUI → arrow keys to choose provider → choose model tier → enter API key inline. Switches hot-reload — no restart needed.

### 8 Built-in Providers

DeepSeek · OpenAI · Anthropic · Google · OpenRouter · Ollama · **Moonshot (Kimi)** · Custom

Set `BOBO_TEMPERATURE` and `BOBO_MAX_TOKENS` per model if needed (reasoning models like kimi-k3 auto-set `temperature=1.0`).

### Context That Scales

Dynamic context budget adjusts to your model's actual window (1M for kimi-k3, 128k for GPT-4o, 32k for Ollama). Retroactive result marking keeps old tool outputs from cluttering context. Compression only triggers when actually needed.

### Privacy & Security

- **Secret redaction**: API keys, tokens, passwords → `[REDACTED]` before reaching the LLM
- **No telemetry**: Zero data leaves your machine except the LLM API calls you configure
- **Atomic writes**: Session files never corrupt on crash
- **Trash-based safety**: Deleted files go to `~/.bobo/trash/`, recoverable via `restore_checkpoint`

---

## Configuration

Bobo auto-detects your config. To check or change:

```
/model          Interactive provider/model picker (hot-reload)
/provider       Switch provider
/mode           Toggle proactive mode (off/subtle/full)
```

Or set environment variables in `~/.bobo/.env` (or `data/.env` in dev mode):

```bash
BOBO_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
API_MODEL_NAME=deepseek-v4-pro
BOBO_TEMPERATURE=1.0        # reasoning models
BOBO_MAX_TOKENS=32768
```

### Obsidian

```bash
OBSIDIAN_VAULT=/path/to/your/vault
```

### GitHub

Talk to Bobo: "connect GitHub" — it'll ask for a Personal Access Token.

### Notion

Talk to Bobo: "connect Notion" — it'll ask for your Notion API key.

---

## Commands

```
/model      — Interactive provider + model picker
/help       — Available commands
/tools      — List all tools
/clear      — Clear current conversation
/mode       — Toggle proactive mode
```

---

## Architecture

```
bobo (CLI)
  └── ui-tui/              Hermes TUI frontend (React/Ink/TypeScript)
        └── spawns python backend via JSON-RPC over stdin/stdout
              └── core/    Agent engine (~340 LOC each)
                    ├── engine.py      State machine, skill injection
                    ├── context.py     Dynamic context budget, token estimation
                    ├── tool_runner.py Parallel execution, result marking
                    ├── llm_caller.py  API caller with streaming + retry
                    ├── provider.py    8 built-in providers
                    └── session_manager.py  Atomic persistence
              └── tools/              78 auto-discovered tools with gating
              └── data/skill-standards/ Preset workflow standards (auto-discovered)
              └── ~/.bobo/             User config + data directory
```

---

## Development

```bash
git clone https://github.com/Newton-666/boboagent.git
cd boboagent
pip install -e ".[dev]"

# Run tests (no API key needed, 735 passed, 2 skipped)
pytest tests/ -q
```

### Add a Skill Standard

```bash
mkdir -p data/skill-standards/my-skill
cat > data/skill-standards/my-skill/standard.md << 'EOF'
# My Skill Standard v1

> keywords: trigger, words, here
> excludes: avoid, these, topics
> requires: git-workflow

## Workflow

1. Step one
2. Step two

## 禁止

- ❌ Don't do this
EOF
```

Bobo auto-discovers it. No code changes, no registration.

### Single Runtime Rule（单一运行时规矩）

> 本机开发只有一个运行时：**这个仓库**。
>
> - 终端 `bobo` 命令是 editable install，直接运行仓库代码。
> - 数据目录是仓库内 `data/`（config.py 检测到仓库根有 `data/` 即启用开发模式）。
> - **`~/.bobo` 里只放数据，不放代码。** 那里曾经躺着一份旧代码副本
>   （桌面 app 打包时的安装产物），造成过 5 次"改了但没生效"的同步惊吓，
>   已于 2026-07-27 清除。
> - **交付/验收代码改动时，永远不需要"同步到 ~/.bobo"。** 看到有人
>   （包括 AI 协作者）条件反射式地往 `~/.bobo` 复制代码，请制止。
> - 桌面 Bobo.app 是个例外：打包版启动时会自动把自身捆绑的后端重新装入
>   `~/.bobo`（见 `apps/desktop/electron/main.cjs` 的 `installBoboBackend`），
>   它自给自足，也不需要手动同步。要更新桌面 app 的代码，正确姿势是在
>   `apps/desktop/` 里重新 build，而不是手动复制文件。

---

## License

MIT

## Acknowledgements

The TUI frontend is based on [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research (MIT). Hermes Ink is a fork of [Ink](https://github.com/vadimdemedes/ink) by Vadim Demedes.
