# 票 RWORK-F29：GUI-F29 终审返工——16 测试失败 + 3 个行为回归（虚拟滚动收口）

分支：在 `feat/ticket-gui-f29-virtual-scroll` 上继续（不新建分支，同票收口）。
回滚标签：`rollback/pre-gui-f29-20260819-2200` 已打（保持不动）。
六步工作流 + GUI-LESSONS 全程，返工完成等终审复跑。

---

## 背景（Kimi 终审 2026-08-19，GUI-F29 首轮未通过）

GUI-F29（虚拟滚动）首轮终审发现：
- **全量 pytest 16 失败**（bobo 汇报"2797 passed"与实际不符——漏跑/漏看）；
- **3 个行为回归**（owner 实弹反馈，均为 F29 引入或暴露）。

**Owner 定调（延续）**：丝滑不卡即可（≥50fps），不追 120Hz；**不出错 > 极致
性能**；向上滚动见全部历史；全部既有行为零回归。

## 返工项

### 1. 全量 pytest 16 失败（必须 0 失败收口）

- **tests/test_ticket_gui_f6d.py（5 个）**：F29 重构工具聚合为数据模型驱动
  （liveAggSwallow/liveMount），f6d 测试用 `node [eval]` 加载 index.html JS，
  eval 片段里拿不到 F29 新函数（`ReferenceError: liveMount is not defined`）。
  **修测试适配**（让 F29 函数在 eval 环境可见 / 同步断言到新实现）——功能
  本身没坏，是测试加载方式没跟上；
- **tests/test_ticket_desk_tel.py::test_tel_8_zero_interference**：index.html
  改动未登记 GUI-F29 特批标记，按既有授权机制登记；
- **其余 10 个失败**：自行跑全量确认清单，同型处理（测试适配或登记）；
- 验收：`.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` 0 失败
  （cost1b 分支名环境失败为既有已知项）。

### 2. 行为回归①：工具卡显示错乱（edit_file 显示成 task_ledger + diff 挂错卡）

**owner 实弹**：编辑文件时工具卡显示 "task ledger" 而非 "Edit file"，
diff 挂到 task_ledger 卡下，调用完 diff 被收掉。**以前正常，F29 后出现**。

**根因（Kimi 定位）**：
- 多工具并行（DeepSeek 一次返回 task_ledger + edit_file，22:53:05 实证）；
- **F29 窗口化回收**：edit_file 卡被 liveRecycle 回收后，
  `tool.complete` → `updateToolResult('edit_file')`（index.html:2097
  querySelectorAll `data-tool="edit_file"`）**找不到 running 卡** →
  div=null → diff 挂载锚点失效/错位到相邻卡；
- **task_ledger/load_result 无 TOOL_FRIENDLY 映射**（只有 TOOL_ICONS）→
  显示原始名（历史遗漏，F29 让它暴露）。

**修复要求**：
- updateToolResult 找不到 running 卡时，**按数据模型（liveUnits）回退**
  找对应 unit 重建/挂载 diff，不静默失败；
- diff 挂载锚点必须**精确到工具卡本身**（数据模型索引），不依赖 DOM
  querySelectorAll 的"第一个 running"猜测；
- TOOL_FRIENDLY 补全：task_ledger / load_result 等所有 TOOL_ICONS 有但
  FRIENDLY 无的工具（脚本比对，一次补全）；
- 验证：多工具并行场景（task_ledger + edit_file 同批）diff 正确挂到
  edit_file 下 + 显示 "Edit file"。

### 3. 行为回归②：思考/工具折叠失效

**owner 实弹**：bobo 运行时思考/工具调用不再自动折叠（以前自动折叠）。

**根因（Kimi 定位）**：`liveRecycle` 回收节点时**不清 thinkBoxEl**
（index.html:3656 全局变量）——流式 think-box 滚出可视区被回收后，
thinkBoxEl 仍指向已移除节点 → 后续 addTool 检查 `if (thinkBoxEl)` 为真但
节点不在 DOM → 折叠/收束操作落在幽灵节点上 → 折叠表现异常。

