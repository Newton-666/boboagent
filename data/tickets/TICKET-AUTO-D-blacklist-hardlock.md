# TICKET-AUTO-D：auto 黑名单硬锁 + 外部不可逆拒绝 + 收工交接清单

> 立案：2026-08-10 · 依据 v0.7 裁决一 + bobo 改动面核实报告（2026-08-10）
> 前置：票 B 已合并（含 46cd0e3 安全修正）。分支自最新 main 切出：feat/ticket-auto-d
> 纪律：branch 施工、五查汇报、未终审不 merge 不 push
> **只改 auto 路径。正常模式确认流程一个字不动。**

---

## Kimi 对改动面报告三问（Q1-Q3）的裁决

- **Q1**：是。`_confirm` 尾部兜底分支 auto 下统一 deny——**auto 不弹窗是铁律**，任何意外落入兜底的灰名单都即时拒绝+留痕，不留 120s 卡死路径；
- **Q2**：采用前者。新增 `is_blacklisted(command)` 辅助函数（command_safety.py，复用 DANGEROUS_PATTERNS，split 前整条检查——注意 46cd0e3 的教训：shlex 会把 `$(` 拆散，必须查原始串），语义清晰、可独立测试；
- **Q3**：追加到 `_pending_content` 进对话流（用户回来一眼看到）+ events 留痕已有。两通道都要。

---

## 一、施工内容（3 项）

### D-1. auto 下即时 deny 两档（engine.py `_auto_decide` execute_terminal 分支）

现状：external-irreversible → escalated 审计 → confirm_callback 弹窗（120s 卡死）。
改为**均不调 confirm_callback**：

- **黑名单**（`is_blacklisted` 命中）→ `_write_auto_audit("deny", ..., "危险黑名单硬锁：auto 即时拒绝（{side_reason}）", ...)` → `return False`；
- **外部不可逆灰名单**（git push / npm publish / curl 写 / scp 等）→ `_write_auto_audit("deny", ..., "auto 模式：外部不可逆操作，拒绝并记入待人工执行清单（{side_reason}）", "external-irreversible", None)` → `return False`；
- 兜底分支（非 terminal 灰名单意外落入）→ 统一 deny（Q1 裁决）。

### D-2. 收工交接清单（从 events 现查，不定新结构）

- 位置：engine.py 收工路径（`_append_to_history("assistant", ...)` 之前）；
- 实现：读 `event_bus.filepath`（公开属性）逐行过滤 JSONL：`type=="auto.decide" and sid==self.sid and verdict=="deny"` → 取 command+reason，**同命令去重** → 渲染"📋 待人工执行清单"追加到收工回复尾部；
- 清单每条含：命令 + 被拒原因；黑名单条目与外部不可逆条目分节展示；
- 仅在 auto 模式且清单非空时追加；正常模式零影响；
- 轮转学：只读当前 events.jsonl（`.1` 旧文件不读）。

### D-3. 测试同步更新（报告已列 8 处 + 新增）

需改断言：
- test_auto_mode.py 4 处（git push / rm -rf 链：走 callback → 改即时 deny 且 confirm_callback 调用次数 == 0）；
- test_auto_mode_b.py 3 处（escalated → deny）；
- 超时 deny 测试语义改写为"正常模式超时 deny"（`_wait_for_confirmation` 只服务正常模式，不删）。

新增测试：
- 黑名单即时 deny 且 confirm_callback 零调用；
- 外部不可逆即时 deny 且零调用；
- 收工清单含被拒命令（含去重、黑名单/不可逆分节）；
- auto 关闭时收工回复无清单（零影响断言）。

## 二、验收（终审口径）

1. auto 下 `rm -rf x`、`echo $(rm -rf x)` → 即时 deny，**无弹窗、confirm_callback 零调用**、审计 reason 含"危险黑名单硬锁"；
2. auto 下 `git push` → 即时 deny，零调用，审计含"记入待人工执行清单"；
3. 收工回复尾部出现交接清单，含上述被拒命令，同命令去重；
4. **auto 关闭时行为零变化**：黑名单仍弹窗、git push 仍弹窗、收工无清单（强制回归断言）；
5. test_mode → auto → _all_confirmed 顺序不破坏（票 A/B 保留测试全过）；
6. 全量 pytest 零回归（基线 1677 passed / 2 skipped）；真实库 md5 闸门照旧。

## 三、边界（明确不做）

- 不动 tool_runner.py / classify_command / DANGEROUS_PATTERNS / classify_side_effect / engine_adapter 的 confirm_callback 与 _wait_for_confirmation；
- 零前端改动（AUTO-F 才动 TUI）；
- 不做台账字段（票 C）；交接清单只从 events 现查；
- 不动 ESC/Ctrl+C（AUTO-E）。

## 四、五查汇报要求

照旧：改了什么 / 验收逐条 / 测试输出原文 / commit 与分支 / git status 原文 / 是否需重启。
禁止项：未终审不 merge、不 push、不碰 main。
