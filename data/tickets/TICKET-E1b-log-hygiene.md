# 票 TICKET-E1b：log 卫生——stack_dump 环形快照 + 大战卷宗归档

## 背景

熵减 log 专项（owner 2026-08-07 拍板，四项全决）：

| 项 | 决定 |
|----|------|
| L1 stack_dump.log | **环形快照**：覆盖写，恒定 ~50KB；BOBO_STACK_DUMP=1 切回全量连拍（战时模式） |
| L2 大战卷宗 | bobo.log.2026-07-27 ~ 2026-08-01 压缩归档 docs/战役卷宗/ |
| L3 bobo.log 轮转 | 维持 TimedRotatingFileHandler backupCount=7，不动 |
| L4 events.jsonl | 永不删，>50M 再议压缩，不动 |

## 病灶

`bobo_tui_gateway/entry.py:55-63`：faulthandler 每 120 秒全线程堆栈
**追加**写入 stack_dump.log，无上限——战时探针病愈忘停（7.1M 且日增 ~1-2M）。

## 目标

### A. 环形快照（entry.py 改造）

- 默认模式：后台线程每 120 秒，以 **"w" 覆盖模式**打开 stack_dump.log，
  `faulthandler.dump_traceback(file=fd)` 写一屏，关闭。文件恒定只留最新一屏。
- `BOBO_STACK_DUMP=1`：保留现有 repeat 追加模式（全量连拍，战时排查用）。
- 两种模式都要在进程退出时干净收尾（atexit/daemon 线程）。
- 现有 7.1M 的 stack_dump.log：截断清零（旧内容全是"一切正常"废片，
  无考古价值——大战卷宗已由 L2 保管在 bobo.log 里）。

### B. 大战卷宗归档

- `data/logs/bobo.log.2026-07-27` ~ `bobo.log.2026-08-01`（共 6 个）
  → gzip 压缩移入 `docs/战役卷宗/`（git add -f，与 Obsidian 手册第十八章互证）。

## 边界（不碰）

- bobo.log 轮转配置、events.jsonl、其他任何日志逻辑
- core/、tools/ 一行不动（与 E2b 并行施工不冲突）

## 验收

1. 默认模式启动 gateway，等 ≥2 个写周期：stack_dump.log 只含最新一屏
   （文件以最近一次覆盖为准，mtime 更新、体积不累积）
2. BOBO_STACK_DUMP=1 启动：追加模式行为与旧版一致
3. 卡死场景破案能力验证：人为造一个线程阻塞（sleep 600），
   下一屏快照里能看到该线程堆栈
4. docs/战役卷宗/ 含 6 个 .gz，原 data/logs/ 对应文件已移出
5. 全量 pytest 零回归（基线 1474 passed / 2 skipped）
6. 改 gateway 入口 → 五查第 6 项填"是，需重启"

## 纪律

- 从最新 main 切 `chore/ticket-e1b-log-hygiene`，开工先 `git branch --show-current`
- ⛔ 禁止 merge、禁止 push 到 main，完成后停手等 Kimi 终审
- 五查汇报含 git status 原文 + git branch --show-current 原文
