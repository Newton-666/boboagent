# 任务：diff 白字可读性修复 + 全写工具 diff 覆盖

日期：2026-07-27。两部分：①TUI 渲染修复（字色）②后端全写工具接入 diff。
前置：inline diff 通道（`<<<INLINE_DIFF>>>` → engine_adapter → TUI）
与 Claude 风格渲染（gutter/全宽色带）均已上线，edit_file / file_operation 已接入。

---

## ① diff 文字白字化（TUI，先修——当前看不清）

**问题**（用户实测）：diff 色带里代码文字是浅绿 `rgb(120,220,140)` 配
深绿底 `rgb(18,56,36)`——同色相低对比，糊成一团，代码看不清。
Claude Code 的体验是深色带 + 白字（明度对比），清晰。

**另有一个隐患**（`ui-tui/src/theme.ts` 亮色系主题 343–350）：
亮色主题下 diff 背景色没换（仍是深绿深红），但字色被覆盖成
深绿 `rgb(27,94,32)` / 深红 `rgb(183,28,28)`——深字配深底直接隐形。
疑似复制粘贴漏改。

**修法**（`ui-tui/src/components/markdown.tsx` diff 渲染段 + `theme.ts`）：

1. add/del 行的**代码文字**改为近白色（如 `#e8e8e8`）；
   gutter 行号和 +/- 符号列保留浅绿/浅红（色块身份不丢）
2. ctx 上下文行维持 muted 灰（刻意的视觉降级，不动）
3. 修亮色系主题：要么 diff 背景换浅色、要么删掉 349–350 那两行
   Word 覆盖色，消灭"深字配深底"组合
4. `npm run build` 重新构建 TUI bundle，**同步构建产物到运行路径**
   （老坑：构建产物不同步 = 白改）

**验收**：
- 改一个文件触发 diff，pty 截图/文本断言：add/del 行代码文字为近白色
- 亮色系主题下 diff 不出现深字深底
- 行号 gutter 和 +/- 符号仍是绿/红色

---

## ② 全写工具 diff 覆盖（后端，体力活）

**目标**：凡是局部替换/追加类写操作——代码、文稿、obsidian 笔记——
都在 TUI 显示白字色带 diff。通道已建成本任务就是逐个接水管。

### 步骤 1：抽公共 helper

新增 `core/diff_utils.py`（或合适位置）：

```python
def make_inline_diff(old_text: str, new_text: str, path_hint: str = "") -> str
```

- 输出统一 `<<<INLINE_DIFF>>>...<<<END_INLINE_DIFF>>>` 块
- 统一边角规则：超 40 行截断（显示 +N -N 计数 + 前后各几行）、
  空 diff 返回空串、新文件显示全 +、纯追加可只 diff 追加段
- **收编现有重复**：edit_file 和 file_operation 里现有的 diff 生成逻辑
  改成调用 helper（它们现在是各自复制的双胞胎，防以后改一个漏一个）

### 步骤 2：逐个写工具接入（按优先级）

| 优先级 | 工具 | 说明 |
|---|---|---|
| P0 | obsidian_tools（append/overwrite 笔记） | 用户最高频，写前读旧内容 → diff → 附加 |
| P1 | code_execution 写文件路径 | 执行代码写文件时（能捕获新旧才做，捕获不了跳过） |
| P2 | notion 写工具 | 旧内容在 API 侧，需先拉取；拉取成本高时可降级为"只显示本次追加片段的 diff" |
| P2 | memory/knowledge 写入（memory_set 等局部 KV 修改） | 旧值 → 新值的 diff |

### 设计要点

- **append 类**：只把追加段当 diff（全 + 行），不做整文件对比，开销小信息量一样
- **没有旧内容可得的工具**：跳过不强行做，清单里标注原因
- **大文件防炸**：沿用 40 行截断 + 计数规则
- 每个接入工具遵守"写 .py 自动 py_compile"的既有机制，互不干扰

### 验收

- 用 bobo 改一条 obsidian 笔记（局部替换 + append 各一次）→
  TUI 出现白字色带 diff，内容正确
- edit_file / file_operation 回归正常（收编 helper 后行为不变）
- 每个接入工具新增测试：断言返回文本含 INLINE_DIFF 块且 diff 内容正确
- `pytest tests/ -q` 全绿；py_compile 所有改动文件（交付底线）

## 两部分共同验收

- 最终效果：bobo 改 obsidian 笔记 → TUI 显示**白字**深绿/深红色带 diff
- 测试只增不减，打回必留测试

---

## ③ 附带：P1 抽离验收发现的两个毛刺（2026-07-27 一并处理）

### 毛刺 1：`record_read` 存了 dict 包装纸

`core/engine.py`（约 1471 行）：`self.tracker.record_read(fpath, str(match) if match else "")`
——`match` 是整个 tool_result 字典，`str()` 后存进 `_read_files` 的是
`"{'tool_call_id': 'c1', 'role': 'tool', 'content': '...'"`，
200 字符的恢复预算被字典包装结构吃掉一截。

**修法**：取 `match.get('content', '')`（结果字典的实际内容字段），
不是 `str(match)`。

**验收**：同一轮读文件后，`_read_files[fpath]` 以文件内容开头，
不含 `'tool_call_id'` 字样；既有 N3 测试（AAA/BBB 场景）保持绿。

### 毛刺 2：round_tracker 缺模块级单测

P1 抽离时 N3 测试留在 test_bugfixes.py（e2e 通路覆盖存在），
但验收条目"新模块有自己的单测"未做。

**修法**：新增 `tests/test_round_tracker.py`，锁定三个方法：
- `record_read`：正常存取、>200 字符截断、>10 条淘汰最旧
- `compress_changelog`：>20 条时压缩、压缩后含"[历史改动]"
- `recent_reads`：按 recency 返回、条数上限
配合毛刺 1 修完后，断言 record_read 存的是纯内容而非 dict repr。

**验收**：`pytest tests/ -q` 测试数 ≥ 724 + 新增。
