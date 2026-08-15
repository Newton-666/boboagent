# ROADMAP — bobo 体系作战地图

> v4.7 · 2026-08-14 · 随每票终审合并滚动更新；发现新问题/新想法 → 补进本文件对应梯队

## 当前队列（按执行顺序）

### 第一梯队：桌面端体系化（A 类追平，owner 2026-08-13 拍板；铁律：现有 CSS 视觉零改动）

| 序 | 票 | 干什么 | 状态 |
|---|---|---|---|
**▶ 待施工（按执行顺序）**

| 序 | 票 | 干什么 | 状态 |
|---|---|---|---|
| 0 | GOV-1 能力内化 | 纪律注入 + 收工自审固化 + 新人开箱测试 | ✅ 已合并 2edb207（含打回重修：discipline 段曾致 prompt.budget 事件被丢；教训册 +L13 且已进 wrapup 注入清单） |
| 1 | DESK-V4 桌面小组件（owner 22:33 拍板：提至 GOV-1 后第一顺位；22:59 钉死**第一铁律：只读投影、零干涉**） | **定位=桌面端的只读映射投影，非独立应用**：Electron frameless 半透明小窗贴桌面，显示「我的要求 + bobo 的执行」（**不显示 session 侧栏、不显示 plugins 面板**）+ **diff 完整渲染（owner 23:03 拍板：diff 必须有，高亮底色 1:1 带进小窗）**；**窗口可拖拽调大小、内容自适应铺开、最小尺寸锁定**（owner 23:03）；样式与桌面端 1:1 同渲染管线零偏差；数据全部只读自取 gateway 现成数据流，**不改桌面端任何状态/布局/行为，主窗关掉小组件、关掉小组件主窗，互不干涉**；审批时橙边轻闪点击跳主窗；WidgetKit 原生版等 Apple 签名 | ✅ 已合并 db5876d（回滚标签 rollback/pre-desk-v4；全量 2498 passed） |
| 2 | DESK-V4B 小组件会话钉选 + BUSYGATE 忙碌隔离 | 钉选三向同步（行内投影按钮/小窗轮换/删除回落）；**追加⓪ 忙碌态按会话隔离**——_busySids 按 sid 登记，A 跑只锁 A、B 空闲可独立开跑（owner 23:51 实弹抓的 bug 已修） | ✅ 已合并 07b0f20（全量 2510 passed；回滚标签 rollback/pre-desk-v4b） |
| 2.5 | 黑名单硬拦 git reset --hard（owner 23:56 拍板） | DANGEROUS_PATTERNS 新增，AUTO 硬拦；soft/裸 reset 不误伤 | ✅ 已合并 122a3ec（全量 2512 passed） |
| 3 | DESK-CLI `bobo desktop` 子命令（owner 22:33 拍板——"下次我自己终端输 bobo desktop 也会快很多"） | CLI 加 desktop 子命令：检测 node_modules→缺则自动 npm install→npm start 拉起 Electron；配套新人上手 README（clone→pip install -e .→bobo / bobo desktop 全流程） | 📋 V4B 之后 |
| 3 | DESK-V2C3 记忆面板 | 右侧滑出抽屉 + /memory 命令入口（摆放方案待 owner 最终点头） | 📋 待确认 |
| 4 | DESK-V2D 美学微票串（owner 12:19/12:24 定调：**incremental——一票只改一处精调，大 CSS 骨架一概不动**；每票独立 rollback 标签，改完一处 owner 实弹看过再开下一票） | D1 回复正文 Charter 衬线（一处 font-family 变量）→ D2 橙色印章语义（橙=bobo 手笔/灰=机器状态）→ D3 排版细节（中西文混排间距/中标点悬挂/引用块 serif：中楷体西 Charter）→ D4 纸感浮起（更浅卡片底+暖调半透明阴影，不碰 noise）→ D5 药丸升认知状态条（水位+记忆数+工具数） | 📋 逐票精调 |
| ⏸ | COST-1a 工具画像+外置实验 | ✅ 沙盒完成（**结论封存：B 合并 14 档=平衡点，100% 成功率且省 37%**；PARK-2 合并落地 + /tools 指令**暂缓，owner 思考中**） | ⏸ 封存 |

**✅ 已完成（近期，新→旧）**

