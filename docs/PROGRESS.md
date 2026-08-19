# PROGRESS — bobo 当前进度快照

> 2026-08-18 记录 · 随每次终审/合并滚动更新 · 主文档仍是 ROADMAP（本文件只做可追溯快照）

## 〇、2026-08-18 收编完成（VSC-2C / VSC-2D / GUI-F16 已合并推送 main）

- GUI-F16（b5f37354）、VSC-2D（217e6a84）、VSC-2C（e38ec049），回滚标签全部在远端
- main 上 npm 96/96、pytest 2721/1fail（cost1b 分支名环境已知项，另票处理）
- VS Code 扩展已 deploy 最新代码（VSC-2C+2D 全部生效），owner Reload Window 即可实弹
- 数学渲染端到端实弹验证 6/6（行内/块级/中文/分数渲染 + 代码块/货币 $ 不误判）
- 教训：apps/desktop/dist 被根 .gitignore 忽略，收编需 git add -f；VSC 票分支各自
  带 ROADMAP 登记行，合并时冲突保留 main 完整版

## 一、当前主线：VS Code 扩展迭代（owner 大学场景主战场）

扩展已部署版本：`~/.vscode/extensions/bobo-local.bobo-vscode-0.1.0`
**部署状态（2026-08-18 收编后已重新 deploy）：包含 VSC-2C + VSC-2D 全部修复**
（owner Reload Window 后实弹：工作目录感知 / SVG 图标 / 裸 HTML 文本化）。

## 二、票状态总表（按施工顺序）

| 票 | 内容 | 状态 |
|---|---|---|
| VSC-2B | diff 串行闸门 + 聚合卡 + 停止按钮 + 写审批 RPC | ✅ 已合并推送（92a6d08e，回滚标签在远端） |
| VSC-2C | 工作目录感知 + 图标 SVG + 对比度核验 | ✅ 已合并推送（e38ec049，回滚标签在远端） |
| VSC-2D | 裸 HTML 元素化修复（md-render 转义） | ✅ 已合并推送（217e6a84，回滚标签在远端）；待 owner 实弹（已 deploy） |
| VSC-2E | VS Code AUTO 模式（闸门感知 auto + 面板开关） | 📋 排队（票已开） |
| VSC-2F | 审批双端弹窗 + 联通开关 syncWithDesktop | 📋 排队（**语义待 owner 确认**：isolated 下桌面端不在线则 120s 超时） |
| VSC-2G | diff 删除栏不显示 | 📋 排队（**需 owner 提供修改场景实弹证据**：新建 vs 修改、是否折叠、路径含空格？） |
| COST-4 | 结果标记/load_result 循环 + 压缩频率治理 | 📋 排队（票已开，第二梯队） |
| cost1b 热修 | main 上 test_ticket_cost1b 分支名环境失败 | 📋 待开（BOBO_TICKET 兜底） |
| GUI-F16 | 桌面端 markdown 数学公式渲染（KaTeX） | ✅ 已合并推送（b5f37354，回滚标签在远端）；数学端到端 6/6 验证过 |

## 三、未解决问题清单（owner 实弹反馈，等待处理/证据）

1. **VSC-2D 实弹验收**：裸 HTML 代码片段是否文本可见（需 deploy 后测）
2. **VSC-2G diff 删除栏不显示**：等 owner 提供"修改已有文件"场景证据（C1 新建
   无旧内容 / C3 diff 折叠 / C4 uri 编码，先复现再修，L14）
3. **VSC-2F 联通开关语义**：等 owner 点头（isolated 下审批 120s 超时取舍）
4. **桌面端 markdown 数学**：缺 KaTeX，公式显示为 LaTeX 源码（GUI-F16 待开）
5. **VSC-2C/2D 收编**：两票分别 merge main + push（文件零重叠，先 2C 后 2D）
6. **工作区误建文件**：example1/2/3.py（owner 实弹问题 1 时 bobo 误建到仓库根，
   待删除）

## 四、后端/桌面端已知事实（排查参考）

- 共享后端：GW-SOCK（socket 常驻）+ GW-MULTI（多客户端并发，事件全广播 +
  客户端按 sid 过滤）
- 写审批闸门：engine_adapter.py `_guarded_execute`（VSC-2B）——**不感知 AUTO**
  （VSC-2E 修）
- AUTO 决策树：engine.py `_confirm`（:204-206）AUTO 开走 `_auto_decide` 绕过
  confirm_callback
