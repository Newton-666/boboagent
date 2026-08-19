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
| 3 | DESK-CLI `bobo desktop` 子命令 | 子命令分发 + node≥18 人话检测 + 自动 npm install + README 快速开始 | ✅ 已合并 be64f8c（全量 2526 passed；守卫升级为锚点段精确化——收紧非松绑；回滚标签 rollback/pre-desk-cli） |
| 3 | DESK-V2C3 记忆面板 | 右侧滑出抽屉 + /memory 命令入口（摆放方案待 owner 最终点头） | 📋 待确认 |
| 4 | DESK-V2D5 药丸修复+升级 | ⓪ 根因实锤：refreshCtxStats 双重剥壳（call() 已剥壳又取 res.result → d 恒 null → 永停硬编码初值）→ ① 认知状态条（水位+本轮记忆注入+本轮工具调用，meta 弱字） | ✅ 已合并 c6a8d5e（实弹截图实证药丸真实上涨 87K→88K；全量 2532 passed；回滚标签 rollback/pre-desk-v2d5） |
| 4.5 | GUI-F13 历史像素级复原 + 丝滑窗口化（owner 19:46/19:48 拍板） | 统一渲染管线 + 视觉姿势持久化 + 窗口化（>200 条分流/提前 2 屏/占位高度/rAF）；考古聚合降级为开关；零上下文影响 | ✅ 已合并 5d3beb1（全量 2557 passed；**遗留：长会话滚动帧率 Playwright 实测挂 F13b 补票，owner 实弹验收重点**；回滚标签 rollback/pre-gui-f13） |
| 5 | DESK-V2D 美学微票串余下三张（owner 12:19/12:24 定调：**incremental——一票只改一处精调，大 CSS 骨架一概不动**；每票独立 rollback 标签，改完一处 owner 实弹看过再开下一票） | ✅ D5 药丸修复+认知条（c6a8d5e）→ ✅ D6 思考框中性化（419e450，去 emoji/去蓝/同族不同阶）→ ✅ D7 药丸墨痕重设计（6d5e550，方案 A 墨痕填充；思考蓝全面退役，色彩收口=纸+墨+橙印；信息蓝 12 处迁墨灰为票面④授权内的范围扩张，owner 实弹裁决中）→ ~~D2 橙色印章语义~~（owner 20:25 实弹否决：bobo 做过什么工具卡已一目了然，橙印是重复表达，价值不足，**封存**）→ D3 排版细节（中西文混排间距/中标点悬挂/引用块 serif：中楷体西 Charter）→ D4 纸感浮起（更浅卡片底+暖调半透明阴影，不碰 noise） | 📋 D3 待开 |
| ⏸ | COST-1a 工具画像+外置实验 | ✅ 沙盒完成（**结论封存：B 合并 14 档=平衡点，100% 成功率且省 37%**；PARK-2 合并落地 + /tools 指令**暂缓，owner 思考中**） | ⏸ 封存 |
| **GUI-F16 桌面端 markdown 数学公式渲染（2026-08-18 开票，owner 实弹反馈）** | 桌面端助手正文缺 KaTeX——marked 不解析 LaTeX，`$x^2$` 显示为裸源码（实测原样输出）。修：KaTeX vendor 本地化（dist/vendor/ 对齐 marked/hljs 先例）+ mdReply 管线接公式渲染（先保护代码块再提取 $...$/$$...$$，占位符还原，渲染失败原样容错） | ✅ 已合并 b5f37354 |
| **GUI-F17 停止假中断（Hermes 评审 Bug 1，严重）** | stopThinking 的 session.interrupt 只在 thinkBoxEl 非空时发；tool.start 收束思考框置 null → 工具执行期间停止失效。修：interrupt 无条件发 | ✅ 终审通过，待 owner 实弹 + 收编 |
| **GUI-F18 Esc 路由优先级 + 清空会话模态化（Hermes 评审 Bug 2+4）** | Esc 双监听冲突 → 浮层优先级链 + stopPropagation；清空会话原生 confirm 改 askConfirm（L6） | 📋 排队（票 docs/tickets/TICKET-GUI-F18.md） |
| **GUI-F19 滚动锚定（Hermes 评审 Bug 3）** | 8 处无条件 scrollTop → isNearBottom 判定 + 统一 scrollToBottomIfNear | 📋 排队（票 docs/tickets/TICKET-GUI-F19.md） |
| **GUI-F20 设置空 key 保存弹窗不关（Hermes 评审 Bug 5）** | settings-save 空 key 时弹窗照样关。修：空 key return 不关弹窗 + 内联错误 | 📋 排队（票 docs/tickets/TICKET-GUI-F20.md） |
| **GUI-F21 桌面端历史渲染对齐实时** | 实时=聚合卡+最新摊开+思考吞并；历史默认平铺 → 不一致。修：历史默认聚合形态 + 编辑流摊开 + 窗口化同步 | ✅ 终审通过，待 owner 实弹 + 收编 |
| **GUI-F22 侧栏折叠按钮置顶** | 折叠按钮（SVG）移到 Session 头之上（owner 实弹；首次未 commit 被覆盖，重建提交） | ✅ 已合并 aee40d6f |
| **GUI-F23 草稿会话模式（2026-08-18 owner 定案 Hermes 同款）** | 启动/New chat 进草稿态（初始页、左侧栏不新增）；首条消息才 session.create → 会话浮现（动画）；根治"启动进会话却显示初始页" | ✅ 已合并（f23 分支并入 F22 后收编，回滚标签在远端） |
| **GUI-F24 Request 面板——会话级 Roles/Rules 设定与注入（2026-08-18 owner 设计定案）** | Work with a project 旁加 Request ▾：自由输入 Roles/Rules + 保存（会话级持久化）；injector 尾部动态块注入（复用 project_root 先例）；Office 无关纯引导 | ✅ 已合并 785f35ca（+ pill 并排对齐 744076e9） |
| **GUI-F25 Request 保存失败修复（2026-08-18 开票，owner 实弹：Save failed: unknown）** | 双 bug：①前端 call() resolve err 本体→res.error 恒 undefined→吞错显示 unknown（修 errMsg 三形态兼容）；②后端 set_request 池外会话返回"会话不存在"（修磁盘兜底加载，对齐 resume 语义） | 📋 排队（票 docs/tickets/TICKET-GUI-F25.md） |

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
| **P0-1 记忆六类分类 + Memory 模块 UI（2026-08-19 开票，自进化系统第一票）** | 自进化施工开始（快照 snapshot/pre-self-evolving-20260818 已打）。记忆六类（USER_PREF/RULES/FACT/ACHIEVEMENT/LESSON/GOAL）+ 656 条历史迁移（确定性启发式+人工抽查）+ 指针校验 + 侧栏 Memory 模块（diff 增删/token 统计/手动编辑）。独立价值：解决现有 656 条失控 + 空分类 | ✅ 已合并推送（2026-08-19，回滚标签 rollback/pre-p0-1 在远端）；Memory 面板实弹通过
| **REASONING-ECHO thinking 模式 reasoning_content 回传（2026-08-19 开票，P0-1 施工阻塞 bug 定案）** | DeepSeek thinking 模式要求两个 user 消息之间夹工具轮时 assistant 必须回传 reasoning_content（否则 400）。根因：收集✅（llm_caller:552）→ 落盘❌（engine 存 thinking 而非 reasoning_content）→ 回传❌（发送侧 0 处转换）。修复：injector.build_messages 发送副本 thinking→reasoning_content（方案 B，不动 history），压缩路径覆盖 + 回归测试 | ✅ 已合并推送（2026-08-19，回滚标签 rollback/pre-reasoning-echo-20260819-1800 在远端）；等 owner 实弹多轮施工确认不再 400
| **P0-2 信号日志化双通道（2026-08-19 开票，自进化第二票）** | 对话信号（guidance 四条：工作流/负强化/隐含偏好/强信号，LLM 判定）+ library 主题频率信号（确定性统计）——**只记录不动作**（零记忆写入/模型变化，md5 锁死），两周看信号密度质量再定 P1。抗自举崩溃的证伪实验（Hermes 17 节） | ✅ 已合并推送（2026-08-19，回滚标签 rollback/pre-p0-2-20260819-1900 在远端）；两周后 owner/Hermes CLI 评估信号质量决定 P1
| **P0-3 缓存实测（2026-08-19 开票，自进化第三票）** | 量化尾部动态块变化对 DeepSeek 前缀缓存命中率的影响（四场景：同主题微调/完全替换/长度变化/头部对照，≥3 次取样取中位数）——纯实验不改功能，产出测量报告，决定 P2 evolved 投影经济模型（P2 开门闸，未闭合项 #1 缓存红线） | ✅ 已合并推送（2026-08-19，回滚标签 rollback/pre-p0-3-20260819-2000 在远端）；未闭合项 #1 缓存红线闭合——尾部注入不塌缓存（位置敏感/内容不敏感），P2-1 硬约束=注入位置尾部
| **P0-5 记忆偏好变更替换 + memory.changed 实时刷新（2026-08-19 开票，自进化第四票，负面淘汰雏形）** | owner 实弹：说"不喜欢冰美式了喜欢 dirty"期望红删绿增替换，实际旧条并存无 diff。三缺口一次补：①偏好变更识别（确定性规则：同主题+反转关键词→旧条 archived+降权归零+新条写入+REPLACE 审计，零 LLM 淘汰判断）；②memory.changed 事件（add/delete/retype/replace 广播）；③前端实时刷新（面板开→自动 diff 红删绿增；未开→只更 count）。衔接 P0-5 负面淘汰 + DISCUSSION 11.3-c | ✅ 已合并推送（2026-08-19，回滚标签 rollback/pre-p0-5-20260819-2010 在远端）；等 owner 实弹（说"不喜欢X喜欢Y"→ 面板实时红删绿增）
| **COST-6 COST-2 动态块写回 → 双 user 夹工具轮 → thinking 400（2026-08-19 开票，二次事故根因定位）** | 400 真正根因：动态块写回 history 制造"user#0→103工具轮→user#104"触发结构（REASONING-ECHO 只修回传没修结构）。修复：消除双 user 夹工具轮（方案 A 不写回/B system 角色/C 去重，三选一实测定案），**双验收硬约束**：缓存命中率改前改后对比不塌（COST-2/3 战果 99.8%/≥85%）+ 400 复现测试防回归 | ✅ 已合并推送（2026-08-19，回滚标签 rollback/pre-cost-6-20260819-2100 在远端）；缓存 99.9%→99.6% 不塌，长会话不再 400（重启后生效） | | | | | |
| **VSC-2C 工作目录感知 + 工具图标 SVG + 对比度核验（2026-08-17 owner 实弹热修）** | ①bobo 感知不到 VS Code 打开的文件夹（send 入口 project_root 错误依赖选区）；②工具图标 emoji→桌面端同款细线 SVG（L4）；③对比度核验。终审已过（npm 91/91、pytest 2722/2/1、md5 3/3），owner 实弹通过（部署新代码后 3 问题解决） | ✅ 终审通过，待收编（feat/ticket-vsc-2c 工作区 6M+2新，未 commit） |
| **VSC-2D 裸 HTML 元素化修复（2026-08-18 开票）** | bobo 回复里未包代码块的裸 HTML 被 marked+DOMPurify 当真渲染成 DOM→标签文本消失/被盖住/字变灰。根因实证 + 修复方案已 node 实测。修：marked 自定义 html renderer 转义为文本 | 📋 排队（票 docs/tickets/TICKET-VSC-2D.md） |
| **VSC-2E VS Code AUTO 模式支持（2026-08-18 开票，owner 实弹）** | ①写审批闸门 _guarded_execute 不感知 AUTO→AUTO 开了照样弹审批（根因实证 engine.py:204 决策树 vs engine_adapter 闸门）；②VS Code 面板补 AUTO 开关（对齐桌面端 #auto-toggle，走既有 /auto 命令零后端新 RPC） | 📋 排队（票 docs/tickets/TICKET-VSC-2E.md） |
| **VSC-2F 审批双端弹窗 + 联通开关（2026-08-18 开票，owner 实弹）** | GW-MULTI 事件全广播→approval.request 双端都弹。加设置 bobo.syncWithDesktop（默认 true）：关闭时 VS Code 不弹审批卡（审批由桌面端处理），事件流维持 sid 过滤。语义取舍待 owner 点头（isolated 下桌面端不在线则 120s 超时） | 📋 排队（票 docs/tickets/TICKET-VSC-2F.md，语义待 owner 确认） |
| **VSC-2G diff 删除栏不显示（2026-08-18 开票，owner 实弹严重问题）** | vscode.diff 左栏（删除侧）显示不好/有时完全不显示，新增侧正常。候选根因 C1 新建无旧内容/C3 diff 编辑器折叠未修改区/C4 快照 uri 编码——L14：先复现取证再修，不许只修一个收工 | 📋 排队（票 docs/tickets/TICKET-VSC-2G.md，需 owner 提供修改场景实弹证据） |
| EV-2 | 评估跑道升级：轨迹回放 + mock 驱动；复活 BLOCKED 的 A5/A7 题；A1 新规则（≤2 次工具）复测；B2 的 test_archive_file_exists 定位 | 📋 排队 |
| COST-1 成本与功耗总线（owner 2026-08-14 拍板：**GUI 票收官后全队注意力转向此处**） | 三端成本体检：① API token 成本（TOOL-OPT 已有实证：26.7% 纯重复调用/2.8 亿 tokens/3 天）② 桌面端 Electron 内存/CPU 常驻功耗 ③ TUI 与后端 gateway 常驻开销 ④ 对照标杆：DeepSeek Harness 单任务约 2 毛钱。**速度与成本同一杠杆：前缀缓存命中率（标杆 Pi 99.93%、P99 -42%）+ PTC 减少模型往返 + prompt 瘦身**。产出：测量报告 → 优化票 |
| COST-1a 外置变量实验沙盒（owner 立规：**核心引擎零改动，实验全外置**） | 独立目录搭模拟栈：可调 N 工具/N skill/N 段注入 prompt，实测缓存命中率与速度提升，找 efficiency×ability 平衡点；报告出来前核心一行不动 | 📋 COST-1 第一子票 |
| COST-1b 三端功耗体检 | 桌面端 Electron 常驻内存/CPU + TUI + gateway 常驻开销测量 | 📋 随 COST-1 | 📋 GUI 梯队收官后启动 |
| COST-4 结果标记/load_result 循环 + 压缩频率治理（2026-08-17 开票，接 COST-2/3 战线的实测新发现） | 根除"读文件=read+load_result 两步走"重复调用（read_local_file 分级标记，<2000 字符不标记直给全文）；压缩摘要调用可观测化（llm.usage 带 reason:summary）+ 预算比 0.7→0.85 拉长压缩间隔；工作锚点补"已读文件"防压缩后重读。背景实证：VSC-2B 施工时段命中率 13%（压缩黑洞 hit=7.7K miss=5.1万）、Repeated read ×8、上下文 60K→111K 暴涨 | 📋 排队（票 docs/tickets/TICKET-COST-4.md） |
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
| **产品纲领（owner 20:28 拍板）：一切都可见，一切都透明** | bobo 的差异化路线：不只心理安全感，而是 workflow/工具调用/执行历史/策略全部可见——药丸（上下文可见）→ 小组件（执行可见）→ F13（历史可见）→ 审计事件流（尸检可见）→ DESK-V1 票据面板（治理可见，待开）都是这条线的果实；后续讨论再展开，不着急 |
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

