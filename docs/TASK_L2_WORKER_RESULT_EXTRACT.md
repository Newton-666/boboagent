# TASK_L2_WORKER_RESULT_EXTRACT — L2 任务单 ①：Worker 结果提取拼接修复

> 2026-07-27 Kimi 出单。**首个 L2 级任务**（小 bug、单文件、几行），
> 验收走 duo B——这是 duo B 验收链路第一次实战。
> 背景：/duo 商讨中 B 收到的 A 方案是元描述残句（"方案已完整提出……"），
> 根因：`_extract_worker_result` 只取最后一条 assistant 消息，
> 分多轮产出的方案正文丢失。铁证：tools/spawn_worker.py:131-139。

## 任务文本（粘贴给 bobo）

```
任务：修复 Worker 结果提取丢失多轮产出（feat/fix-worker-result-extract 分支）

工作目录：/Users/niuqingwei/Desktop/BOBO_Project_Backup

根因（已定位，先读代码确认再动手）：
tools/spawn_worker.py 的 _extract_worker_result（约 131-139 行）
用 reversed(history) 找到第一条 assistant 消息就返回。
当 Worker 的产出分多条 assistant 消息时（长方案拆轮、末轮是
"方案已完整提出"式收尾），只抓到最后一条残句，正文丢失。
/duo 商讨中 B 因此收到空壳方案。

要求：
1. git checkout -b feat/fix-worker-result-extract，全程在该分支
2. 先 read_local_file 读 _extract_worker_result 及其调用方，确认理解
3. 修复：提取器应拼接 worker 的全部 assistant 消息内容
   （而非只取最后一条）。注意：
   - 有工具调用的 worker：assistant 消息里夹杂的过程性文字
     要有合理取舍（工具轮的过渡语不该污染结果），想清楚取舍规则
     并在 commit message 里说明
   - 保持现有"没有回复时返回 (Worker 没有产生回复)"的行为
4. 补测试：构造一个多 assistant 消息的 history，断言拼接后的
   结果包含所有轮次的正文；再构造单轮 history 确认行为不变
5. ./.venv/bin/python3 -m pytest tests/ -q 全绿
6. 在 feat 分支上 commit，输出五查汇报（表格格式，每项附证据），然后停

验收标准（逐条可判定）：
① _extract_worker_result 不再"只取最后一条"——多轮 history 的
   拼接结果包含每轮正文
② 有工具调用的场景取舍规则明确（commit message 说明）
③ 新增测试覆盖：多轮拼接 + 单轮回归
④ pytest 全绿
⑤ git branch / git status 证明 commit 在 feat 分支、main 未动
⑥ 五查汇报表格齐全，汇报后停止
```

## 我（Kimi）验收时的独立检查

- 自己构造多轮 history 直调 _extract_worker_result，看拼接结果
- 看 diff：只许动提取逻辑 + 测试，顺手重构 = 打回
- `git log main --oneline -1` 确认 main 未动（当前 729f121）
- 全量重跑 pytest

## duo B 验收（L2 流程新增环节）

bobo 交付、我初审通过后，把 diff + 汇报贴给 duo B 挑刺：
- B 重点：拼接规则在有工具轮时是否合理？有没有边界 case 漏掉
  （空 content、whitespace-only、tool_calls 消息无 content）？
- B 通过 → 用户终审合并；B 打回 → 打回点写清，bobo 修

## 通过后的意义

- L1→L2 正式解锁（此前 L1 两次成功）
- duo B 验收链路首次实战
- /duo 商讨的 A→B 转播恢复完整，后续"问题雷达"等场景才可信
