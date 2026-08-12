# TICKET-D1: 桌面版复活——全栈刨根审计 → 通电 → 共享后端 → GUI 平齐 TUI

| 属性 | 值 |
|------|-----|
| 分级 | L3 |
| 分支 | feat/ticket-d1 |
| 前置 | 无（自 main 763c376 切出） |
| 授权路径 | apps/desktop/**、tests/**、docs/**；内核文件（core/、bobo_tui_gateway/）**只读**，确需改动必须单列报 Kimi 批准 |

## 背景

桌面版（apps/desktop/，Electron ^33）最后改动停在 2026-07-25（146778e）。此后内核发生大量变更：socket 模式、BOBO_BACKEND=1 纯后端模式、崩溃黑匣子（frontend_<pid>.log）、闸（goal_gate）、自我地图注入、EVAL 跑道等。桌面版大概率已无法正常工作。

已知结构性矛盾：`electron/main.cjs` 直接 spawn `python -m bobo_tui_gateway.entry`，而现行 entry 默认会再 spawn Node TUI——桌面版必须改走 `BOBO_BACKEND=1` 纯后端模式。

owner 战略：桌面端与 TUI 同步升级；GUI 先做到与 TUI 功能平齐、无明显 bug，后期再打磨；Apple 签名等成熟后再买，本票不做。

## 施工内容（严格按顺序，上一步验收不过不得进下一步）

### D-1a 全栈刨根审计（本票第一步，最重）

把桌面端所有问题全部挖出来，四层全翻，不许遗漏、不许边修边发现：

- **前端 renderer 层**：dist/index.html 全部静态资源、与后端的 JSON-RPC 消息协议（发了什么、期望收什么）
- **Electron 主进程层**：main.cjs / preload.cjs——后端 spawn 方式、Python 路径解析、数据目录、环境变量、重启策略、窗口生命周期
- **后端接口层**：对照现行 bobo_tui_gateway 的 JSON-RPC 方法清单与事件通知，逐项核对桌面版代码在调什么——哪些方法还存在、哪些已改名/删除/语义变更
- **底层依赖层**：package.json / electron-builder 配置、Node 版本要求、extraResources 打包路径（指向 ../../core 等是否仍有效）、install.sh 现状（user-site/pipx/venv 三级）对齐情况
- **实跑取证**：亲手起一次桌面版（npm start 或等效），完整记录每一个报错/异常行为，截图或日志留证

产出：`docs/DESKTOP_AUDIT.md` 完整问题清单，每条含：层级、现象、根因、证据（文件:行 / 日志摘录）、修复建议、严重度（阻断/高/低）。**此清单是后续所有修复的唯一依据，修复阶段发现清单外的新问题必须回报 Kimi，不得擅自扩大范围。**

### D-1b 通电复活（最小修复）

按审计清单只修"阻断级"：main.cjs 改走 BOBO_BACKEND=1 纯后端模式；数据目录、Python 路径解析对齐 install.sh 三级现状。
验收：Electron 窗口完成一轮真实对话（发消息、收回复），黑匣子日志正常落盘。

### D-1c 共享后端同步机制

桌面版不复制内核代码，与 TUI 共用同一个已安装的 bobo 后端（同一 ~/.bobo 数据目录、同一 Python 环境），内核升级一次两端同时生效。extraResources 打包内核仅保留为发布 dmg 时的路径，开发期走共享后端。
验收：改一处内核可见行为（如 [NOW] 锚点），TUI 与桌面版同时体现。

### D-1d GUI 平齐 TUI（先平齐后打磨）

拉 TUI 能力清单逐项对齐：消息流、工具调用折叠显示（可展开/收起）、diff 显示、模式切换（普通/AUTO/OFFICE）、状态行（ready/running）、会话恢复、中断（esc 等效物）、黑匣子日志入口。视觉语言**保持 Electron 当前样式不变**——背景、字体、颜色全部沿用桌面版现状（owner 2026-08-12 明确裁决：平齐的是 TUI 的功能，不是 TUI 的皮；不得换成 TUI 皮肤，不得另起视觉设计）。**每一项都要有、每一项无明显 bug。**打磨（动画、精排版、快捷键体系）不在本票。

**决策点**：D-1a/b/c 完成后，按审计清单评估 d 的工作量报 Kimi——一张票做完或拆 D-1d 单独票，由 Kimi 定。

### D-1e 对齐清单验收

同一任务在 TUI 与 GUI 各跑一遍，功能与体验对等；产出对照表作为验收证据。

## 明确不做

- Apple Developer 签名 / 公证 / 自动更新
- UI 精修打磨
- 内核代码改动（只读，确需改动单列报批）

## 验收标准

- [ ] 1. docs/DESKTOP_AUDIT.md 四层问题清单完整，条条有证据
- [ ] 2. 桌面版一轮真实对话跑通，黑匣子落盘
- [ ] 3. 共享后端生效实证（内核改动两端同步）
- [ ] 4. TUI 能力对照表全项平齐，无明显 bug
- [ ] 5. 全量 pytest 零回归（桌面版改动不应影响内核，跑一遍作证）
- [ ] 6. 五查汇报 + 未 merge 未 push 等终审

## 纪律

- 修阻断之外的问题前必须对照审计清单，清单外问题报 Kimi 裁决
- 每阶段完成在台账销号，D-1a 清单出炉即向 Kimi 汇报一次（不等全票完工）
