# REWORK：活体冒烟测试（打回返工）

> 对象：feat/live-smoke-harness @ c8d16bc（scripts/smoke_boot.py 251 行）
> 级别：L3，返工后需重走 duo B 验收 + Kimi 终审
> 打回人：Kimi（2026-07-28）
> 一句话：现版是"真 API 版 e2e"，不是票上签的"活体进程冒烟"。进程边界被偷换了。

## 阻塞项（4 + 1 实证要求）

### 阻塞 1：假启动——必须 spawn 真实 bobo 进程

现版 `from core.engine import Engine` 进程内 import 构造，不经过 entry、不经过进程边界。任务单写明的验收目标是"静态测试全绿但进程起不来的事故由此兜底"——现版对此类事故完全失明（entry.py 损坏、TUI spawn 链条断裂、信号处理问题均照不到）。

**修法**：
- 一期：`subprocess` 启动 backend 模式（`entry.py` 的 `_run_backend` 路径或等效入口），通过 stdin/stdout 协议驱动对话，读取进程输出判定 ready
- 二期（本次必须至少做尝试，做不了要写明原因）：pexpect/pty 驱动 TUI 模式
- 五联征第 1 征"ready"必须以**进程输出中的就绪标记**为准，不得以 import 成功代替
- 第 5 征"退出干净"必须有真实内容：发退出指令 → 进程在限时内结束 → 退出码 0 → 无残留子进程（ps 验证）

### 阻塞 2：日志白名单过宽

`"No module named"` 会把所有 ImportError 免疫——断链 import 恰是近期真实病型（_skill_mgr、proactive.py call_llm）。

**修法**：白名单只放精确匹配的已知无害完整消息（含模块名/上下文），禁止放错误类别子串；每条白名单项须附注释说明来源。`No module named` 和 `python-dotenv could not parse` 必须移除或精确化。

### 阻塞 3：工具轮投降通道

```python
# 即使没有显式 tool 轮，也算通过（模型可能选择直接 echo）
```
任务单要求"必触发工具"。

**修法**：history 中必须存在 role=tool 消息且结果含 smoke_ok 才判 PASS；模型未调工具 → 换更明确的指令重试一次（如"必须使用 execute_terminal 工具执行 echo smoke_ok"）→ 仍无 tool 消息则 FAIL。删除"也算通过"分支。

### 阻塞 4：退出干净空断言

"Python API 无子进程"是循环论证。阻塞 1 修复后此条自然有实义（见上），现版该断言写法禁止保留。

### 实证要求 5：数据隔离不能只写注释

现版注释"Engine 默认会话由 tests/ 模式约束"——这不是 tests，没有 mock，`engine.run()` 会走 session_manager 写 `data/sessions/`。

**修法**：脚本运行前快照 `data/` 目录文件清单 + mtime（或 git status 式 diff），运行后输出 diff 报告；产生的会话文件须落在可指定的临时数据目录（如支持 `BOBO_DATA_DIR` 环境变量指向 tmp），或运行后自动清理。五查汇报中须附 data/ diff 证据。

## 保留项（现版做对的）

- 日志快照 diff 机制（_snapshot_log_lines / _check_log_clean）思路正确，保留
- --dry 模式、重复性验证（3 次）、结果报告格式，保留
- 真 API 驱动的 Engine 对话轮可作为"第 6 征：引擎直连"保留，但不得替代进程级五联征

## 验收标准（新版）

1. 五联征全部在**真实子进程**上验证（backend 模式最低要求；TUI 模式尝试结果须汇报）
2. 白名单精确化，无错误类别子串
3. 工具轮无投降通道，无 tool 消息即 FAIL
4. 退出码 + 残留进程检查为真实断言
5. data/ diff 报告附在五查汇报中
6. 三次连续 PASS；pytest 全量绿不受影响
7. 所有 commit 走 feat 分支（包括打回修复——2026-07-28 已有 6393deb 直提 main 前科，此票返工期间重点盯防）
