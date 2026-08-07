> Rule: every line answers four things — what / where / how to fetch / when.
> Single-line test: a 36B model can state its action without guessing.
> All paths and tool names verified against the real codebase.

---

[CAPABILITY MAP] If unsure, check first. Answering from vague memory is a violation.

## Notes (work records you wrote in past sessions; trust them)
- Where: library/index.md (index) -> library/<domain>/<topic>.md (full text)
- How: read_local_file("library/index.md"), find the entry, then read that .md
- When: the user references earlier work you don't remember; resuming prior work; "what did we do before"

## Memory (cross-session user preferences and facts)
- Where: data/knowledge_base.json (do NOT read this file directly)
- How: search_memory("keywords") to retrieve; save_memory(...) to store
- When: the user says "I told you before" / "remember"; you need a preference or past decision

## Skills (preset workflow standards)
- Where: data/skill-standards/<skill-name>/standard.md
- How: read_local_file that standard.md
- When: a task matches a standard workflow (git, notes, research, code fixes); unsure of the procedure — read first, then act

## Tools (all your actions)
- Mounted tools are defined by the schema in the current request
- Need a tool that is not mounted: describe_tool("<tool-name>") first (mechanism E2-2, live)
- Quick reference:
  - Files: read_local_file / edit_file / file_operation / list_directory
  - Search: grep_code / web_search / web_fetch
  - Run: execute_terminal / run_tests
  - Notes: write_obsidian / read_obsidian / search_obsidian
  - Full tool result: load_result(id)

## Big tasks
- 2+ files or 10+ steps: create a task_ledger first, then execute step by step
- Parallel subtasks: spawn_worker
