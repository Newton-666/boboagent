# 票 P0-5：记忆偏好变更替换 + memory.changed 实时刷新（负面淘汰雏形，自进化第四票）

分支 `feat/ticket-p0-5-memory-replace`，自最新 main（`59198f6b`）切出。
回滚标签 `rollback/pre-p0-5` 先打再动工。
六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等终审。

---

## 背景（SELF-EVOLVING-PLAN.md P0-5；DISCUSSION 11.3-c/174-177/306/329 节；owner 2026-08-19 实弹）

**owner 实弹场景（本票直接来源）**：测试记忆时对 bobo 说"我现在不喜欢喝冰美式了，
我喜欢喝 dirty"，期望 Memory 面板**红色删除旧条 + 绿色新增新条**（替换语义），
但实际：旧条 `id=2 "用户喜欢喝冰美式"`（USER_PREF）仍在，新条 `id=685
"咖啡偏好从冰美式改为 dirty"`（FACT）**追加**——两条并存，且面板无 diff。

**暴露的三个缺口**（本票一次补上）：

1. **偏好变更识别缺失**：对话沉淀（add_entry）只会追加，不会识别"同主题
   语义变更"→ 旧条应删除/降权、新条替换；
2. **实时刷新缺失**：记忆写入不发事件，面板只在"打开时"对比快照 → 用户
   看不到实时 diff（"每次重启才能看到=鸡肋"——owner 原话）；
3. **负面淘汰雏形缺失**（P0-5 规划项）：用户纠正（"不喜欢X"）→ 旧条降权/
   删除 + 信号源降权（DISCUSSION 306："回滚必须同时降权/删除对应信号源，
   否则回滚无效，且用户觉得 Bobo 听不懂人话"）。

**规划锚点**：
- P0-5 规划："负面淘汰机制定义——谁触发/降多少权/信号源怎么降（用户手动
  删除 → 降权信号源）"（SELF-EVOLVING-PLAN.md）；
- DISCUSSION 11.3-c：用户纠正/回滚 → 记忆降权 + 信号源降权；
- DISCUSSION 174-177 警示：淘汰判据不能纯 LLM（无锚点）；**本票的判据
  是确定性规则**（同主题 + 语义反转关键词），不用 LLM 做淘汰决定。

## 施工项

### 1. 偏好变更识别（核心，确定性规则，零 LLM 淘汰判断）

`tools/v5_memory.py` 新增替换检测（对话沉淀 `add_entry` 路径接入）：

- **触发**：新条与某旧条**同主题**且新条含**语义反转关键词**（"改为/改成/
  不再是/不喜欢/别/不要/以后不/换"）→ 判定为"偏好变更"；
- **同主题匹配**：确定性启发式——旧条文本与 new_text 共享显著 token
  （如"冰美式"出现在两者、或 P0-1 六类 + 文本余弦/关键词交叠）。**具体
  匹配规则施工时定，但必须确定性、可测试、不许 LLM**；
- **动作**（替换语义）：
  1. 旧条标记 `archived=true` + `signal_score` 归零（保留历史可查，不物理删除）；
  2. 新条写入（signal_score 100）；
  3. 写审计日志（复用 `_audit_log`，action=REPLACE，记 from_id→to_id）；
- **降权幅度**：归零（偏好反转=彻底失效），非 5 分小降——与 P0-5"负面
  淘汰"对齐：纠正类变更一次到位；
- **不触发**：无反转关键词的普通新增（照旧追加）；同主题但不相反的
  （如"我也喜欢 dirty"）不替换。

### 2. memory.changed 事件（实时刷新通道）

- `tools/v5_memory.py`：`add_entry` / `delete_memory` / `update_memory_type` /
  REPLACE 路径成功写入后，经 event_bus 发 `memory.changed` 事件
  （payload: `{action: "add"|"delete"|"retype"|"replace", entry_id, changed_at}`）；
- **gateway 广播**：复用既有事件广播（server_utils.emit / write_json，
  notes.changed 有注释先例），前端按 sid 过滤；
- **注意**：v5_memory 是工具层，event_bus 注入需最小侵入（参考
  living_notes 的 bus.write 先例，失败静默降级）。

### 3. 前端实时刷新

