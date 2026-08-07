# TICKET-E4a — living_notes 自动管道失语诊断与修复

- 分支：`fix/ticket-e4a-living-notes-silence`（从最新 main 切出）
- 类型：熵减计划 · 闸门 A 基线补考（A4 观测点挂科根修）
- 纪律：禁止 merge、禁止 push、禁止碰 main；完成后五查汇报等 Kimi 终审
- 基线：1494 passed / 2 skipped

## 背景（Kimi 已核实的既定事实）

**案情**：2026-08-07 19:04 会话（sid 20260807_190425_b358d2，kimi-k3）完成了一个完整多步骤任务（todo-cli：13 个 pytest 全绿），但 library/ 主库**没有任何笔记沉淀**——没有 notes.written 事件、没有 takeaway 事件（该 sid 全程 0 条 takeaway 相关事件）、library/ 无新文件。

**管道结构**（已核实）：
- `core/engine.py` 约 1036–1062 行：LN-2 钩子，每轮收工时提取 takeaways，非空则调 `tools/living_notes.py::write_living_notes()`（自动写项目 library/，含 judge LLM 判定、主题合并、版本快照、索引重建）
- **唯一的 takeaway 事件是 19:03 另一会话的 `takeaway.skipped {reason: local_gate}`**——说明跳过时会留事件，但目标会话连"跳过"事件都没有
- 致命嫌疑：`core/engine.py` 约 1061 行 `except Exception: pass`——钩子的注释自己写着"内部已保证失败静默降级（WARNING + notes.error）"，但**外层这个裸 except 把包括 notes.error 在内的一切无声吞掉**

## 施工清单

### A. 先取证（不许先改代码）
1. 用代码走读 + 日志考古回答三个问题，全部写进汇报：
   - 目标会话每轮收工时 takeaways 提取到底产出了什么？（`_extract_takeaways` 的触发条件、`local_gate` 的判定逻辑是什么、什么条件会连 skipped 事件都不留）
   - 如果 takeaways 非空，`write_living_notes` 会被调到吗？judge LLM 会怎么判？
   - 是否存在被裸 except 吞掉异常的可能性？（构造一个会让 write_living_notes 抛异常的输入，实证异常确实无声消失）
2. 允许写一个临时复现脚本（tests/ 外、用完即删或归入 tests/fixtures），用目标会话的真实历史最后 4 条消息重放 takeaways 提取与 living_notes 判定，记录每一步输出。

### B. 修复
3. `core/engine.py` 裸 `except Exception: pass`（living_notes 钩子处）改为：WARNING 日志 + `notes.error` 事件（含 error 信息与 sid）——与钩子上方注释承诺的纪律对齐。takeaways 提取的 except 同样排查一遍，同标准处理。
4. 根据 A 的取证结论修复根因（可能是 gate 误判、可能是事件缺失、可能是异常吞噬）。根因是什么就修什么，汇报里必须写清"根因是 X，证据是 Y"。
5. `takeaway.skipped` / `notes.*` 事件链补全：保证"每轮收工时管道要么产出笔记、要么留下为什么不产出的明确事件"——**不允许再出现零事件的静默轮**。

### C. 验收测试（新增）
6. 裸 except 已修：注入一个会抛异常的 write_living_notes（monkeypatch），断言 WARNING 日志 + notes.error 事件产出，且引擎不炸。
7. 闸门回归：构造"明显值得记"的收工场景（多步骤任务完成），断言管道产生 notes.written 或带明确 reason 的 skipped 事件——不允许静默。
8. 全量 pytest 零回归（基线 1494）。

### D. 实证（Kimi 终审时配合）
9. 修完后 Kimi 会让 bobo 跑一个真实小任务，现场验证笔记自动落 library/（A4 补考）。

## 边界（不许碰）
- living_notes 的主题合并/版本快照/索引重建算法本身（除非 A 取证证明根因在其中，且只修根因涉及的最小范围）。
- GUIDANCE、injector、记忆系统。
- `write_obsidian`（Obsidian 分馆通路，与本票无关）。

## 五查汇报要求
1. A 项三问的答案 + 重放脚本输出（罪证）。
2. 根因陈述："根因是 X，证据是 Y"。
3. 每处修改的 before/after。
4. 新增测试列表 + 全量 pytest 输出。
5. 分支/commit/工作区状态原文 + 是否需重启。
