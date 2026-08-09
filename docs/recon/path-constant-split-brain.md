# 路径常量裂脑审计（TICKET-D2）

> 票：TICKET-D2 路径常量裂脑修复（测试反复污染真实 index.md）
> 分支：fix/ticket-d2-index-path-split-brain
> 日期：2026-08-09
> 状态：施工完成，待终审

## 一、问题定义（裂脑模式）

模块在 import 时把"从目录/环境派生的路径"固化为模块级常量（快照），
测试用 monkeypatch 改目录后，**扫描/读取走 patch 后的路径，写出仍走快照常量**
——读写不同源，测试把真实文件当 tmp 文件写，反复污染生产数据。

典型案例（本票起因）：

```
测试 patch tools.living_notes.LIBRARY_DIR = tmp
  → _rebuild_index() 扫描 tmp 目录
  → INDEX_PATH（import 时 = 真实 library/index.md）写真实索引
```

同类模式在 tools/ 多处存在：`vm._save() → sync_mirror()` 只 patch v5 侧
`_memory_db`，sync_mirror 走 memory_mirror 自身未 patch 的路径 → 全量测试
读真实 knowledge_base.json、重写真实 library/MEMORY.md（信号 85→70 事故）。

## 二、修复原则

路径一律改为**调用时动态解析**的模块级函数（`_xxx_path()` / `_xxx_dir()` /
`_xxx_db()`），废除 import 时快照常量。测试 patch 目录后读写天然同源，
无需任何隔离闸（隔离闸把测试假设硬编码进生产代码，隐式分支易误伤真实运行）。

## 三、审计清单（9 个独立快照，6 个模块）

| # | 模块 | 废除的快照常量 | 替代函数 | 说明 |
|---|------|---------------|---------|------|
| 1 | tools/living_notes.py | `INDEX_PATH` | `_index_path()` | 票本体：index.md |
| 2 | tools/v5_memory.py | `MEMORY_DB` | `_memory_db()` | knowledge_base.json |
| 3 | tools/v5_memory.py | `_MEMORY_BACKUP` | `_memory_backup()` | 随 `_memory_db()` 派生 |
| 4 | tools/memory_mirror.py | `MEMORY_DB` | `_memory_db()` | 与 v5 同源（BOBO_DATA_DIR） |
| 5 | tools/memory_mirror.py | `_MEMORY_BACKUP` | `_memory_backup()` | 同上派生 |
| 6 | tools/memory_mirror.py | `MIRROR_PATH` | `_mirror_path()` | MEMORY.md 镜像 |
| 7 | tools/load_result.py | `WORKSPACE_DIR` | `_workspace_dir()` | workspace 目录 |
| 8 | tools/bobo_schedule.py | `SCHEDULE_FILE` | `_schedule_file()` | schedules.json |
| 9 | tools/edit_file.py | `TRASH_DIR` | `_trash_dir()` | 回收站目录 |

注：`load_result._STATS_PATH` 是 `WORKSPACE_DIR` 的二次派生（`os.path.join`），
随 `_workspace_dir()` 一并动态化为 `_stats_path()`，不单列。

### 动态化明细（5 个审计扩展模块 + living_notes 票本体）

- **living_notes.py**（票本体）：`INDEX_PATH` → `_index_path()`，
  写出点 `_rebuild_index()` L476 同步改。
- **v5_memory.py**：`MEMORY_DB`/`_MEMORY_BACKUP` → `_memory_db()`/`_memory_backup()`。
- **memory_mirror.py**（已知嫌疑）：`MEMORY_DB`/`_MEMORY_BACKUP`/`MIRROR_PATH`
  → 三个派生函数，`sync_mirror()`/`import_from_md()`/`_write_json()`/`_align_mtime()`
  全部改走函数。
- **load_result.py**：`WORKSPACE_DIR`/`_STATS_PATH` → `_workspace_dir()`/`_stats_path()`。
- **bobo_schedule.py**：`SCHEDULE_FILE` → `_schedule_file()`。
- **edit_file.py**：`TRASH_DIR` → `_trash_dir()`。

## 四、测试配套（双通道隔离）

凡是触发写库（`_save → sync_mirror`）的测试，必须**同时 patch v5 侧与
memory_mirror 侧**，否则 sync_mirror 读真实 JSON、写真实 MEMORY.md：

```python
import tools.v5_memory as vm
import tools.memory_mirror as mm
monkeypatch.setattr(vm, "_memory_db", lambda: str(db))
monkeypatch.setattr(vm, "_memory_backup", lambda: str(bak))
monkeypatch.setattr(mm, "_memory_db", lambda: str(db))
monkeypatch.setattr(mm, "_memory_backup", lambda: str(bak))
monkeypatch.setattr(mm, "_mirror_path", lambda: tmp_path / "MEMORY.md")
```

