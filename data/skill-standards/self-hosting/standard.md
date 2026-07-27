# Self-Hosting Standard v1（bobo 改 bobo 铁律）

> keywords: BOBO_Project_Backup, boboagent, 自迭代, self-hosting, bobo 源码, bobo 自己, feat/, 改 bobo
> requires: git-workflow
> 当任务涉及修改 bobo 自身源码（BOBO_Project_Backup 仓库）时必须遵守本文档。本文件是硬约束，不是建议。
> 完整手册见 docs/SELF_HOSTING.md，本文是执行时的不可逾越红线摘要。

## 停止线（最高优先级，违反任一条 = 任务失败）

git 权限边界——以下四个动作**只有用户能做**，bobo 永远不许执行：

- ❌ `git checkout main`（或任何切回 main 的操作）
- ❌ `git merge`
- ❌ `git push`（任何远端推送）
- ❌ `git branch -d` / 删除分支

允许且必须做的：

- ✅ 在用户指定的 `feat/xxx` 分支上工作
- ✅ **在 feat 分支上 commit**（改动必须 commit 干净，不留脏工作区）
- ✅ 汇报（五查证据 + diff 摘要 + 测试结果）
- ✅ 然后**停**。等用户审查合并。

- ❌ 禁止带脏工作区切分支（改动未 commit 就 checkout = 假分支工作）
- ❌ 禁止汇报里写"等用户 merge"然后自己动手——说好规矩又违反规矩，比不懂规矩更糟（2026-07-27 首秀教训：bobo 自行 merge + push 到 origin/main + 删分支）

## 完成定义

任务完成 = 分支上 commit 干净 + **输出完整五查汇报（表格格式，每项附证据）** + **停**。
"完成"绝不包含合并、推送、清理分支。
- **一个分支一个任务，完成即停**：五查汇报 = 任务终点。汇报后不得自行切到下一个 ticket/分支/任务。即便还有待办，也必须等用户审查完当前分支后再派发。多 ticket 由用户逐个分配，不是 Bobo 逐个执行。
- **禁止跳过五查汇报直接说"完成了"**：没有表格格式的五查汇报 = 任务未完成。即使代码已 commit、测试已跑完，也必须补全汇报再停。

## 其他硬约束

- **没有任务单不动手**：验收标准必须预先写死且可判定，"看看有没有问题"不是任务
- **永远不许直接动 main 分支**
- **改工具前先确认注册名和调用链**：obsidian 写工具是 `write_obsidian.py` / `append_obsidian.py`，不是 file_writer.py
- **TUI 改动需构建**：动 `ui-tui/src` 后必须 `npm run build` 且产物同步到运行路径
- **editable install**：改动重启 bobo 才生效，汇报时必须提醒用户重启验证
- **分析代码前先读实现**：声称某个方法的内部行为（如"逐条调LLM"、"调用次数"、算法复杂度）之前，必须用 `read_local_file` 实际阅读该方法的源码。禁止仅凭 `grep` 方法名/函数签名推断行为。这条对架构分析、性能评估、代码审查同样适用。
- 测试底线：`pytest tests/ -q` 全绿（用仓库 `.venv/bin/python3`）；打回必留测试

## 汇报格式（强制，禁止省略）

完成 commit 后，**必须**输出以下格式的五查汇报，这是任务终点，不是可选项：

```
#    检查项        结果
───  ────────────  ─────────────────────────────────────────
1    编译闸        python3 -m py_compile 全部通过 / 有 N 个失败
2    通路验证      改动被调用到的证据（工具名/函数名 + 调用链）
3    真实运行      pytest tests/ -q: N passed, M skipped
4    环境一致性    确认分支名、工作区路径、无第二副本
5    证据式自报    git log --oneline -2 + git branch 输出
```

每项必须有具体结果（数字、路径、输出），禁止"通过了""没问题"等无证据表述。五项全部输出后说"已停止。未 merge、未 push main、未删分支。"然后停。
