# TICKET-D1 复盘笔记正规管道重写（绕管道二犯纠正票）

> 分支：`fix/ticket-d1-note-via-pipeline`（从最新 main 切出）
> 性质：流程纠正 + 管道实弹演练。工作量小，但纪律意义大。

## 一、背景

2026-08-09 10:43，bobo 手写 `library/项目复盘/exam明牌考试方法论错误复盘.md`，
**绕开 living_notes 正规管道**（无 notes.written 事件、index.md 未收录、
镜像未同步、library git 未提交）。这是第二次犯同一错误
（第一次：08-07 手写《压缩体系战役复盘》，台账 05/06 项的教训）。

手写文件 = 管道的暗物质：索引看不到它、镜像没有它、版本库不知道它。
血案之后才立的 G1 版本化保底，绕管道写入直接让它形同虚设。

## 二、施工内容（两步，不许多做）

1. 删除手写文件 `library/项目复盘/exam明牌考试方法论错误复盘.md`
   （内容先读出来备好，下一步重写要用）；
2. 用 `write_living_notes()` 正规管道重写同一主题的复盘笔记
   （judge 成文、frontmatter、版本、sid 事件全流程）。

## 三、验收标准（终审逐条核验）

1. events.jsonl 出现本次 `notes.written` 事件（带 sid）；
2. `library/index.md` 的「项目复盘」分区出现该笔记条目；
3. Obsidian 镜像侧对应路径出现该笔记（带 MIRROR 头）；
4. `git -C library log --oneline` 出现对应 auto 提交（G1 钩子联动）；
5. 全量 pytest 零回归（本票不应触碰任何代码，若碰了必须说明理由）。

## 四、禁止项

- 禁止手写/手改 library/ 下任何笔记文件（包括 index.md）；
- 禁止改代码（除非复跑中发现管道真 bug——发现则停工汇报，另开修复票）；
- 禁止 merge/push。

## 五、附带自省（写进复盘笔记末尾）

为什么又绕了管道：上次立的"正确做法"里没有把自己绑进管道。
以后凡是"写工作记忆/复盘笔记"的冲动，第一反应必须是
write_living_notes，而不是 file_operation。
