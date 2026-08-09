# TICKET-D2 路径常量裂脑修复（测试反复污染真实 index.md 根治票）

> 分支：`fix/ticket-d2-index-path-split-brain`（从最新 main 切出）
> 优先级：高。每次全量 pytest 都在悄悄重写真实 `library/index.md`——已案发两次。

## 一、罪证（已终审定案，不许翻案）

`tools/living_notes.py` L34：`INDEX_PATH = LIBRARY_DIR / "index.md"` —— **import 时的快照常量**。
测试 `monkeypatch.setattr(ln, "LIBRARY_DIR", tmp)` 后：
- `_rebuild_index()` 扫描用的是**打补丁后**的 LIBRARY_DIR（tmp 内容）；
- 但 L476 写出用的是**未打补丁**的 INDEX_PATH（真实 index.md）。

结果：测试内容（如"已有主题（2 篇会话）"）反复覆盖真实索引。
案发时间：08-09 08:53（血案期间）、08-09 18:34（D1 验收 pytest 期间，index.md mtime 铁证）。
镜像同步随后把坏索引传播到 Obsidian——污染是双库的。

## 二、施工内容

1. **living_notes 索引路径动态化**：废除 INDEX_PATH 快照常量，改 `_index_path()`
   函数在调用时从当前 LIBRARY_DIR 解析；全文件引用点改完。
2. **同类审计**：全项目扫描"import 时由可变目录常量派生的路径常量"
   （已知嫌疑：`tools/memory_mirror.py` MIRROR_PATH / MEMORY_DB 同源问题——
   考试时 Kimi 被迫同时 patch 两个模块才封住污染，见 GC1 runner 注释）。
   列出清单，一并动态化或论证保留。
3. **回归测试 `test_never_writes_real_index`**：
   patched LIBRARY_DIR=tmp 下跑 write_living_notes 全流程，
   断言真实 `library/index.md` mtime 与内容**零改动**。
4. 审计清单落盘 `docs/recon/path-constant-split-brain.md`。

## 三、验收标准

1. 回归测试通过且能证明修复前会失败（施工报告中给出修复前复现输出）；
2. 全量 pytest 零回归，且**跑完全量后真实 index.md 内容不变**（终审实测）；
3. 审计清单覆盖 tools/ 与 core/ 全部 path 常量；
4. 分支停靠未 merge/push。

## 四、禁止项

- 禁止只改 INDEX_PATH 不做同类审计（这个 bug 是模式，不是个例）；
- 禁止改笔记正文内容；
- 禁止 merge/push。
