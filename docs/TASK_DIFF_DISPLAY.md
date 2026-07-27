# 任务：edit_file 编辑操作显示 Claude Code 风格彩色 diff（纯后端版）

## 背景与目标

用户（bobo 所有者）希望 bobo 编辑文件时显示 Claude Code 风格的红绿对照 diff，
不用打开文件就能审阅模型改了什么。显示效果参照 Claude Code 的
`⏺ Update(path) ⎿ Added N, removed M` + 红绿对照块。

**显示时机**：edit_file 执行完成的那一刻，diff 以段落锚定方式插入对话流中编辑实际发生的位置（AI 前一句话和后一句话之间），与 Claude 的节奏一致。

## 关键事实（已逐行核实，2026-07-26）

**前端已完整具备该能力，零改动：**

- `ui-tui/src/app/uiStore.ts:19` — `inlineDiffs: true`，默认开启
- `ui-tui/src/app/createGatewayEventHandler.ts:694` — `tool.complete` 事件已读取 `payload.inline_diff`，非空则走 `recordInlineDiffToolComplete`
- `ui-tui/src/app/turnController.ts:476` — `pushInlineDiffSegment` 把 diff 包成 ```` ```diff ```` markdown 块并锚定插入对话流（段落级，落在编辑发生的位置）；连续重复 diff 自动去重
- `ui-tui/src/components/markdown.tsx:750-781` — ```diff 代码块渲染，`diffAdded`/`diffRemoved` 背景色 + 文字色，`@@` hunk 头着色，即 Claude 风格红绿对照

**唯一缺口（后端）：**

- `core/engine_adapter.py:71-83` — `tool_result` 分支 emit `tool.complete` 时只放了 `result_text`，**没有 `inline_diff` 字段**。这是本任务唯一要补的数据通道。

## 方案（纯后端，约 15 行）

### 1. `tools/edit_file.py`

替换成功后（现有"已替换"返回处），用标准库 `difflib.unified_diff` 生成 diff
（函数手里本来就有替换前后完整内容，无需 git），以约定分隔符附加到返回文本尾部：

```
已替换: ui-tui/src/components/appLayout.tsx
  文件大小: 20481 → 20485 字符
  行数: 455 → 457 行
  备份: ~/.bobo/trash/appLayout.tsx.bak
<<<INLINE_DIFF>>>
@@ -253,6 +253,8 @@
   )}
 
-      <StatusRulePane at="top" composer={composer} status={status} />
+      <Text color={ui.theme.color.border}>{'─'.repeat(...)}</Text>
+
+      <StatusRulePane at="top" composer={composer} status={status} />
<<<END_INLINE_DIFF>>>
```

截断规则：diff > 40 行时只保留首尾各一个 hunk，中间标注 `... (省略 N 行)`。

注意：
- 生成的 diff 必须同时保留给 LLM（维持现有"diff 注入下一轮"行为），不能因为要显示就从 LLM 上下文里省掉。
- 分隔符用不太可能与文件内容撞车的字符串；`file_operation` 的写文件操作如方便可同样支持，不方便就只做 edit_file。

### 2. `core/engine_adapter.py`（tool_result 分支，71-83 行附近）

```python
result = data.get("result", "")
inline_diff = ""
if "<<<INLINE_DIFF>>>" in result:
    result, _, tail = result.partition("<<<INLINE_DIFF>>>")
    inline_diff, _, _ = tail.partition("<<<END_INLINE_DIFF>>>")
    result = result.rstrip()
    inline_diff = inline_diff.strip()
emit("tool.complete", sid, {
    ...,
    "result_text": result,
    "inline_diff": inline_diff,   # 空字符串时前端自动走原路径
    ...
})
```

注意：`inline_diff` 为空字符串时前端行为与现在完全一致（`createGatewayEventHandler.ts:694` 对空值走 `recordToolComplete` 原路径），所以对其他所有工具零影响。

## 明确不做

- **不改任何 TUI/前端代码**（能力已存在，改前端是纯浪费）。
- 不改 gateway 消息协议格式（`inline_diff` 是协议里已有的字段）。
- 不做词级高亮、不改 `/details` 折叠机制、不动 `● Tool(...)` 头部样式。
- 不要给 diff 文本加 ANSI 颜色码（前端 markdown ```diff 渲染自带主题色；ANSI 反而会在 `createGatewayEventHandler.ts:696` 被 `stripAnsi` 剥掉）。

## 验收标准

1. 让 bobo 用 edit_file 改一个真实文件，对话流中在工具调用位置出现红绿对照的 diff 块（`+` 绿底、`-` 红底、`@@` 着色），位置在 AI 前后话语之间而非消息末尾。
2. diff > 40 行时正确截断并有省略提示。
3. 连续两次相同编辑不重复显示 diff（前端已有去重，验证生效即可）。
4. 其他工具（execute_terminal、read_local_file 等）显示与之前完全一致。
5. pty 自动化验证：跑 bobo 触发一次 edit_file，剥离 ANSI 后确认对话中出现 diff 内容，原始字节中含 SGR 颜色码。
