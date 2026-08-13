# ROADMAP — bobo 体系作战地图

> v1.0 · 2026-08-13 · 随每票终审合并滚动更新

## 当前队列（按执行顺序）

### 第一梯队：桌面端体验收口（进行中）

| 票 | 干什么 | 状态 |
|---|---|---|
| AUTO-G1 | AUTO 模式 git 只读命令误杀修复（status/log 放行，push 仍拦） | 🔧 施工中 |
| DESK-V1 票据面板 | **差异化核心**。界面新增票据视图：当前票、台账进度、五查状态、回滚点；对标 Hermes REVIEW 但更深（五查报告+批准合并+rollback 标签） | 📋 待开 |
| GUI-F5 会话分组 | 侧栏会话置顶（PINNED）+ 按时间分组（今天/本周/本月），学自 Hermes 解剖 | 📋 待开 |
| DESK-V2 模型/底栏 | 底栏模型选择器 + 当前分支显示 + 本回合改动统计（+N/−M） | 📋 待开 |

### 第二梯队：评估与内核深化

| 票 | 干什么 | 状态 |
|---|---|---|
| EV-2 | 评估跑道升级：轨迹回放 + mock 驱动；复活 BLOCKED 的 A5/A7 题；A1 新规则（≤2 次工具）复测；B2 的 test_archive_file_exists 定位 | 📋 排队 |
| EVAL 体验题 | 新增考题：同一真实任务在 Hermes/bobo 桌面端对照跑，体验差距量化（DESKTOP_VISION 第四步机制） | 📋 待开 |
| vitest 存量 13 失败 | gatewayClient websocket 10 个等陈年老账立案清理 | 📋 排队 |

### 第三梯队：治理与组织

| 票 | 干什么 |
|---|---|
| 章程 v1.1 | 宪章 HARCHITECTURE 升级：编制/派单/降级规则 + "团队任务也必须先领票" + office 散场纪律（ENG-2 战果入宪） |
| E5 清理 | owner 的 ~/.bobo/.env 20+ 坏行修复（等 owner 说"清"） |
| worktree/分支大扫除 | 残留 worktree（wt_g1/claude/hermes/pi）+ 已合并分支归档删除 |

### 远期战略（owner 拍板项）

| 项 | 触发条件 |
|---|---|
| Apple Developer 签名发布 | 桌面端成为每日主力后再买（$99），不提前 |
| DESK-V3 Automation 侧栏 | 定时任务进侧栏（对标 Hermes CRON JOBS，我们体系现成） |
| 造 Agent 方向讨论 | 战略级对话，等桌面端稳定后展开 |

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

D-1 桌面复活（审计/通电/Electron 43/共享后端/GUI 平齐）→ GUI-F1（输入法/thinking/轰炸）→ ENG-2（防僵尸+终端复位，破崩溃案）→ ENG-1（答完不收工）→ GUI-F2（发送键/AUTO开关/聚合/层级）→ GUI-F4（聚合吞并/diff 高亮/JSON/撞车/面板/AUTO 对齐+内核缺参修复）→ OBS-1（load_result 套娃）→ GUI-F3（会话一等公民/diff 同级整行底色/thinking 分段/空落盘兜底）→ DESKTOP_VISION 成文

当前 main: 48d83c4 · 测试基线 2158 passed · 59+ 回滚标签全在远端