已适配：
- tests/conftest.py（isolated_memory_db 增补 mm 侧）
- tests/test_p1_memory.py（memory_db fixture + 2 处内联写库测试）
- tests/test_memory_time_decay.py（clean_db fixture）
- tests/test_memory_mirror.py、tests/test_note_pointer.py、
  tests/test_library_git.py、tests/test_library_mirror.py、
  tests/test_note_rewrite.py、tests/test_note_source.py、
  tests/test_context_marking.py、tests/test_p0_schedule.py
  （patch 快照常量 → patch 派生函数）
- tools/exam/runner.py（考卷隔离，见第五节）

新增回归测试：`test_living_notes.py::test_never_writes_real_index`
——patch LIBRARY_DIR 下全流程跑通，断言真实 index.md mtime（纳秒）+ 内容零改动。

## 五、考卷隔离（exam/runner.py）仍然成立

runner.py 装配考生时对记忆双通道重定向（`build_examinee` 前的隔离段）：

```python
import tools.v5_memory as _v5
import tools.memory_mirror as _mm
tmp_kb = tmp_events / "knowledge_base.json"
_v5._memory_db = lambda: str(tmp_kb)
_v5._memory_backup = lambda: str(tmp_kb) + ".bak"
_mm._memory_db = lambda: str(tmp_kb)
_mm._memory_backup = lambda: str(tmp_kb) + ".bak"
_mm._mirror_path = lambda: Path(tmp_events) / "MEMORY.md"
_ln.LIBRARY_DIR = tmp_lib
```

新旧赋值方式等价性论证：
- 旧：`monkeypatch.setattr(module, "CONST", value)`——改模块全局属性；
  新：`module.func = lambda: ...`——改模块全局属性（函数对象也是属性）。
  两者都是**在调用方模块命名空间上做属性替换**，函数体内通过模块全局名
  `_memory_db()` 调用，运行时查模块 `__dict__`，赋值后即命中新函数。
- 唯一的差异是语法层面（setattr vs 直接赋值），语义完全一致。
- 考卷隔离的完整性取决于"两条链路的路径都在 tmp"：
  JSON 读写走 `_v5._memory_db`/`_mm._memory_db`（tmp），
  镜像写走 `_mm._mirror_path`（tmp），索引写走 `_ln.LIBRARY_DIR`（tmp），
  三处全部重定向 → 考生无论触发哪条写路径都不会碰真实文件。
- 证据：`python -m pytest tests/test_exam_gate_c.py` 通过（见下）。

## 六、保留论证（不动态化）

| 模块 | 常量 | 保留理由 |
|------|------|---------|
| core/injector.py | `_GUIDANCE_PATH` | 只读注入（stat+open），不写回；测试用 setattr 改常量本身，读写同源，无裂脑 |
| core/privacy.py | `_PRIVACY_FILE` | 只读；基于 BOBO_DATA_DIR 派生，测试无 patch 需求 |
| tools/code_execution.py | `PROJECTS_DIR` | 从 config 派生，config 已支持环境变量 BOBO_PROJECTS_DIR 覆盖（test_bugfixes 用 env 控制），无裂脑 |
| tools/obsidian_tools.py | `TRASH_DIR` | 基于 Path.home() 固定派生，不依赖可 patch 的项目目录 |
| tools/file_operation.py | `TRASH_DIR` | 同上 |
| config.py | `SESSION_DIR`/`PROJECTS_DIR`/`BOBO_ENV_FILE` | 已有 os.environ.get 覆盖，env 是测试可控源头，无裂脑 |

## 七、验收结果

- 修复前复现：patch LIBRARY_DIR 后 `_rebuild_index()` 写真实 index.md，
  md5 aae30552 → b49f2710（内容含"测试主题"）。复现后已恢复。
- 相关测试（p1_memory / time_decay / memory_mirror / living_notes 等）全绿。
- 全量：`1569 passed, 2 skipped` 零回归（修复 conftest 后复跑确认）。
- 跑完全量后真实 index.md / MEMORY.md / knowledge_base.json md5 与 mtime 不变：
  - index.md aae30552、MEMORY.md 1e2f3b4f、knowledge_base.json e8b607e5
- 污染源排查：全量曾污染 MEMORY.md（信号 85→70）。根因是
  `conftest.isolated_memory_db` 只 patch v5 侧、缺 memory_mirror 侧——test_injector
  autouse 复用它跑 engine，`_save → sync_mirror` 读真实 JSON、写真实 MEMORY.md。
  已在该 fixture 补 mm 侧三函数 patch（见第四节），复跑全量零改动。
- 真实库恢复：knowledge_base.json 已从 18:11 清洁备份（exam-clean2）恢复，
  MEMORY.md 由 sync_mirror 重生成与之收敛。历史信号分衰减为真实使用残留，
  非本次测试虚构数据。