| 票 | 合并 |
|---|---|
| DESK-V2D25 工具卡精致化 | 9a168e0（细线 SVG 图标 TOOL_ICONS+_default 回退/data-state 三态/shimmer 流光+reduced-motion 禁用；CSS 全进锚点段零新增颜色；顺手修复 friendlyMap 未定义 ReferenceError；附带补票 INT-1 漏网测试入库；全量 2476 passed；回滚标签 rollback/pre-desk-v2d25） |
| GUI-F12 历史聚合渲染 | 2db1b6c（过往回合思考+工具链收聚合卡/最新一轮平铺/diff 语义保留；自审四修复：冒泡误收/空链丢思考/histLatest 重置/reflow 统一；抽 buildHistThinkBox/buildHistToolCard 公函数） |
| GUI-F11 自动命名持久化 | 6415ded（rename 加 auto 通道：落盘不置 user_named，已命名拒绝覆盖，TUI 天然同步） |
| DESK-V2C12 Markdown+衬线 | 420bf8a（marked+DOMPurify+highlight.js 全 vendor 本地含 LICENSE；渲染仅 .msg.bobo .txt 一处；Charter 四件 woff2 + --font-reply 中落宋体；CSS 全在锚点段；全量 2459 passed） |
| TOOL-PARK-1 工具外挂仓 | b325736（51 死工具打包 data/tool_park.json 出链：schema 税 8353→4026 tokens/轮（-52%），函数保留可执行 + describe_tool 可取件；全量 2426 passed） |
| COST-1a-SANDBOX 四档实验 | fc75bed（100 次真实 API：B 合并档=平衡点——成功率 100% 持平全量档且比现状省 37% tokens；C 极简最省但笔记能力掉；B 档 action 选错率 27% 可自愈。报告 reports/cost1a_sandbox_report.md） |
| CORE-R3 四刀拆闸 | 7b8e96f（补账豁免/质量闸扩面≥3次执行/完成词短语化+零工具才触发/熔断前施工证据确认通道；全量 2409 passed） |
| GUI-F10 事件流 sid 过滤 | a916d41（串台修复 + 后台活动圆点 + 审批应答回来源会话） |
| CORE-INT2 中断黑洞修复 | 5077771（headers 阶段 join 黑洞补 0.5s 轮询 ≤0.5s 响应 + cancel 四打点；取证：39 次 cancel 对齐，129s 黑洞实锤） |
| DESK-V2B4 药丸修复包 | 71de7ec（kimi-k3 1M + 活引擎数据源 + 实况折叠卡；教训册 +L12） |
| DESK-V2B3 斜杠命令面板 | 59d23a0（斜杠路由 + 命令面板 + IME 保护；+L10/L11） |
| GUI-F9 丢回合修复 | 1e29018（活引擎 history 注册表） |
| DESK-V2B2 进度药丸 | aacdeb3（三色阶） |
| CORE-R2a/R2b 台账软引导+答复质量闸 | 6a62fc4 / 92d232d |
| DESK-V2B 差异化面板 | 31e09cb（工具耗时 + 上下文细条） |
| DESK-V2A 体验地基 | 6d11d0b（覆盖层/搜索/重命名/删除/pin/Toast/三态） |

### 第二梯队：评估与内核深化（排在 DESK-V2 之后，owner 拍板：性能在 GUI 提升后）

| 票 | 干什么 | 状态 |
|---|---|---|
| EV-2 | 评估跑道升级：轨迹回放 + mock 驱动；复活 BLOCKED 的 A5/A7 题；A1 新规则（≤2 次工具）复测；B2 的 test_archive_file_exists 定位 | 📋 排队 |
| COST-1 成本与功耗总线（owner 2026-08-14 拍板：**GUI 票收官后全队注意力转向此处**） | 三端成本体检：① API token 成本（TOOL-OPT 已有实证：26.7% 纯重复调用/2.8 亿 tokens/3 天）② 桌面端 Electron 内存/CPU 常驻功耗 ③ TUI 与后端 gateway 常驻开销 ④ 对照标杆：DeepSeek Harness 单任务约 2 毛钱。**速度与成本同一杠杆：前缀缓存命中率（标杆 Pi 99.93%、P99 -42%）+ PTC 减少模型往返 + prompt 瘦身**。产出：测量报告 → 优化票 |
| COST-1a 外置变量实验沙盒（owner 立规：**核心引擎零改动，实验全外置**） | 独立目录搭模拟栈：可调 N 工具/N skill/N 段注入 prompt，实测缓存命中率与速度提升，找 efficiency×ability 平衡点；报告出来前核心一行不动 | 📋 COST-1 第一子票 |
| COST-1b 三端功耗体检 | 桌面端 Electron 常驻内存/CPU + TUI + gateway 常驻开销测量 | 📋 随 COST-1 | 📋 GUI 梯队收官后启动 |
| TOOL-OPT 实验线 | 工具调用效率（COST-1 的子线）：读文件缓存/同回合去重/纯读结果复用；借鉴 DeepSeek Harness PTC 程序化工具调用 → EV-2 轨迹回放做 A/B | 📋 并入 COST-1 |
| EVAL 体验题 | 同一真实任务 Hermes/bobo 桌面端对照跑，体验差距量化 | 📋 待开 |
| vitest 存量 13 失败 | gatewayClient websocket 10 个等陈年老账立案清理 | 📋 排队 |

### 第三梯队：体系化界面能力（ROADMAP 原规划）

| 票 | 干什么 | 状态 |
|---|---|---|
| DESK-V1 票据面板 | **差异化核心**：界面新增票据视图（当前票/台账进度/五查状态/回滚点），批准合并+rollback 一键完成；对标 Hermes REVIEW 但更深 | 📋 待开 |
| GUI-F5 会话分组 | 时间分组（今天/本周/本月）；置顶已并入 DESK-V2A | 📋 待开 |
| DESK-V2 模型/底栏 | 底栏模型选择器 + 当前分支显示 + 本回合改动统计（+N/−M） | 📋 待开 |
| WORKER-V1 worker 产品化 | 机制先行、GUI 辅佐（owner 2026-08-13 裁决）：用户可指派角色的并行 worker（research/写码分工）→ 系统层重设计后再做右面板 tab 视图；现状=引擎自派、用户无入口 | 📋 缓做，等系统层讨论 |