- 桌面端渲染：mdReply（marked+DOMPurify+hljs，V2C12）+ md()（自研回退）；
  **无 KaTeX**（GUI-F16 修）
- VS Code 渲染：md-render.js（marked v12 + DOMPurify + hljs）；VSC-2D 已修
  裸 HTML；同样无 KaTeX（对齐时机另议）

## 五、纪律提醒（教训册新条目）

- **write_obsidian 写错路径（第 4/5 次，2026-08-19 教训）**：bobo 收工报告
  TICKET-P0-1完成报告.md 又用 write_obsidian 写进 Obsidian vault
  （~/Desktop/Obsidian note/agent开发/）而非项目 library/agent开发/（VSC-2B、
  GUI-F23、GUI-F24、GUI-F25 同款，本次第 5 次）。已手动拷贝+删除修正。
  **待治本**：bobo 收工汇报工具链强制检查"完成报告固定落 library/agent开发/"
  （或 write_obsidian 增加 project-root 校验）。待开票或纪律注入。
- **DeepSeek thinking 模式 400：reasoning_content 必须回传（2026-08-19 排查）**：
  引擎收集 reasoning 存 `msg["thinking"]`（GUI-F8 用），发送侧从不回传
  `reasoning_content`。触发规则：**两个 user 消息之间**若有工具调用轮，
  assistant 必须带 reasoning_content 回传，否则 400（间歇性：平时单 user 结构
  不触发）。排查链路见 TICKET-P0-1.md 施工阻塞记录。修复方向：发送副本
  thinking→reasoning_content 转换（方案 B）。待开修复票。

- **deploy 是实弹前置**：VSC 票改 media/ 或 src/ 后，实弹前必须
  `scripts/deploy.sh` + Reload Window，且终审应验证扩展目录版本特征
  （2026-08-17 教训：VSC-2B/2C 从未 deploy，owner 实弹一直跑 VSC-2 旧版）
- **ROADMAP 登记防覆盖**：开票时登记的 ROADMAP 行曾被施工分支文件操作覆盖丢失，
  已重登记（2026-08-18）；后续开票登记与施工并行时注意
- **任何改动必须立即 commit + push（owner 铁律，2026-08-18 教训）**：
  GUI-F22（侧栏折叠按钮置顶）首次改了工作区**未 commit**，被 F23 施工覆盖丢失，
  已重建提交（aee40d6f）。规则：不管改动多小（移动一个按钮、改一行 CSS），
  完成即 commit（含标记）+ push 远端，保证可回溯；切分支前先 stash/commit
  当前工作区，禁止未提交改动跨分支流动。
- **收编必须全量 pytest（2026-08-18 教训）**：GUI-F22 收编只跑了桌面端套件
  （21/21）未跑 pytest 全量 → TestSidebarFold 3 失败（F22 结构变更未同步断言）
  漏进 main，F24 终审时才暴露。规则：**每票收编 merge 后必须全量
  `.venv/bin/python -m pytest tests/ -q -p no:cacheprovider`，main 全绿才 push**
  （L13 纪律在收编环节同样适用）。
- **write_obsidian 写错路径（第 3 次，2026-08-18 教训）**：bobo 收工报告用
  write_obsidian 写到了 Obsidian vault（~/Desktop/Obsidian note/agent开发/）而非
  项目 library/agent开发/——VSC-2B、GUI-F23、GUI-F24 三次同款。已每次手动修正；
  **需治本**：bobo 的 note-taking/收工流程强化"完成报告固定落 library/agent开发/"
  （或收工汇报工具链检查路径）。待开票或纪律注入。

## 六、自进化系统施工前全量备份（2026-08-19）

- **git 快照标签**：`snapshot/pre-self-evolving-20260818`（指向 main 45c3bc85，annotated，
  已推远端）——覆盖 TUI/桌面端/后端全部代码（单仓库），随时可 checkout 回溯；
- **tar 物理备份**：`/Users/niuqingwei/Desktop/boboagent_pre-self-evolving_20260818.tar.gz`
  （257MB，40116 文件，排除 node_modules/.venv/.git/data 大件）——物理保险；
- 用途：自净化系统是大型系统性变动（P0 记忆重构起），一旦走错，回到此基线；
- 施工开始后每完成一个阶段（P0 完成/P1 完成）建议再打一个阶段快照。