08-14/15：PARK-1 工具外挂仓（schema 税 8352→4025）→ COST-1A 沙盒实验（B 档平衡点）→ D25 工具卡 SVG+流光 → GOV-1 纪律内化 → V4/V4B 小组件+忙碌按会话隔离 → CLI bobo desktop → D5 药丸修复 → D6 思考框中性化 → D7 药丸墨痕（思考蓝退役）→ F13 历史像素级复原+窗口化 → DESK-TEL Telescope 观测台（五区战报+活表格+diff 弹层+历史轮+delta 节流，终审打回一处修复后通过）

DESK-TEL 热修（幻影 render→mdReply，L14 立规）→ COST-1b Token 度量层（rounds.jsonl 双观测注入+重复劳动侦测+消耗页签+cost_report.py；gateway 白名单授权模式确立）

TEL-b 表格管道符转义 → GUI-F14 初始化链解耦（loadSession 15s 超时兜底 + readyFallback 同症状补修，Plugin 空白/药丸恒 0% 根治）

COST-1c 度量层数据质量补强（缓存透传+逐次累计+target 抓取；真实数据验收通过：cache 1920/54445、usage_calls=35）→ GUI-F15 Plugin 图标 SVG 化

COST-2 前缀稳定化（小时级锚点+尾部动态块统一注入 user 消息；实测 R3 起缓存命中 99.8%，基线 3.4%——账单结构性打折落地）

