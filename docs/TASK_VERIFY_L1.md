# 任务：L1 机械层验证——写 .py 后自动 py_compile（物理保证）

日期：2026-07-27。优先级：小任务，半天以内。
前置：`data/skill-standards/code-fix/standard.md` 已上线 Phase 5.5 验证五查
（纪律层）。本任务把其中第 1 查（编译底线）从"纪律"升级为"物理保证"——
不是提醒模型检查，是工具每次写 .py 都自动检查，结果摆在模型和用户眼前。

## 背景

2026-07-27 打回案例：server.py 交付时多一行 `else:` 导致 IndentationError，
整个后端起不来，而交付方连 py_compile 都没跑。
此类问题不该依赖自觉——验证五查是 prompt 纪律，模型可能漏；
本任务让它想跳都跳不过去。

## 改动

### `tools/edit_file.py` 和 `tools/file_writer.py`（file_operation）

在**写文件成功**的路径末尾（替换/写入已落盘、inline diff 已生成之后）：

1. 判断目标文件后缀为 `.py`（其他后缀零行为变化）
2. `subprocess.run([sys.executable, "-m", "py_compile", path],
   capture_output=True, text=True, timeout=10)`
3. 把结果附加到工具返回文本末尾，格式：

```
✅ py_compile 通过: <文件名>
```
或
```
❌ py_compile 失败: <文件名>
<stderr 前 10 行>
（文件已写入，但语法检查未过——必须立即修复，禁止交付）
```

4. py_compile 失败**不阻断写入、不抛异常**——只附加醒目的失败信息。
   （文件已落盘是事实，回滚是另一件事；模型看到 ❌ 后按 code-fix 标准
   必须继续修，不允许带着失败交付。）
5. subprocess 自身异常（超时等）静默降级：附加 `⚠️ py_compile 未执行: <原因>`，
   不影响主流程。

### 明确不做

- 不自动跑 pytest（太慢，保持提醒级）
- 不检查非 .py 文件
- 不改变写文件本身的成功/失败语义
- 不动 INLINE_DIFF 通道

## 验收

1. 用 edit_file 改一个正常 .py → 返回末尾带 "✅ py_compile 通过"
2. 用 edit_file 写入一段含语法错误的 .py（如多一行 `else:`）→
   返回末尾带 "❌ py_compile 失败" 和 stderr 关键行
3. 用 file_operation 写 .py → 同样带编译结果
4. 改 .md/.txt/.ts 文件 → 返回中无任何 py_compile 内容（零行为变化）
5. 新增测试：mock/临时文件覆盖①②③④
6. `pytest tests/ -q` 全绿
7. **py_compile 自身通过**（本任务就是在防这个错，交付前自己先做到）
