# Git Workflow Standard v1

> keywords: git, GitHub, push, commit, merge, branch, 提交, 合并, 推送, 分支, PR, pull request, 回退, 回滚, undo, revert
> excludes: 新版本, 发布了, 更新了什么, 有什么新功能
> 价值: 用户要做 git 操作（提交/合并/回退/分支）时命中 → 约束提交纪律与回滚安全（"软件新版本"讨论不注入）
> Bobo 在做任何 Git 操作时必须遵守本文档。本文件是硬约束，不是建议。
>
> **工作流（必须遵守，不可跳过）**：
> 1. 操作前 → git status + git fetch 确认当前状态
> 2. 改代码前 → 切新分支（从 main），永远不在 main 上直接修改
> 3. 改完后 → commit + 打回滚标签，然后 merge 回 main
> 4. push → 推 main + 推标签，确认远程同步
> 5. 记录 → 改动记入 Obsidian 开发手册
> 禁止在 main 上直接修改。禁止 merge 前不 push。禁止不创建回滚标签就 merge。
>
> **设计哲学**：每一次改动都要有回溯空间。main 只接受来自 feature 分支的 merge。没有回滚标签的 merge 等于裸奔——出问题时你没有任何办法回到 merge 之前的状态。宁可多打一个标签，不要少留一条退路。

## 约束

### 绝对禁止（违反任一条 = 不合格）

- ❌ 在 main 分支上直接 `git commit`——所有修改必须在 feature/fix 分支上进行
- ❌ 不带回滚标签就 merge 到 main——每次 merge 前必须 `git tag rollback-xxx-YYYYMMDD-HHMMSS`
- ❌ `git push --force` 到 main 或任何共享分支
- ❌ 不先 fetch 就操作——每次操作前必须 `git fetch origin` 确认远程状态
- ❌ merge 前不确认当前分支——避免误 merge 到错误的分支
- ❌ 修改提交历史（rebase, amend, reset --hard）——已经 push 的 commit 就是历史，不要改
- ❌ 提交包含 API key、密码、token 等敏感信息

### 必须遵守

- Git 操作前必须先 `git status` + `git fetch origin`
- Branch 命名规范：`feat/`（新功能）、`fix/`（修复）、`refactor/`（重构）
- Commit message 格式：
  ```
  <type>: <简短描述（≤50字，中文）>
  
  <详细说明（可选）>
  
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  ```
- 每次 merge 到 main 后必须 push main + push 回滚标签
- Merge 使用 `--no-ff`（保留分支历史，便于回溯）

## 工作流状态机

### Phase 1: 操作前检查（CHECK）

**目标**：确认当前状态，避免意外操作。

**步骤**：
1. `git status` — 查看当前分支、未提交的改动、未跟踪的文件
2. `git fetch origin` — 确认本地与远程是否同步
3. 检查是否有未提交的改动：
   - 有 → 先提交或 stash
   - 无 → 继续
4. 如果当前分支不是 main 且需要切回 main，先确认没有未 push 的 commits：
   ```
   git log origin/当前分支..当前分支
   ```
   有未 push 的 commits → 先 push 再切分支

### Phase 2: 开始工作（START）

**目标**：在独立分支上工作，保护 main 的稳定性。

**步骤**：
1. `git checkout main && git pull origin main` — 确保 main 是最新的
2. `git checkout -b <type>/<描述>` — 创建新分支
   - Feature: `feat/skill-auto-discovery`
   - Fix: `fix/compression-crash`
   - Refactor: `refactor/clean-engine-history`
3. 在新分支上进行修改

### Phase 3: 提交改动（COMMIT）

**目标**：将改动记录为清晰的 commit。

**步骤**：
1. `git add` 只 stage 相关文件，不一股脑 `git add -A`
2. `git diff --cached` 过一遍改动，确认没有意外内容
3. `git commit -m "..."` 按规范写 commit message
4. **如果有多个独立改动**，拆成多个 commit 而不是一个大 commit

### Phase 4: 合并前准备（PRE-MERGE）

**目标**：确保有回溯空间，远程已同步。

**步骤**：
1. 在 feature 分支上：
   ```
   git push origin feat/xxx   # push feature 分支到远程
   git checkout main
   git pull origin main        # 拉取最新 main
   ```
2. 在 main 上 merge feature 分支：
   ```
   git merge feat/xxx --no-ff -m "merge: <描述>"
   ```
3. **Merge 成功后立即打回滚标签**：
   ```
   git tag "rollback-<feature名>-$(date +%Y%m%d-%H%M%S)"
   ```

### Phase 5: 推送 & 验证（PUSH & VERIFY）

**目标**：确保远程仓库反映本地状态。

**步骤**：
1. `git push origin main` — 推 main 分支
2. `git push origin <回滚标签名>` — 推回滚标签
3. `git log --oneline -3` — 确认 commit 历史正确
4. 可选：清理已合并的本地分支 `git branch -d feat/xxx`

## 紧急情况处理

### 需要回滚

```bash
# 查看所有标签
git tag | grep rollback

# 回到某个标签（创建新分支用于检查）
git checkout -b recovery-branch rollback-xxx-YYYYMMDD

# 如果确认恢复，merge 回 main
git checkout main
git merge recovery-branch --no-ff -m "merge: 回滚到 rollback-xxx"
```

### Merge 冲突

1. 不要慌，不要 force push
2. `git status` 查看冲突文件
3. 手动解决冲突后 `git add` + `git commit`
4. 继续正常的 merge 流程

## 验收

- [ ] `git status` 在执行任何操作前检查过
- [ ] `git fetch origin` 确认了远程同步
- [ ] 没有在 main 上直接 commit
- [ ] Branch 命名符合 `feat/` / `fix/` / `refactor/` 规范
- [ ] Commit message 格式正确
- [ ] Merge 使用了 `--no-ff`
- [ ] 回滚标签已创建并推送
- [ ] Main 和标签都已 push 到远程