SAFETY-1 进程杀灭分级（pkill/killall 黑名单 + kill PID 强制审批 + bobo 进程标识硬拦）+ 后端 code-0 自动重启 + 1345 空值守卫

DIAG-1 调试纪律场景注入（复现→取证→验证→定位→修后验证 五步纪律 22 触发词）——实战验收：药丸埋雷（id 少字母 e）被独立抓出，定位精确到行，修后自发全量回归 + 排除 owner 进程

COST-3 长会话缓存杀手清除（工作锚点属性化移出 history + 工具集 31 schema 会话内逐字节稳定）——e2e 12 轮长会话三连 93.7/93.6/95.5%；a 口径修正：R2 ≥85% 稳定为引擎可控线，R3 掉落实证为 provider 缓存时序（hit 前沿逐字节相等），引擎无 cache_control 可控点；副产物：探针 profile 隔离/newChat/ fail-fast 三修正

当前 main: 含 COST-3 · 测试基线 2693 passed / 2 skipped / 1 xpassed · 回滚标签全部在远端

DESK-P1 欢迎屏 Charter 文案（"Let's finish up something today." serif 700/30px）+ Work with a project 会话项目根（原生选夹 + 最近项目 + project_root 尾部注入，无项目零注入）



DESK-P2 界面全英文化（106 HTML + 278 JS 字符串，"仍在工作"心跳协议串豁免）+ 欢迎屏极简（副标题/常驻状态条删除，标题居中 36px）+ 侧栏 panel-left 折叠图标