`apps/desktop/dist/index.html`：
- 新增 `on('memory.changed', ...)` handler：
  - 若 Memory 面板当前**打开**（#memory-view 可见）→ 重新 `loadMemoryPanel()`
    （快照对比 → 红删绿增实时冒出）；
  - 若未打开 → 只更新导航 count（不打扰）；
- **diff 语义对齐替换**：REPLACE 时旧条 archived → 快照对比应显示
  `- [id] 旧文本`（红）与 `+ [新id] 新文本`（绿）——renderMemoryDiff 的
  现有逻辑按 id 增减对比，archived 条目在 list_memories 里不再返回 →
  自然显示为删除；**需确认 list_memories 过滤 archived**（若不过滤，
  REPLACE 的旧条不会消失，diff 不显示红——施工时核对）。

### 4. 回归测试

`tests/test_p0_5_memory_replace.py`（或并入 test_signal_log 体系）：
- 替换触发：同主题+反转词（"不喜欢冰美式了，喜欢 dirty"）→ 旧条
  archived+score 归零 + 新条写入 + 审计 REPLACE 记录；
- 不触发：普通新增 / 同主题不相反 → 旧条不动；
- 确定性：同一输入两次跑结果一致（无 LLM 随机）；
- 事件：add/delete/replace 后 event_bus 收到 memory.changed；
- 前端：index.html 含 `on('memory.changed'` handler + 打开时刷新逻辑
  （静态断言）；
- 零动作回归：本票不破坏 P0-2"只记录不动作"（signal 判定路径不受影响）；
- 全量 pytest 零失败。

## 验收标准（终审逐条复跑）

1. 对话说"不喜欢X，喜欢Y" → 库中旧条 archived+score=0、新条写入、
   审计 REPLACE 留痕（确定性，两次跑结果一致）；
2. `memory.changed` 事件在 add/delete/retype/replace 后发出（event_bus
   事件可观测）；
3. 前端：面板打开时收到 memory.changed → 自动刷新 → diff 红删绿增；
   未打开时只更新 count；
4. list_memories 对 archived 条目的处理符合 diff 语义（红删可见）；
5. 全量 pytest 零失败（基线 2781 passed / 2 skipped / 1 xpassed +
   新用例；cost1b 分支名环境失败为既有已知项）；
6. 收工报告落 `library/agent开发/TICKET-P0-5完成报告.md`
   （md5/git 实况/测试原话/替换场景样例/事件样例）。

## 风险自查点

- **淘汰判据零 LLM**（DISCUSSION 174-177）：同主题匹配 + 反转关键词全部
  确定性规则，测试锁死；LLM 只负责产出新条文本（既有沉淀路径），不参与
  "该不该替换"的决定；
- **防误替换**：同主题共享 token 匹配必须够严（如"冰美式"这类专有名词
  命中才算，泛词如"咖啡"单独不算）——施工时给误判保护，测试覆盖
  "同主题但不反转"不触发；
- **archived 语义**：物理不删（历史可查/可回滚），list_memories 过滤；
  P0-1 的 656 迁移幂等测试不受影响（archived 是运行时态，非 type 残留）；
- **event_bus 最小侵入**：v5_memory 发事件失败必须静默（记忆写入是主
  路径，事件是旁路）；
- **前端零打扰**：面板未打开时收到事件只更新 count，绝不弹窗/刷新聊天区；
- **write_obsidian 陷阱**：报告落 `library/agent开发/`（已错 7 次的教训）。

## 已完成取证（Kimi 开票前核实，施工不必重复）

- 现状：`add_entry` 纯追加（tools/v5_memory.py:166）；`update_entry` 仅
  手动改文本；无替换/降权逻辑；对话沉淀路径 `_precipitate_memory`
  （core/context.py:659）只 add_entry；
- 库现状：id=2 "喜欢喝冰美式"（USER_PREF, 6/16）与 id=685 "改为 dirty"
  （FACT, 8/19）并存——替换缺失实证；
- 事件通道：前端 onMessage → handlers（index.html:860），`on('notes.changed'`
  有注释先例（2313 行）；v5_memory 当前不发任何事件；
- 审计通道：`_audit_log` 已存在（P0-1 建，data/logs/memory_audit.log，
  DELETE/RETYPE 已用），REPLACE 接入即可；
- 基线 pytest：2781 passed / 2 skipped / 1 xpassed（cost1b 已知项除外）；
  当前真实库 657 条（P0-1 基线 656 + id=685 对话沉淀）。
