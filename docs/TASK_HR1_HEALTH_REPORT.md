# 票 HR-1：夜班体检报告

> 状态：待开工
> 前置：宪法十六章（可观测支柱）+ LIVING_NOTES_DESIGN.md Q1（定期整理并入体检）
> 分支：`feat/health-report`（从最新 main 新建）

## 目标

每天一份 bobo 健康日报：挖前一天的 events.jsonl + 扫描 library/ 治理状态，
生成人话 markdown 报告，落盘 `library/健康日报/YYYY-MM-DD.md`。
**MVP 纯统计，零 LLM 调用**（确定性、零成本；叙事化总结以后再说）。

## 触发方式（两个都要）

1. **启动补报**：engine_adapter 初始化时（LN-1 导入钩子附近），检查
   `library/健康日报/` 是否缺昨天的报告，缺则生成
   （覆盖"每天第一次启动补昨晚"场景，无需外部 cron）。
2. **手动**：`./.venv/bin/python3 -m tools.health_report [YYYY-MM-DD]`
   可生成指定日期报告（默认昨天）。

幂等：同日重复生成 → 全量覆盖重写（内容一致）。

## 报告内容（三个板块）

### 板块 1：引擎健康（events.jsonl 按日聚合）

| 指标 | 来源事件 |
|---|---|
| 回合数 / completed / max_steps / 异常退出 | engine.thread.exit 按 reason 分类计数 |
| 步数熔断次数 + 涉及会话 | engine.step_fuse |
| 收工闸触发：无账检测/承诺检测/熔断放行 | goal_gate.* 分类计数 |
| LLM 调用数 / 错误分类（rate_limit/balance/stream_stall/headers_stall）| llm.call / llm.stream_stall / llm.headers_stall |
| 工具调用总数 / 失败数 | tool.exec（若有 status 字段则分成败）|
| 上下文压缩次数 + 压缩前后条数 | context.compressed |

### 板块 2：知识库治理（library/ 扫描）

- 主题笔记总数、昨日新增（按 frontmatter created/last_touched）
- **疑似重复主题**：主题名规范化后编辑距离 ≤2 或互相包含的对子
- **孤儿笔记**：无 frontmatter 或缺 topic 字段的 md
- **90 天未触达**：last_touched 距今 >90 天的清单（MVP 时期大概率无）
- MEMORY.md 条目数 / 草稿数 / 信号 <20 不再注入数（读 knowledge_base.json）

### 板块 3：异常关注（需要用户或开发者看一眼的事）

自动列出"值得看"的异常，如：熔断放行发生、balance_error 出现、
mirror_import_failed、notes.error、任何 error 级事件 top 5。

## 实现

新模块 `tools/health_report.py`：
- `generate_report(date_str, *, events_path=None, library_dir=None) -> Path`
  参数可注入（测试用 tmpdir）
- 事件解析容错：坏行跳过不炸；events.jsonl 不存在 → 板块 1 标"无数据"
- 失败静默降级：报告生成失败记 WARNING，不影响启动
- 事件埋点：`health.reported`（date、sections ok）

报告格式示例：

```markdown
# 夜班体检 · 2026-07-30
## 引擎健康
- 回合 12 次：completed 10 / max_steps 1 / 异常 1
- 收工闸：无账检测 3 次，熔断放行 1 次 ⚠️
## 知识库治理
- 主题笔记 8 篇（昨日 +2）；疑似重复：「收工闸」~「收工闸门」
## 异常关注
- ⚠️ 14:32 balance_error 出现 1 次（DeepSeek 余额不足）
```

## 验收金标准（tests/test_health_report.py，tmpdir 全物理）

1. 造 20 行假事件（含 exit/fuse/gate/compressed）→ 报告数字与手工核算一致
2. events.jsonl 不存在 → 报告仍生成，板块 1 标"无数据"，不炸
3. 坏行混入 → 跳过，统计不含坏行
4. 假 library（3 篇笔记含一对疑似重复 + 1 篇无 frontmatter）→
   治理板块全部命中
5. 幂等：同数据跑两次，报告内容逐字节一致（日期相关字段固定时）
6. 启动补报钩子：缺昨天报告 → 自动生成；已存在 → 不重复生成
7. `python -m tools.health_report` 手动模式可跑（指定日期）
8. 全量 pytest 通过，零回归

## 边界

- 零 LLM 调用，叙事化不做
- 不做通知推送、不做阈值告警（先看几天报告再定什么算异常）
- engine_adapter 只加补报钩子（try/except），逻辑全在 health_report.py
- `library/健康日报/` 与普通主题笔记共存即可，`_existing_topics`
  已按目录扫描，健康日报会出现在主题清单里——**要在 living_notes 的
  _existing_topics 中排除"健康日报"目录**（日报不是讨论主题），
  本票含这个小改动。

## 纪律

- 开工前 `git branch --show-current` 确认在 `feat/health-report`。
- 完成后五查汇报（含 git status 原文 + git branch --show-current 原文），
  ⛔️ 禁止 merge、禁止 push，等 Kimi 终审。
- 改了 core/ → 五查第 6 项填"是，需重启生效"。
