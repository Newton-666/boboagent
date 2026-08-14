# TICKET-DESK-V2B4 —— 上下文药丸修复包（Kimi 已定位，按图施工）

> 性质：bug 修复票（无样式变更）。施工前必读 docs/GUI-LESSONS.md（尤其 L10/L11）。
> 分支：feat/ticket-desk-v2b4（自最新 main 切出）。未终审不 commit。

## 背景（owner 实弹发现，2026-08-14 早）

1. 药丸永远显示 `0% · 0/128K`，输入和回合中不更新
2. 上限 128K 是错的：deepseek-v4-flash/pro 是 1M，**kimi-k3 也是 1M**，须按当前 provider/model 动态取值
3. 重启后点进会话，收工汇报里的"工作区实况（git status 等）"原始几十行文本糊满屏幕，owner 裁决：渲染成**默认折叠的卡片**（标题一行 + 点击展开），信息不删

## 台账（建议 4 项）

- [ ] B4-1 kimi-k3 上下文窗口补登 1M
- [ ] B4-2 药丸数据源切活引擎 + 刷新时机修正
- [ ] B4-3 工作实况区块默认折叠渲染
- [ ] B4-4 专项测试 + 全量零回归 + md5 闸门 + 五查收工

## B4-1 kimi-k3 补登（core/provider.py）

第 63 行附近 kimi provider 的 `model_context` 字典缺 kimi-k3，补上 `"kimi-k3": 1000000`。
（参考第 20 行 deepseek 的既有写法："kimi-k2.6": 262144 等保持不变，只加不改。）

## B4-2 药丸数据源与刷新（bobo_tui_gateway/handlers/misc.py + apps/desktop/dist/index.html）

根因：`handle_context_stats` 读 `ctx.sessions[sid].messages` 估算，但 F9 后引擎跑在活引擎副本上，gateway 那份是空的 → 永远 0。

修法：
- misc.py：`handle_context_stats` 优先从活引擎取消息估算——`core.engine_adapter` 已有 F9 建的 `get_live_history(sid)`，活引擎有消息时用它，没有时回退现有路径（双兜底，与 F9 resume 同款思路）。
- index.html `refreshCtxStats`：现有两个时机（gateway.ready / 回合结束）保留，**新增"回合中每次 tool.complete 后轻量刷新"**（context.stats 是只读毫秒级估算，无性能问题；不加轮询）。
- 药丸文本的 `0/128K` 硬编码初始值改为渲染后由数据填充（HTML 里的占位文案无所谓，但必须保证首次 refresh 后立即被真实值覆盖）。

## B4-3 工作实况折叠渲染（apps/desktop/dist/index.html，纯 JS 渲染层，CSS 只允许新增不允许改旧的）

- 助手消息渲染时检测收工实况区块特征：`── 工作区实况` / `── 实况对账` / `工作区实况（收工对账` 等分隔线起始，到下一个同级分隔或消息结尾。
- 命中后渲染成折叠卡：默认收起，标题一行（如"📋 工作区实况对账"）+ 点击展开/收起；展开内容保持等宽字体原样。
- 新增 CSS 集中放 `/* === V2B4 实况折叠卡 === */ ... /* === end V2B4 === */` 锚点段，取色只用 GUI-DESIGN.md 第二节色板。
- 历史消息重放（resume/重启后加载）与流式新消息走同一渲染路径，确保两边都折叠。

## 验收

- 专项 tests/test_ticket_desk_v2b4.py：①kimi-k3 context_limit=1000000（经 handle_context_stats 或 get_context_length 断言）②活引擎有消息时 token_estimate>0 ③前端 node 实跑：含"工作区实况"的消息渲染出折叠卡且默认收起 ④V2B/V2B2 既有药丸测试不破
- GUI 子集 + 全量零回归；md5 三文件闸门；TUI 零变化
- 收工汇报按 L11：文件清单+行数、测试原话输出、md5 三值、git 状态