VSC-1 VS Code 扩展最小闭环（apps/vscode-extension/：Ask bobo 选中即问 cmd+shift+B + Explain 教学模式 + unix socket JSON-RPC 客户端含退避重连；协议级实弹 Explain OFF/ON 双模式通过；UI 级实跑待补）



待发票仓（docs/tickets/）：VSC-3（桌面端体验完整搬进 VS Code + vsix 私有分发）/ 连接韧性 / DESK-V1 / V2C3 / CLEAN / 桌面端低对比色回同步（VSC-2A 治理后）
待讨论（2026-08-18 owner，不急）：**diff 显示增强**——VSC-2G 只修"删除栏不显示"，diff 两栏展示的信息密度/美观度提升（如改动统计、上下文行数控制、行内词级高亮）另行讨论后再开票

GW-SOCK 桌面端后端 socket 常驻（固定名 bobo-gw-main.sock + 防双实例拒绝 + 断连后端不死重连恢复；VS Code 扩展自动连接打通；Kimi 终审修专项 ROOT off-by-one 后 6/6）

GW-MULTI socket 后端多客户端并发（listen(16) + 每连接一线程 + 事件全广播/RPC 定向写 + 全部断开才计空闲；治 VS Code "not connected" 根因——桌面端占线时扩展握手成功但 5s 超时；Kimi 终审并发实弹 PASS：A 长连占线下 B 完整流式问答；合并 d77aad5a）

