# TASK_L4_GIT_PUSH_GATE — push/毁灭性命令物理闸（仅 bobo 自身仓库）

> 2026-07-27 Kimi 出单。L4 级（动 command_safety 安全核心）——bobo 执行，
> Kimi 独立审查，出问题用户 revert。
> 背景：prompt 层停止线两次失守（首秀 merge+push、L2① 收尾顺手 merge）。
> v2 规矩：本地 merge 放宽，push / reset --hard / clean -f 死守。
> 死守不能只靠 prompt，要有物理闸。**闸只对 bobo 自己的仓库生效，
> 操作其他项目仓库时 git 全量放行（用户明确要求）。**

## 现状事实（我已读码确认）

- `core/command_safety.py` 的 `classify_command(command)` 是纯字符串分类器，
  不知道命令在哪个仓库执行
- 现有黑名单已有 `git push .*--force`（全局），普通 push 不拦
- `is_high_risk_tool` 是分类器入口，execute_terminal / shell.exec 都走它
- 仓库根 = `core/` 的上级目录（与 duo_orchestrator._PROJECT_ROOT 同款取法）

## 任务文本（粘贴给 bobo）

```
任务：git push/毁灭性命令物理闸——仅 bobo 自身仓库生效
（feat/self-repo-git-gate 分支）

工作目录：/Users/niuqingwei/Desktop/BOBO_Project_Backup

背景：self-hosting v2 规矩允许 bobo 本地 merge，但 git push、
git reset --hard、git clean -f 在 bobo 自己的仓库里只有用户能做。
prompt 层两次失守，需要在 command_safety 层加物理闸。
关键约束：闸只对 BOBO_Project_Backup 这个仓库生效；
在其他任何项目目录里，git push 等操作必须照常放行。

已确认的现状（先读码核实再动手）：
- core/command_safety.py 的 classify_command 是纯字符串分类，
  无仓库上下文；is_high_risk_tool 是入口
- 黑名单已有 git push --force 全局拦截，普通 push 目前不拦

要求：
1. git checkout -b feat/self-repo-git-gate，全程在该分支
2. 先读 command_safety.py 全文 + is_high_risk_tool 的调用方，
   搞清楚 execute_terminal 执行时的 cwd 从哪里来（调用链要读出来，
   不许猜）
3. 实现"自身仓库判定"：给定命令和 cwd，判定命令作用的 git 仓库
   是否为仓库根（core/ 的上级）。至少处理三种形态：
   a. 在仓库内（含子目录）直接 git push
   b. git -C <路径> push
   c. cd <路径> && git push 链式命令
   判定方法建议：解析目标路径 → 向上找 .git → 与仓库根比较。
   想不清楚的边界形态宁可放行（误伤日常 git 比漏拦更糟——
   漏拦还有 prompt 层和 reflog，误伤会让 bobo 在别的项目残废）
4. 命中自身仓库时：git push（任何形式）、git reset --hard、
   git clean -f → dangerous，原因写"bobo 自身仓库：push/毁灭性
   操作仅限用户（self-hosting v2）"
5. 其他仓库：行为与现状完全一致（除了已有的 --force 全局黑名单）
6. 补测试（tests/ 下新建或加入现有安全测试文件）：
   - 仓库根 + 子目录下 git push → dangerous
   - git -C 指向仓库根 push → dangerous
   - cd 进仓库 && git push → dangerous
   - /tmp 或其他路径下 git push → 放行（非 dangerous）
   - 仓库内 git reset --hard / git clean -f → dangerous
   - 仓库内正常 git 操作（status/log/merge/checkout -b）→ safe 照旧
7. ./.venv/bin/python3 -m pytest tests/ -q 全绿
8. 在 feat 分支上 commit，输出五查汇报（表格），然后停
   （v2 规矩：汇报后允许本地 merge，禁止 push）

验收标准（逐条可判定）：
① 三种命令形态（直接/-C/cd 链）在自身仓库 push 全部 dangerous
② 其他路径 push 放行——测试里必须有一个非仓库路径的证据
③ 正常 git 操作零误伤（现状测试 + 新增 safe 断言）
④ "想不清楚就放行"原则在 commit message 里体现
⑤ pytest 全绿
⑥ 五查汇报表格齐全，未 push
```

## 我（Kimi）审查时的独立检查

- 直调 classify_command/is_high_risk_tool 构造六种形态命令实测
- 重点查 cwd 传递链：execute_terminal 实际执行目录和判定用目录
  是否同一个（不一致 = 闸形同虚设或误伤）
- 检查有没有顺手把 SAFE_COMMANDS 里的 "git" 动了（误伤全局）
- git log main 确认无越权 push

## 风险备案

- 最大风险是误伤（其他项目 git 残废）→ 验收标准②③就是防线
- 闸本身是代码，bug 可 revert；本次由 Kimi 全量审查后才 merge
