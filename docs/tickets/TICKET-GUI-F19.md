# TICKET-GUI-F19 — 滚动锚定修复（窗口化死循环根治）

> 开票：2026-08-19（Hermes 分析，owner 授权执行）
> 分支：`fix/scroll-anchor-f19`（基于 main 87783c1a）
> 提交：`028b12eb`
> 回滚标签：`rollback/pre-scroll-fix-20260819`（修复前 main 现场，87783c1a）

## 现象（owner 实弹报告）

发消息后 Bobo 卡屏，chat 页面只剩 thinking 框、点不开；退出重进后向上滚动卡屏、滚动不上去。

## 根因（RWORK-F29 项6 对应）

长会话（>200 条，`HIST_WINDOW_THRESHOLD=200`）窗口化模式下两个机制互相打架：

1. `message.delta` **无条件** `chatEl.scrollTop = chatEl.scrollHeight`（每 50ms 一次）
2. 窗口化滚动监听 `histWindowOnScroll` → `renderHistWindow()` **全量重建** `chatEl.innerHTML=''`

死循环：流式滚底 → 触发 scroll 事件 → 重建清空实时 thinking 框（不在 histWindowUnits 模型里）→ 下条 delta 写游离节点 → 再滚底 → 再重建 → 主线程饱和卡屏。用户上翻时同样被强制拉回。

## 修法（A+C+D 三处）

| 处 | 位置 | 改动 |
|---|---|---|
| A | message.delta 滚底前 | `isNearBottom` 判定（`scrollHeight - scrollTop - clientHeight < 80`），仅在底部附近才跟随；上翻不拉回、不触发重建 |
| C | histWindowOnScroll 开头 | `if (currentBusy()) return;` —— 回合进行中（思考/工具/回复）不重建。用 currentBusy 而非 thinkBoxEl：工具执行阶段 thinkBoxEl 已置 null 但回合仍在跑 |
| D | message.complete 末尾 | `if (histWindowUnits) renderHistWindow();` —— 回合结束立即实测高度校准坐标系，把"跳"提前到静默瞬间 |

## 验证

- F19 专项测试 `tests/test_ticket_gui_f19.py`：4/4 通过（F19-1 静态断言三处修改存在；F19-2 node 实跑滚动锚定；F19-3 busy 挂起；F19-4 校准触发条件）
- `node --check` 主脚本语法通过（167893 chars）
- 全量 pytest：**2795 passed / 6 failed / 2 skipped / 1 xpassed**
- **6 failed 为基线已有**（`tests/test_ticket_cost1a_sandbox.py` 工具数量断言 78 vs 82、`test_ticket_tool_park_1.py` 过滤数量 77 vs 81 等——工具集变化导致，与本次改动无关）。stash 改动后复跑同样 6 failed → **零回归确认**

## 环境问题（另记，非本票范围）

- Bobo .venv 的 `sys.path[0]` 是 `/Users/niuqingwei/.hermes/hermes-agent`（Hermes 可编辑安装污染）→ 全量回归需 `PYTHONPATH=/Users/niuqingwei/Desktop/boboagent_main` 前置
- editable finder 指向已删除的 `BOBO_Project_Backup` 旧路径（死配置，无害；cwd 优先使 core 实际加载 boboagent_main）

## 回滚

```bash
git checkout rollback/pre-scroll-fix-20260819 -- apps/desktop/dist/index.html
# 或 git revert 028b12eb
```

---

## 追加：GUI-F19b 推理过程实时流（2026-08-19 补票）

### 问题（owner 实弹）
发消息后思考框 10 秒空白才输出——感知回复明显变慢。

### 根因
deepseek-chat thinking 模式下模型先思考 10-40 秒（events 实测间隔
15.2s/11.6s/24.6s/41.9s），推理过程后端经 `reasoning.delta` 实时推送
（engine.py:1533 `_on_reasoning`），TUI 端早已监听（entry.js:58993
`recordReasoningDelta`），**但桌面端漏监听该事件** → 推理内容全被吞，
思考框空白直到正文（message.delta）到达。

### 修法（提交 38df87a6，分支 feat/reasoning-delta-desktop）
1. 声明 `reasoningText` 独立缓冲（与正文 thinkText 分离）
2. `message.start` 重置缓冲
3. 新增 `on('reasoning.delta')`：推理实时滚动显示思考框（含 F19 同款滚动锚定）
4. `message.complete` 收束：final_text 无思考段时用 reasoningText 折叠；
   `stopThinking` 中断即清缓冲防残留

### 验证
- F19 专项 6/6（新增 F19b 静态断言 + node 实跑 12 项行为断言）
- 全量 pytest 2797 passed（较上轮 +2 为新增用例；6 failed 为基线已有，零回归）
- node --check 语法通过
- 回滚标签：`rollback/pre-reasoning-fix-20260819`（7c16bb2f）