VSC-1B VS Code 侧边栏落地 + 连接死锁双 bug 修复（Bug1 package.json 补 viewsContainers/views 注册 + bobo.svg 图标；Bug2 sessionId 不再被面板状态绑架——"not connected" 假报错根治；选中代码实时预览卡片 300ms 防抖；ask 报错拆分 not_connected/connecting 自动重试；Kimi 终审裁决 tel 守卫放行 apps/vscode-extension/ 独立 npm 子项目；npm 40/40 + 全量 2722 零失败；合并 c6adbe89）

VSC-1C VS Code 面板渲染复刻桌面端（marked+DOMPurify+highlight vendor 本地化 + 消息气泡/代码块/表格/diff 增色全套 design token 照抄 + 空态欢迎标题；Kimi 终审 npm 46/46×2 稳定 + 守卫 20/20；合并 ba60dd58）

VSC-2 VS Code 完整聊天+diff 协作+对比度治理（New chat/会话切换/思考折叠/工具行 + tool.start 内存快照→vscode.diff→Accept/Reject 逐字节还原 + 对比度矩阵单测；自审修 existed 高危 bug；Kimi 终审 RPC 实探核实 session.resume/list/inline_diff 均真实存在；合并 da71c50d）

VSC-2B 扩展写审批闭环（approval.request 监听 reason=write_approval 串行闸门单卡 + 移除原生确认框 + 审批卡 Accept/Reject 逐字节还原 + 工具聚合卡 + 停止按钮 session.interrupt；后端 sessions.py 会话级 set_write_approval RPC + engine_adapter 写审批闸门；tel/v4/v4b 守卫补 VSC-2B 特批白名单；Kimi 终审代码层+报告核验合格 md5 5/5 + 全量 2722 补跑背书；npm 84/84 + 守卫 44/44 + 分批 1069 passed；合并 92a6d08e；实弹验收 owner 在 VS Code 执行）

当前 main: 含 VSC-2B · 测试基线 2722 passed / 2 skipped / 1 xpassed + 扩展 84/84 + socket 专项 7/7 · 回滚标签全部在远端（rollback/pre-vsc-2b）
