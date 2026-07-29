# 票 Y 任务台账 — 上下文实验台

**分支**: feat/context-lab
**创建**: 2026-07-29
**状态**: ✅ 完成

## 检查清单

- [x] `git branch --show-current` → feat/context-lab
- [x] 建分支 feat/context-lab
- [x] 建台账
- [x] 写 scripts/context_lab.py（分析器 — 452行）
- [x] 写 tests/test_context_lab.py（测试 — 17条用例）
- [x] 写 docs/context-lab-plan.md（实验方案 — 4个实验）
- [x] 跑真实 events.jsonl 验收 — 12737事件/389会话, JSON导出正确
- [x] 跑全量测试 — 1064 passed, 17 context_lab tests passed
- [x] 五查汇报 + git status + git branch --show-current
- [x] commit 后 git checkout main 归位

## 交付物

| 文件 | 大小 | 说明 |
|------|------|------|
| `scripts/context_lab.py` | 14.9KB | 终端+JSON双模式分析器 |
| `tests/test_context_lab.py` | 7.3KB | 17 条测试用例，full coverage |
| `docs/context-lab-plan.md` | 1.3KB | 四个实验 + budget 灵敏度方案 |

## 真实数据运行摘要（2026-07-29）

- 389 会话，17 个真实会话（非 boot-）
- 最大会话：`20260728_154112` — 343 LLM 调用，22.4M prompt_tokens
- context.compressed：当前无事件（票 T 刚合，需等积累）
- 当前 budget=60 验证：avg_token_per_round 受 boot- 沾污影响偏大，实际值需等压缩事件积累后重新评估