**修复要求**：
- liveRecycle 回收 think-box 时，若它是当前 thinkBoxEl，先收束
  （collapseThinkBox）再清引用；或 thinkBoxEl 改为从数据模型/活节点判定；
- 验证：流式思考中滚动出窗口再滚回，折叠行为与不滚动时一致。

### 4. 行为回归③：diff 不常驻（被回收/折叠消失）

**owner 实弹**：diff 应该常驻显示（与回答同级），但工具调用完后 diff
被收掉（进折叠聚合卡 + 被窗口化回收）。

**根因（Kimi 定位）**：diff 是 liveUnits kind='diff'（可被 liveRecycle
回收），且工具聚合时被吞进默认折叠的聚合卡（tool-agg-body display:none）。

**修复要求**：
- **diff 不参与窗口化回收**（或回收时豁免/保留 diff 块）——Owner 要求
  diff 常驻、与回答同级；
- diff 不随工具聚合折叠（写类工具的 diff 保持摊开——F6D 语义"编辑流
  全程摊开"对齐）；
- 验证：编辑文件 → diff 常驻显示，滚动/后续工具调用后仍在。

### 5. 行为回归④（新增，owner 实弹 2026-08-19 深夜）：最新消息被回收——用户 prompt 和上一轮回复消失

**owner 实弹**：滚动到历史区后，新发送的 prompt、bobo 的回复（在底部）
**被窗口化回收，看不到了**。用户输入和当前回复是最重要的内容，绝不能丢。

**根因（Kimi 定位）**：`liveWindowTick` 回收**窗口区间（scrollTop ± 2 屏）
之外的全部 unit**——`for (i = endIdx+1; i < liveUnits.length; i++)
liveRecycle(...)` 把**底部最新消息**也回收了。**完全没有"最新消息永不
回收"的保护**（代码搜不到任何 keep/pin/latest 逻辑）。

**修复要求（核心）**：
- **最新 N 条（如最后 10-15 条，含用户 prompt + 当前回复 + 流式内容）
  永不回收**——无论滚动位置在哪，底部最新消息恒驻 DOM；
- 回收只针对"**已完成的、旧的历史消息**"（窗口外 + 非最新 N 条）；
- liveRebuild 滚回底部时必须完整重建（含最新 prompt/回复）；
- 验证：滚动到历史区 → 发新 prompt → 底部 prompt+回复可见；
  滚回底部 → 全部消息重建完整。

### 6. 收口纪律

- 施工代码**必须 commit**（首轮 3 个 docs commit 但施工代码在工作区未提交）；
- 全量 pytest 0 失败 + jsdom 测试 + Electron e2e 复跑全过；
- 更新完成报告（library/agent开发/，不是 Obsidian——write_obsidian 已错
  10 次），含返工项逐条说明 + 验证数据。

## 验收标准（终审逐条复跑）

1. 全量 pytest 0 失败（cost1b 已知项除外）；
2. 多工具并行场景：工具卡名正确（Edit file）+ diff 挂对卡 + 常驻不消失；
3. 思考折叠：滚动中/后折叠行为正常；
4. jsdom + Electron e2e 全过（220 条 → DOM 收缩、滚动丝滑 ≥50fps 保持）；
5. 报告落 library/agent开发/，md5/git/测试原话/验证数据齐全。

## 已完成取证（Kimi 定位结论，施工不必重复）

- 16 失败清单：f6d×5（eval 拿不到 liveMount）+ TEL-8×1 + 其余 10（同型）；
- 工具卡错乱：22:53:05 多工具并行（task_ledger + edit_file）+ updateToolResult
  找 running 卡失败（index.html:2097）+ TOOL_FRIENDLY 缺 task_ledger/load_result；
- 折叠回归：liveRecycle 不清 thinkBoxEl（index.html:3656 + liveRecycle 定义）；
- diff 消失：kind='diff' 可回收 + 聚合卡折叠（index.html:2279 + 2014）；
- 基线 pytest：2797 passed / 2 skipped / 1 xpassed（cost1b 已知项除外）；
  真实库 659 条。
