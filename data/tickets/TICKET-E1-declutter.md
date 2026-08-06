# 票 TICKET-E1：熵减计划第 1 波——清垃圾 + 移出 + 归档

## 纪律（最高优先级）

- 从最新 main 切 `chore/entropy-wave1-declutter`，开工先 `git branch --show-current`
- ⛔ 禁止 merge、禁止 push 到 main，完成后归位等 Kimi 终审
- **删除前先生成快照清单**（见验收 1），任何一项与清单不符立即停手报告
- 本票只动文件位置，不改一行代码逻辑

## 起点标记

`entropy-plan-start` 标签已打在 eb52a5f（已推送 GitHub）。
回溯熵减前状态：`git checkout entropy-plan-start`

## D 栏：删除（可再生 / 纯垃圾）

| # | 项 | 说明 |
|---|----|------|
| D1 | `build/` | setuptools 中间产物 |
| D2 | `dist/` | 打包产物 |
| D3 | `bobo_agent.egg-info/` | pip 元数据再生品 |
| D4 | `pyanalyzer-report.json` + `pyanalyzer-report.md`（根目录） | 7月19日陈旧报告 |
| D5 | `git stash drop` stash@{0} 与 stash@{1}（025 WIP 两条，已被 026 消化） | drop 前必须 `git stash show -p` 把内容附进五查汇报 |
| D6 | `git worktree remove /private/tmp/ticket016-parent --force` + `git worktree prune` | 废弃审查现场 |
| D7 | 项目内所有 `__pycache__/`（排除 .venv 与 node_modules 内的） | 字节码缓存 |

## M 栏：移出（不可再生，移到项目外隔离区，不删）

隔离区：`~/Desktop/_entropy_quarantine_20260806/`（先 mkdir）

| # | 项 | 体积 |
|---|----|------|
| M1 | `crmeb_arena/` → 隔离区 | 428M，别人的项目，禁止删除 |
| M2 | `projects/code_20260616_*` → 隔离区 | 13M，1376 个目录的 6 月碎片 |

## R 栏：归档（项目内挪位）

| # | 项 | 目标 |
|---|----|------|
| R1 | `scripts/analyze_prompt_budget.py`、`context_lab.py`、`smoke_boot.py` | → `docs/战役工具/`（git mv，保留历史） |

## 明确不碰

- `data/logs/` 全部（log 专项讨论未定案）
- `apps/desktop/`（方向未定）
- 任何 .py/.ts 代码内容

## 验收

1. **快照证据**：施工前 `du -sh` + `git status` + `ls` 清单附五查汇报；
   施工后同口径对比，证明只动了清单内项
2. D5 的 stash 内容全文附汇报（最后一眼）
3. 全量 pytest 零回归（基线 1474 passed / 2 skipped）
4. `bobo` 启动链路验证：`/opt/homebrew/opt/python@3.14/bin/python3.14 -c "from bobo_tui_gateway.entry import main"` 无报错
5. ui-tui typecheck 不增新错（基线 3 错）
6. 五查汇报含 git status 原文 + git branch --show-current 原文
