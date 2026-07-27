# 任务：把 /duo 注册成真正的斜杠命令

日期：2026-07-27。优先级：小任务（~10 行，单文件为主）。
前置：`docs/DESIGN_DUO_MODE.md` 已验收，duo skill
（`data/skill-standards/duo/standard.md`）已上线并经关键词触发实测通过。

## 问题

TUI 里输入 `/duo 商讨：xxx` 返回"未知命令: /duo …"。
原因：所有斜杠输入被网关 `bobo_tui_gateway/server.py` 的
`handle_slash_exec`（`@method("slash.exec")`，约 751 行）硬编码拦截，
命令不在 if/elif 名单里就掉进 986 行的 `else: 未知命令`，
**请求永远到不了 LLM，duo skill 注入不会发生**。

当前用户只能打无斜杠的自然语言（"duo 商讨：xxx"）才能触发，体验不一致。

## 改动

### ① `bobo_tui_gateway/server.py` — `handle_slash_exec` 加分支

在 `else: 未知命令` 之前插入：

```python
elif command == "duo" or command.startswith("duo "):
    # /duo 不是网关命令，是 skill 触发词：去掉斜杠透传给对话管线，
    # 由 engine 的 skill 注入机制（data/skill-standards/duo）接管。
    rest = command[3:].strip()  # "duo" 之后的内容
    text = f"duo {rest}".strip()
    return handle_prompt_submit(
        {"session_id": sid, "text": text}, rid)
```

注意：
- `handle_prompt_submit` 定义在 468 行，同文件直接调用即可。
- 透传文本保留 "duo" 前缀——这是 skill 的 keywords 之一，必须带着才能触发。
- 不要复制 prompt.submit 的逻辑，直接调函数，避免两条对话路径 drift。

### ② 同文件 `_COMMANDS`（约 1068 行）canon 表加一行

```python
"/duo": "/duo",
```

让 TUI 斜杠自动补全/帮助里能看到它。

### ③ `handle_slash_exec` 的 `/help` 输出文本（756 行）

命令列表字符串里加上 `/duo`，附一句话说明：
"/duo <任务> — 双员模式：A 干活 B 验收；/duo 商讨：<问题> — 双方案辩论出决策清单"。

## 明确不做

- 不改 TUI TypeScript 侧——未知命令目前已经会落到 `slash.exec`（ops.ts 的
  `cmd.slice(1)` 路径），后端分支加上即通，前端零改动。
- 不改 engine、不改 skill 文件。
- 不给 duo 加网关侧的专门处理逻辑（它属于对话管线，不属于命令管线）。

## 验收

1. TUI 输入 `/duo 商讨：测试问题` → 进入正常对话流（有流式输出），
   日志/上下文中可见 Duo Standard 被注入，最终输出决策清单四段格式。
2. TUI 输入 `/duo`（无参数）→ 不崩，进入对话流由 LLM 引导用户补全需求。
3. `/help` 输出包含 /duo。
4. 斜杠自动补全菜单出现 /duo。
5. 其他既有斜杠命令（/help /clear /provider /undo）回归正常。
6. `pytest tests/ -q` 全绿，无新增失败。
