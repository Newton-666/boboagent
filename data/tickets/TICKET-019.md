# 票 TICKET-019：MAX_STEPS 默认 200 → 500 + 提醒节奏适配

## 背景

用户要求工具调用轮次上限 200 → 500（skill 创建类重任务 200 步不够用）。
`core/engine.py:74`：`MAX_STEPS = int(os.environ.get("BOBO_MAX_STEPS", 200))`。

## 目标

1. 默认值 200 → 500（环境变量覆盖逻辑不动）
2. **步数提醒节奏适配**（engine.py:1264 附近）：现状 ≥50 步后每 5 步刷一次
   "已用 x/200 步"，500 步下会刷 90 次屏。改为：
   - ≥100 步后每 25 步提醒一次
   - 达到 80% 上限（400 步）后每 10 步提醒（临近熔断加密）
3. 确认与票 W 熔断逻辑兼容：`_step_count > MAX_STEPS` 的收尾模板里的
   数字必须跟随新上限（若为硬编码 200 一并改）

## 验收

1. 无环境变量时 MAX_STEPS == 500；BOBO_MAX_STEPS=300 时 == 300
2. 提醒节奏单测：mock _step_count 验证 100/125/150… 提醒、400/410/420… 加密提醒
3. 全量 pytest 零回归（基线 1429 passed / 2 skipped）
4. 改 core/ → 五查第 6 项填"是，需重启"

## 纪律

- 从最新 main 切 `fix/ticket-019-max-steps-500`，开工先 `git branch --show-current`
- 五查汇报含 git status 原文 + git branch --show-current 原文
- ⛔ 禁止 merge、禁止 push，完成后 `git checkout main` 归位，等 Kimi 终审
