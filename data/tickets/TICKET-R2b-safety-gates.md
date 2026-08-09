# TICKET-R2b 镜像安全铁闸（血案修正票）

> 分支：`fix/ticket-r2b-safety-gates`（从最新 main 切出）
> 前置：TICKET-R2（feat/ticket-r2-obsidian-mirror，未合并）
> 优先级：最高。本票不过，R2 永不合并。

## 〇、owner 裁决（2026-08-09）

熔断优先，映射可弃：**如果镜像在铁闸之下仍然做不好，就直接砍掉 Obsidian 映射，只保留项目内 library/ 单一主库。** 施工者有权在施工报告中论证并选择砍除路径（见 §四 B）。

## 一、背景：08-09 血案罪证链（已终审定案，不许翻案）

1. R2 初版 `tools/library_mirror.py` 空值闸失效（铁证：`data/trash/library_mirror.py_20260809_085230` L102-103）：
   `Path("")` == `Path(".")`，`str()` 非空且 `exists()` 为真 → OBSIDIAN_VAULT 未配置时 vault 静默落为 **cwd**。
2. `tests/test_library_mirror.py::test_silent_skip_when_env_missing` 删除环境变量后以临时小库（仅 a.md/aaa）调用 sync → 同步目标 = pytest cwd = 项目根 → `项目根/library` = **主库本体**。
3. 删除传播阶段将主库 20+ 篇笔记与整个 `.history/` unlink + rmdir；写入阶段把带 MIRROR 头的测试 a.md 盖进主库。
4. 后续挂钩同步把灭失状态传播至 Obsidian 镜像（43→4），双库陪葬。
5. 靠 Time Machine 08:29 本地快照才救回。主库从未入 git，无其他备份。

**教训：删除传播是核弹级能力，当前实现没有任何剂量限制。**

## 二、三道铁闸（必须全部实现）

### 闸 1 — vault 解析禁区
`sync_library_to_obsidian()` 在解析 vault 后必须校验，命中任一条件 → 跳过（`skipped=True`，发 `library.mirror_blocked` 事件，含原因）：
- vault_raw 为空 / 纯空白（现行 `vault_raw.strip()` 检查保留，并补测试覆盖 `Path("")`→`Path(".")` 陷阱）；
- vault 解析后 == cwd、== 项目根（`_REPO_ROOT`）、== 主库 `LIBRARY_DIR` 本身或其任何祖先目录；
- `dst_root`（vault/library）解析后 == 主库或其祖先/子孙重叠。

### 闸 2 — 批量删除熔断
删除传播阶段执行前统计待删清单 `pending_removed`：
- `len(pending_removed) > 5` **或** `len(pending_removed) > 0.3 * 镜像侧现有文件数` → **整个删除阶段放弃**（写入阶段照常），发 `library.mirror_blocked` 事件（reason="mass_delete_fuse", pending_removed 全清单）。
- 提供显式人工 override：`sync_library_to_obsidian(..., allow_mass_delete=True)`，仅手动入口 `python -m tools.library_mirror --allow-mass-delete` 可触发；living_notes 挂钩**永远不许**传此参数。

### 闸 3 — 测试隔离铁律
- `tests/test_library_mirror.py` 及任何涉及镜像/笔记目录的测试：`sync_library_to_obsidian()` 调用必须显式传 `vault_dir=<tmp>`；凡不传 vault_dir 的调用一律 `monkeypatch.delenv("OBSIDIAN_VAULT")` 且断言 `skipped=True`。
- 新增守卫测试 `test_never_touches_real_paths`：在测试中静态/动态断言 sync 的所有写入与删除路径不落在真实 `library/`、真实 vault、项目根内（可用 tmp cwd + 空环境变量重放本次案发场景，断言主库侧零改动）。
- 新增回归测试 `test_r2b_massacre_scenario_blocked`：**完整重放血案**——delenv + tmp 小库 + cwd=项目根的子进程/隔离目录模拟 → 断言 skipped/blocked，临时主库文件零删除。

## 三、挂钩加固

- `tools/living_notes.py` 挂钩调用处（现 L572-579）：catch 所有异常（已是 try/except），并**显式禁止**传 `allow_mass_delete`；挂钩触发 `library.mirror_blocked` 时降级记 `notes.error`，不阻塞主流程。

## 四、两条路线（施工者择一并论证）

A. **修复路线**：实现 §二 §三，镜像保留。
B. **砍除路线**：若论证删除传播在挂钩自动触发场景下本质不可控，则删除挂钩调用与 `python -m` 自动入口，镜像工具仅保留**纯手动**全量入口（必须每次显式传 vault_dir 且带 `--i-know-what-im-doing` 确认），或整体退役 `library_mirror.py`、主库唯一真源。选 B 需在施工报告中给出论证。

## 五、验收标准（终审逐条复跑）

1. 三道铁闸各有至少 1 个针对性测试，且 §二闸3 的血案重放测试通过；
2. 全量 `pytest tests/ -q` 零回归（当前基线以 main 实测为准）；
3. 真实灌库实测：恢复后的 27 篇主库 → 镜像 27 篇一致（若选路线 A）；
4. 模拟熔断：人为制造主库大批量缺失场景（tmp 双目录），断言删除被拒绝且事件发出；
5. 施工全程未碰 main、未 merge、未 push，停在 `fix/ticket-r2b-safety-gates` 等终审。

## 六、禁止项

- 禁止在测试中以任何形式将真实 `library/`、真实 vault、项目根作为 sync 目标；
- 禁止删除或改动 `data/trash/library_mirror.py_20260809_085230`（罪证存档）；
- 禁止 merge/push；禁止绕过熔断"先跑了再说"。
