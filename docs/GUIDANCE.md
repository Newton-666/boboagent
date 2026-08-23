> Constitution: docs/HARCHITECTURE.md — modes/abilities/enforcement matrix in force.
> SELF L0 is always resident (docs/SELF.md top [SELF] block, byte-identical); consult this file only for details.
> Rule: every line answers four things — what / where / how to fetch / when.
> Single-line test: a 36B model can state its action without guessing.
> All paths and tool names verified against the real codebase.

---

[FRONTEND CONTRACT] Desktop UI work = blueprint-first (constitution Principle 6).
- Where: docs/FRONTEND-BLUEPRINT.md (the ONLY blueprint; apps/desktop/src/ is dead archive — do not edit or cite it as source)
- How: read docs/FRONTEND-BLUEPRINT.md before ANY change to apps/desktop/dist/index.html
- When: any ticket touching dist/, the desktop UI, or frontend guards
- Rule: product (dist/) is the source of truth — never revert it; blueprint MD must be updated in the same ticket; frontend guard tests must pass.

[CAPABILITY MAP] If unsure, check first. Answering from vague memory is a violation.

## Notes (work records you wrote in past sessions; trust them)
- Where: library/index.md (index) -> library/<domain>/<topic>.md (full text)
- How: read_local_file("library/index.md"), find the entry, then read that .md
- When: the user references earlier work you don't remember; resuming prior work; "what did we do before"

## Memory (cross-session user preferences and facts)
- Where: data/knowledge_base.json (do NOT read this file directly)
- How: search_memory("keywords") to retrieve; save_memory(...) to store
- When: the user says "I told you before" / "remember"; you need a preference or past decision
- Profile: user facts (name, language, style) -> save_memory(target="profile", memory_type="key"), injected separately

## Skills (preset workflow standards)
- Where: data/skill-standards/<skill-name>/standard.md
- How: read_local_file that standard.md
- When: a task matches a standard workflow (git, notes, research, code fixes); unsure of the procedure — read first, then act
- Record: say "开始教学" to start recording; "保存为 skill <名称>" to save into data/skill-standards/

## Tools (all your actions)
- Mounted tools are defined by the schema in the current request
- Need a tool that is not mounted: describe_tool("<tool-name>") first (mechanism E2-2, live)
- Quick reference:
  - Files: read_local_file / edit_file / file_operation / list_directory
  - Search: grep_code / web_search / web_fetch
  - Run: execute_terminal / run_tests
  - Notes: write_obsidian / read_obsidian / search_obsidian
  - Full tool result: load_result(id)
  - Unsure of a result? load it — a wrong guess costs more than a load

## Big tasks
- 2+ files or 10+ steps: create a task_ledger first, then execute step by step
- Parallel subtasks: spawn_worker
