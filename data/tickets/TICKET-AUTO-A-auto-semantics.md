# TICKET-AUTO-A：auto 语义改造（AUTO MODE 票 A，三票之首）

> 立案：2026-08-09 · 依据《AUTO MODE 定稿 v0.6》+《v0.6.1 施工前置项》（Obsidian Bobo数据库）
> 纪律：branch 施工（feat/ticket-auto-a）、五查汇报、未终审不 merge 不 push
> 前置阅读：v0.6 定稿全文（决策树、边界、验收纪律）+ v0.6.1 四发前置项

---

## 一、施工内容（4 项）

### A-1. /auto 开关（会话级，放 ctx 不放 engine 实例）

- slash `/auto`（经 slash.exec 通道，gateway 层）翻转会话级 auto 开关；
- 开关存 ctx 会话级状态，不打断工作线程；切换即时生效于**下一次** _confirm 调用；
- 返回当前状态（on/off）供 TUI 显示。

### A-2. _confirm 决策树（顺序定死，v0.6.1 火 1）

```python
def _confirm(self, tool_name, tool_args, reason):
    if self.test_mode:            # 既有，第一行不动
        return True
    if <ctx auto 开关开>:          # 新增：auto 决策树（本票核心）
        return self._auto_decide(tool_name, tool_args, reason)
    if self._all_confirmed:       # 既有，顺序必须在 auto 之后
        return True
    # 原确认流程一字不动
```

### A-3. auto 决策树 v1：只读放行（判定收进 auto 分支，不改 SAFE_COMMANDS）

- `_auto_decide`：命令经 split_shell_segments **逐段判定**（v0.6.1 火 4）——每段都是只读才放行，任何一段非只读 → 本票阶段一律走原确认流程（弹窗）；
- 只读集合 v1：git status/log/diff/show/blame/ls-files/ls-tree（复用 v3.5 的 _find_git_subcommand 判定模式，范围不限 self-repo）+ classify_command 已判 safe 的；
- **禁止**首段命中放行整条链（防 `git status && rm -rf x`）；
- SAFE_COMMANDS / DANGEROUS_PATTERNS 全局名单一个字不动。

### A-4. 审计

- auto 期间每次放行/转弹窗写 events.jsonl：`{type:"auto.decide", auto:true, command, verdict, reason, sid}`。

## 二、验收（终审口径）

1. /auto 切换不打断进行中的任务（slash.exec 通道实证）；
2. auto 开：git status / git log / git diff 在非 self-repo 目录**静默放行**；auto 关：同一命令行为与现状一致（弹窗）；
3. **逐段判定实测**：`git status && echo ok` 放行；`git status && rm -rf x` 转弹窗（或黑名单拦截）；
4. 决策树顺序实测：test_mode 下 auto 开关无效；_all_confirmed=true 且 auto 关时行为不变；
5. **auto 关闭时行为零变化**回归断言（强制，每票必有）；
6. 审计事件落盘字段齐全；
7. 全量 pytest 零回归（基线 1580 passed / 2 skipped）；真实库 md5 闸门照旧。

## 三、边界（明确不做）

- 不做写命令的 auto 放行（票 B 的事，本票写命令一律转弹窗）；
- 不做弹窗超时逻辑（票 B 火 2）；
- 不做台账字段（票 C）；
- 不改 SAFE_COMMANDS / DANGEROUS_PATTERNS；
- 不碰 test_mode 第一行。

## 四、五查汇报要求

照旧：改了什么 / 验收逐条 / 测试输出原文 / commit 与分支 / git status 原文 / 是否需重启。
禁止项：未终审不 merge、不 push、不碰 main。
