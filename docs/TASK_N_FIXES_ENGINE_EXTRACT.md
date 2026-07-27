# 任务清单：N3/N1/N2 正确性修复 + engine.py 后处理段抽离

日期：2026-07-27。来源：kimi code 宏观审视（经 Kimi 逐条复核实锤）。
总原则：先做三个几行的正确性修复（721 测试兜底，零风险），
再做 engine.py 后处理段抽离（阻止雪球，不做大重构）。

---

## P0 — 三个正确性修复

### N3（正确性 bug，最高优先）：`_read_files` 存错变量

**位置**：`core/engine.py` 约 1569–1584（记录已读文件段）。

**问题**：循环记录每个 `read_local_file` 的已读内容时，
`self._read_files[fpath] = str(tool_results)[:200]` 存的是
`tool_results`——**整轮所有工具结果的聚合**，不是该工具自己的结果。
一轮读 A 和 B 两个文件，两者都被记成"A+B 混合体"。
此功能用于"上下文压缩后恢复已读文件"，存错内容 = 恢复出错误上下文。
注释声称"审计 #24 已修"，实际没修对（假修复）。

**修法**：把"当前这个 tool_call 对应的那一条结果"存进去，
不要存聚合变量。按 tool_call_id（或循环索引）从 tool_results 里
取对应条目。如果 tool_results 的结构不便按 id 索引，
就在 `_execute_tool_loop` 返回处一并带回应答映射。

**验收**：
- 新测试：同一轮里 read_local_file 读两个不同文件（内容分别为
  "AAA..." 和 "BBB..."），断言 `_read_files[A]` 含 "AAA" 不含 "BBB"，
  `_read_files[B]` 反之。
- 删掉/修正"审计 #24"那条名不副实的注释。

### N1：`tools/__init__.py:96-100` 坏死代码块

**问题**：`_skill_mgr = get_skill_manager()` 实例化后无人使用；
`print("含技能工具: ...")` 输出虚假（没有技能工具在此注册）。

**修法**：整块删除（import、实例化、print）。skill 已改走
`run_skill:xxx` 工具路径，这块是遗留。删前 grep 确认
`_skill_mgr` 在本文件外无引用。

**验收**：启动 bobo 时 stderr 不再出现"含技能工具"行；
工具加载数不变；测试全绿。

### N2：`file_writer.py read_file()` 漏查路径哨兵

**问题**：write/append（82、140 行）都查了 `BLOCKED_FOLDERS`，
`read_file`（168 行）没查，目前靠巧合兜底。

**修法**：`read_file` 入口加同款 BLOCKED_FOLDERS 检查，
拒绝时返回与 write/append 一致风格的拒绝信息。

**验收**：新测试——read_file 读 BLOCKED_FOLDERS 内路径被拒绝；
读正常路径不受影响。

---

## P1 — engine.py 后处理段抽离（外科手术，不是大重构）

**背景**：engine.py 几天内 1107 → 1690 行（+53%），
duo/草稿记忆/引用追踪全堆在主类里。不做 Pipeline 大拆
（duo 商讨已裁定：过度工程），但要把**约 1460–1635 的回合后处理段**
（change_log 记录、已读文件追踪、pattern tracker 等附属逻辑）
抽成独立模块，例如 `core/round_tracker.py`：

- Engine 持有一个 tracker 对象，主循环在对应位置调用
  `tracker.after_tool_round(...)` 之类的窄接口
- 状态（_read_files、_change_log、_file_last_step 等）迁入 tracker
- **行为零变化**：纯搬迁，不改任何逻辑（N3 的修复在 P0 已先行落地，
  抽离时带着修好的版本走）

**验收**：
- engine.py 行数降到 ~1450 以下
- 既有 721 测试全绿（它们就是最好的回归网）
- 新模块有自己的单测（至少覆盖 N3 验收那个场景）
- py_compile 全部改动文件

## 全线共同验收

- `pytest tests/ -q` 全绿，测试数 ≥ 721 + 新增
- 每个修复/抽离附带对应新测试（打回必留测试的节奏保持）
- py_compile 所有改动文件（交付底线）
