# GUIDANCE.md Draft v1.0 定稿 (English, owner approved 2026-08-07, NOT yet active)

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
- Need a tool that is not mounted: describe_tool("<tool-name>") first [mechanism E2-2, to be built]
- Quick reference:
  - Files: read_local_file / edit_file / file_operation / list_directory
  - Search: grep_code / web_search / web_fetch
  - Run: execute_terminal / run_tests
  - Notes: write_obsidian / read_obsidian / search_obsidian
  - Full tool result: load_result(id)

## Big tasks
- 2+ files or 10+ steps: create a task_ledger first, then execute step by step
- Parallel subtasks: spawn_worker

---

## Review memo (not part of the text)
1. ✅ 双 library 已裁决（owner 2026-08-07）：项目内 library/ 是主库、唯一正统，
   Obsidian 侧只是展示层/映射。导航只指项目 library/。
   后续动作：①排查 Obsidian 侧映射机制现状（是同步还是早已断裂）；
   ②bobo 手写落在 Obsidian vault 的复盘笔记按既有任务走正规管道重建到主库。
2. describe_tool is E2-2 infrastructure, not yet built; add fallback wording before activation.
3. Quick reference 保留（owner 2026-08-07 裁决）：弱模型的第一反应肌肉记忆，不砍。
   正文定稿 ~850 字符，接受略超 800 目标。
