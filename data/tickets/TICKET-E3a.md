# TICKET-E3a — 安葬旧 YAML 技能系统（僵尸系统清理）

- 分支：`fix/ticket-e3a-skill-zombie`（从最新 main 切出）
- 类型：熵减计划 E2-③ 第一刀（删死代码 + 修持久化 bug）
- 纪律：禁止 merge、禁止 push、禁止碰 main；完成后五查汇报等 Kimi 终审
- 基线：1489 passed / 2 skipped（合并后复跑以此为准，删除死代码导致的测试删改需逐一说明）

## 背景（Kimi 已完成的诊断，以下为已证实事实，不是猜测）

1. **7/27 commit `628bb59`** 故意退役了旧 YAML 技能系统（skills/ 清空、prompt 路径改指 data/skill-standards/），但读取它的代码一行没删。
2. **injector 段 2**（`core/injector.py` 约 132–201 行）每轮实例化 `SkillManager` 扫空目录 `skills/*.yaml`，拿到空列表后静默跳过。"40 轮 0 命中"的真相：没有技能可命中。
3. **`tools/save_skill.py` 是必崩工具**：它调用 `sm.extract_steps_from_history()` 和 `sm.create_skill_from_history()`，这两个方法在 `core/skill_manager.py` 中**不存在**（全部方法清单：`_load_all/list_skills/get_skill/get_skill_tools/execute_skill/add_skill/_resolve_vars/save_from_recording/load_skill`）。每次调用必抛 AttributeError——8/1 "创建技能后遗忘"事件的根因：技能从未落盘。
4. 活着的技能系统是 `data/skill-standards/*/standard.md`（8 个）+ `core/skill_loader.py`（injector 段 9）。本票不动段 9 的注入行为（那是 E3b 的活）。
5. `SkillManager` 是缝合怪：`add_skill()` 写旧 yaml，`save_from_recording()` 写新 skill-standards。

## 施工清单

### A. 验证诊断（先做，写入汇报）
- 直接调用 `save_skill` 工具（构造假 history），复现 AttributeError，截图/日志作为罪证附进五查汇报。

### B. 安葬旧系统（删除）
1. **core/injector.py 段 2**：整段技能工作流注入（try 块，约 132–201 行）删除。`prompt.budget` 事件中 skills 段的处理自行决断（保留键置零或移除），但以测试为准并在汇报中说明。
2. **core/engine.py**：
   - line 20 `from core.skill_manager import get_skill_manager`
   - line 94–95 `self.skill_manager` / `self.skill_executor`
   - `_check_skill_match()`（永远返回 None 的死方法）
   - `_handle_pre_input()` 中永远不会进入的 skill 执行分支（约 389–397 行）
3. **bobo_tui_gateway/handlers/sessions.py**：`_skill_mgr` 与 `"skills": {"skills": _skill_mgr.list_skills()}`。**先检查 ui-tui 前端是否消费 skills 字段**：若消费则保留字段返回静态空列表，若不消费则删除。汇报中给出检查证据。
4. **tools/save_skill.py**：重写为调用**唯一活系统**——`save_from_recording()`（写 data/skill-standards/）。保留"把刚才的操作保存成技能"这个能力，这是核心能力，不许丢。TOOL_SCHEMA 描述同步更新。
5. **core/skill_manager.py**：退役 yaml 通路——`_load_all` 的 yaml glob + index.json 兼容、`add_skill`、`load_skill`、`get_skill`、`get_skill_tools`、`execute_skill`、`_resolve_vars`。只留活系统需要的部分（`save_from_recording`、`_auto_triggers`、singleton）。类/文件可重命名或精简，自行决断并说明。
6. **tools/__init__.py:36** 的 `execute_skill.py` 跳过规则：检查 tools/ 下是否存在 execute_skill.py，存在则连同规则一起安葬。
7. **core/context.py:191** 工具分类列表中的 `save_skill`：保留（工具还在，只是修好了），但确认分类仍正确。
8. **skills/ 空目录**：删除（.gitkeep 也不需要，目录由 save_from_recording 按需创建 skill-standards，不再需要 skills/）。同时确认 engine.py:87 `self.skills_dir` 等残留引用一并清除。

### C. 测试
- 更新受牵连的测试：tests/test_injector.py（14 处引用）、tests/test_note_pointer.py（6 处）、tests/test_engine_core.py（2 处）。删除的行为对应测试删除，逐条在汇报中说明。
- **新增验收测试**：
  1. save_skill 端到端：构造含工具调用的假 history → 调用工具 → 断言 `data/skill-standards/<name>/standard.md` 落盘 → 断言 `skill_loader` 能重新加载它（持久化 bug 修复证明）。
  2. injector 回归：注入产物中不再出现 `[推荐技能` / `[可参考的技能工作流` 段。
  3. session.info RPC 返回结构不含死数据（或 skills 字段为静态空列表，取决于 B3 检查结果）。
- 全量 pytest 零回归。

## 边界（不许碰）
- injector 段 9（skill_loader 命中注入与"可用标准列表"）——E3b 的活。
- GUIDANCE 相关一切。
- 段 5 AGENTS.md 注入——E3b 的活。

## 五查汇报要求
1. A 项复现罪证（AttributeError 实录）。
2. B3 前端字段消费检查证据。
3. 每个删除点的 before/after 摘要。
4. 测试删改逐条说明 + 全量 pytest 输出。
5. 分支/commit/工作区状态原文，是否需重启（改 core/ 必是）。