### 第四梯队：治理与组织

| 票 | 干什么 |
|---|---|
| GOV-1 能力内化（owner 15:15/15:17 拍板：**D25 后即刻做**，训练成果必须开箱自带） | ①教训册/工作流纪律进系统提示词自动注入（引擎级触发，不靠叮嘱）②收工自审 diff 固化成提示词级标准动作（实证：bobo 自审 F12 自抓 4 bug）③EV-2 加"新人测试"：零上下文 bobo 开箱验证查码/改码/自验/全量回归 |
| 三方协作模式固化 | bobo 施工 / Kimi 终审 / **Hermes 独立尸检**（2026-08-14 实证：Hermes 读 events.jsonl 解剖出 R3 根因链，799 次误伤铁证）——疑难杂症互诊机制写入章程 |
| 章程 v1.1 | 宪章 HARCHITECTURE 升级：编制/派单/降级规则 + 降级策略全景章（四分法骨架：深度/范围/频率/危险度）+ ENG-2 战果入宪 |
| E5 清理 | data/.env 17-42 行粘贴散文坏行修复（等 owner 说"清"） |
| worktree/分支大扫除 | 残留 worktree + 已合并分支归档删除 |

### 远期战略（owner 拍板项）

| 项 | 触发条件 |
|---|---|
| Apple Developer 签名发布 | **仅打包分发（.dmg 直接下载/自动更新/iPhone 版）才需要**（$99），不提前；开源路径免签——新人 clone repo → `pip install -e .` → `bobo desktop` 即可拉起桌面端（dist/ 与 vendor/字体均已强制入库，Electron 走 npm 官方签名包，Gatekeeper 不介入用户自跑开发命令）；待办票：新人上手 README + `bobo desktop` 子命令（检测 node_modules→自动 npm install→npm start） |
| DESK-V3 Automation 侧栏 | 定时任务进侧栏（对标 Hermes CRON JOBS，我们体系现成） |
| 造 Agent 方向讨论 | 战略级对话，等桌面端稳定后展开 |
| 电脑操控方向（BROWSER-1→COMPUTER-1） | 2026-08-13 讨论后 owner 拍板"先放着"：真实浏览器 CDP 驱动（可并行多窗口）→ 像素级操控（串行、需签名权限）；重启讨论前不动 |
| iPhone 版 bobo（owner 15:17 长远想法） | 可行路径=iPhone 做瘦客户端连家中 Mac 的 gateway（我们 JSON-RPC/WebSocket 架构现成，桌面端本身就是这么连的）；手机端不做本地 agent（无文件系统/终端），定位=远程监视+指令+审批。等桌面端稳定 + Apple 签名后展开 |

## 固定循环（每张票的生死流程）

```
owner 实弹抓问题 / 队列取票
  → Kimi 开票（含验收标准+授权路径）
  → owner 亲手发给 bobo
  → bobo 施工（分支+台账+五查）
  → Kimi 亲手终审（专项复跑+全量+md5 闸门+代码抽查）
  → 合并 main + rollback 标签 + 推送
  → owner 实弹验收
```

铁律：不 merge 不 push 等终审；内核改动需特批；每票必留回滚点。

## 已完成战役（2026-08-12/13）

D-1 桌面复活（审计/通电/Electron 43/共享后端/GUI 平齐）→ GUI-F1（输入法/thinking/轰炸）→ ENG-2（防僵尸+终端复位，破崩溃案）→ ENG-1（答完不收工）→ GUI-F2（发送键/AUTO开关/聚合/层级）→ GUI-F4（聚合吞并/diff 高亮/JSON/撞车/面板/AUTO 对齐+内核缺参修复）→ OBS-1（load_result 套娃）→ GUI-F3（会话一等公民/diff 同级整行底色/thinking 分段/空落盘兜底）→ DESKTOP_VISION 成文 → AUTO-G1（git 只读误杀）→ GUI-F6（thinking 分段+历史恢复）→ GUI-F7（手动命名优先）→ GUI-F6B（连续思考合并）→ PERF-1（收尾黑洞+空回复自愈+沉淀后台化）→ INT-1（Interrupt 一刀切）→ AUTO-G2（清单增量+折叠卡+清零命令+heredoc 收紧）→ CORE-R1（150 轮+死循环硬掐/推进软着陆+60% 水位）→ F6C（思考随工具吞并）→ LEDGER-1（台账重构+对账+汇报质量）→ F6D（状态行跳过+写类工具思考摊开）→ LEDGER-1B（对账段改内部注入）→ GUI-F8（历史 diff 恢复+思考持久化）；Hermes 桌面端源码研读完成（差距清单 A/B 两类，A 类追平立项 DESK-V2A/B/C）

当前 main: 94558e9 · 测试基线 2476 passed / 2 skipped / 1 xpassed · 回滚标签全部在远端
