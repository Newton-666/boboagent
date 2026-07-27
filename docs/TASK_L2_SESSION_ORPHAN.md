# TASK_L2_SESSION_ORPHAN — L2 任务单②：会话加载孤儿 tool_calls 保护

> 2026-07-27 Kimi 出单。L2 级（单区域、可判定）。
> 背景：HTTP 400 机理已实锤——崩溃把孤儿 tool_calls 存进会话文件，
> 恢复后带毒历史直发 API 被 400 拒绝。C3 修过压缩路径和硬截断路径的
> 孤儿保护，**会话加载路径漏网**。我已用构造历史直发 DeepSeek 复现
> 同样的 `请求错误 (HTTP 400)`。

## 已确认的事实（先读码核实再动手）

- 加载路径：`core/session_manager.py` `load_session`（约 67 行）、
  gateway `handlers/sessions.py` `handle_session_resume`（约 160 行）
- 现有孤儿保护参考：`core/context.py:149`（压缩路径配对回卷）、
  `core/engine.py:450-491`（硬截断 split 点保护）——思路可复用
- 毒药结构：assistant 消息含 `tool_calls`，但后续缺少对应
  `tool_call_id` 的 `role:"tool"` 消息（崩溃把结果弄丢了）
- 崩溃还可能留下半个 JSON（写盘时被 kill）——加载解析失败也该有兜底

## 任务文本（粘贴给 bobo）

```
任务：会话加载孤儿 tool_calls 保护（feat/session-orphan-guard 分支）

工作目录：/Users/niuqingwei/Desktop/BOBO_Project_Backup

背景（机理已验证，可复现）：
崩溃时线程死在工具调用中途，历史存盘留下孤儿 tool_calls
（assistant 发了调用、tool 结果丢失）。恢复会话后这份带毒历史
直发 API → HTTP 400，会话报废。压缩/截断路径已有配对保护
（context.py:149、engine.py:450），会话加载路径没有。

要求：
1. git checkout -b feat/session-orphan-guard，全程在该分支
2. 先读 load_session、handle_session_resume、context.py:149
   三处，理解现有配对保护的思路
3. 实现历史清洗函数（建议放 core/context.py，与现有孤儿保护同家）：
   扫描 messages，找出所有孤儿：
   a. assistant 的 tool_calls 中，没有对应 tool 消息（tool_call_id
      匹配）的调用 → 补占位 tool 消息
      content="[工具结果因中断丢失]"（补占位优于删除：保留上下文
      语义，且 LLM 知道发生过中断）
   b. 游离的 tool 消息（其 tool_call_id 找不到对应的 assistant
      tool_calls）→ 删除并计数
   c. 返回清洗后的 messages + 清洗报告（补了 N 个占位、删了 M 个
      游离），报告写 logging（bobo.log 已就位）
4. 接入点：SessionManager.load_session 加载后、返回前清洗
   （gateway resume 走同一条路则自动覆盖）
5. 兜底：会话文件 JSON 解析失败时（崩溃写了一半），
   不得抛异常 crash，返回空会话 + 记日志 + 保留原文件
   改名 .corrupted 供回溯
6. 补测试（数据一律 tmp_path，code-fix 数据隔离铁律）：
   - 含孤儿 tool_calls 的历史 → 清洗后每个 tool_call 都有配对、
     API 结构合法
   - 游离 tool 消息 → 被删除
   - 干净历史 → 清洗前后逐字节一致（零误伤）
   - 损坏 JSON 文件 → 不抛异常、返回空会话、原文件改名保留
7. ./.venv/bin/python3 -m pytest tests/ -q 全绿
8. 在 feat 分支 commit，五查汇报（表格），然后停
   （v2 规矩：汇报后允许本地 merge，禁止 push）

验收标准（逐条可判定）：
① 清洗函数三种孤儿形态全覆盖（缺结果/游离/混合）
② 占位补法而非删除（保留中断语义）
③ 干净历史零误伤（测试证明）
④ 损坏文件不 crash（测试证明）
⑤ 端到端：构造带孤儿会话 → load_session → 历史合法
⑥ pytest 全绿 + 五查表格 + 未 push
```

## 我（Kimi）初审时的独立检查

- 构造带孤儿会话文件，走 load_session 后用直发 API 的方式验证不 400
- 检查清洗是否只在加载时发生（不动压缩/截断现有逻辑）
- 端到端：kill -9 复现崩溃 → 重启恢复 → 不再 400（需用户配合）

## 结案意义

崩溃连环案第一个直接结案的 bug。修完后"崩溃→重启→400"这条
二次伤害链被斩断：线程还是会死（待抓），但死了不再毒死会话。
