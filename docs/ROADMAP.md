# ROADMAP — bobo 体系作战地图

> v3.0 · 2026-08-14 · 随每票终审合并滚动更新；发现新问题/新想法 → 补进本文件对应梯队

## 当前队列（按执行顺序）

### 第一梯队：桌面端体系化（A 类追平，owner 2026-08-13 拍板；铁律：现有 CSS 视觉零改动）

| 序 | 票 | 干什么 | 状态 |
|---|---|---|---|
**▶ 待施工（按执行顺序）**

| 序 | 票 | 干什么 | 状态 |
|---|---|---|---|
| 1 | CORE-R3（P0，下一张） | 答复压制源排查与拆除：owner 定调——好答复是自然反应，必是被某机制卡住，**找限制拆限制，禁止叠新机制**。**根因已被外部取证坐实**（events.jsonl：收尾 15 次 10 次空回复、收工闸误伤 deny 799 次/库）：三闸叠加逼死正常收尾，修复四刀已定为收窄/拆除 | 📋 票已写，即刻可派 |
| 3.5 | RESEARCH-DSH | bobo 亲拆 DeepSeek Harness 源码（一切皆插件/9 子代理/PTC/缓存键/Session Log），产出对照笔记入 library，兼作研究能力测试 | ✅ 已完工（笔记 182 行带源码行号，Kimi 抽查引用属实）；可移植清单待消化进 WORKER-V1/TOOL-OPT/COST-1a/EV-2 |
| 2 | DESK-V2C1+C2 样式票 | 完整 Markdown 渲染（粗斜下划线/表格/代码高亮，owner 要求 99% 成功率）+ 回复正文衬线（Charter 类，Anthropic Serif 有版权坑不捆）；双语通用排版不针对单语言；样式票独立回溯纪律已立（GUI-DESIGN 规则 6） | 📋 待开 |
| 3 | DESK-V2C3 记忆面板 | 右侧滑出抽屉 + /memory 命令入口（摆放方案待 owner 最终点头） | 📋 待确认 |

**✅ 已完成（近期，新→旧）**

| 票 | 合并 |
|---|---|
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
| 三方协作模式固化 | bobo 施工 / Kimi 终审 / **Hermes 独立尸检**（2026-08-14 实证：Hermes 读 events.jsonl 解剖出 R3 根因链，799 次误伤铁证）——疑难杂症互诊机制写入章程 |
| 章程 v1.1 | 宪章 HARCHITECTURE 升级：编制/派单/降级规则 + 降级策略全景章（四分法骨架：深度/范围/频率/危险度）+ ENG-2 战果入宪 |
| E5 清理 | data/.env 17-42 行粘贴散文坏行修复（等 owner 说"清"） |
| worktree/分支大扫除 | 残留 worktree + 已合并分支归档删除 |

### 远期战略（owner 拍板项）

| 项 | 触发条件 |
|---|---|
| Apple Developer 签名发布 | 桌面端成为每日主力后再买（$99），不提前 |
| DESK-V3 Automation 侧栏 | 定时任务进侧栏（对标 Hermes CRON JOBS，我们体系现成） |
| 造 Agent 方向讨论 | 战略级对话，等桌面端稳定后展开 |
| 电脑操控方向（BROWSER-1→COMPUTER-1） | 2026-08-13 讨论后 owner 拍板"先放着"：真实浏览器 CDP 驱动（可并行多窗口）→ 像素级操控（串行、需签名权限）；重启讨论前不动 |

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

当前 main: 4fb8237 · 测试基线 2386 passed / 2 skipped / 1 xpassed · 回滚标签全部在远端
