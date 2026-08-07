# TICKET-E3b — L2 按需化：GUIDANCE 进预付层 + 段9未命中清单删除 + 段5死代码安葬

- 分支：`fix/ticket-e3b-guidance-prepaid`（从最新 main 切出）
- 类型：熵减计划 E2-③ 第二刀（导航预付 + 内容自取）
- 纪律：禁止 merge、禁止 push、禁止碰 main；完成后五查汇报等 Kimi 终审
- 基线：1490 passed / 2 skipped

## 背景（Kimi 已核实的既定事实）

1. **段 5（AGENTS.md 注入）是死代码**：`OBSIDIAN_VAULT=/Users/niuqingwei/Desktop/Obsidian note` 下不存在 AGENTS.md，`isfile` 每轮失败，从未注入过任何内容。删除 = 行为零变化。
2. **段 9（技能标准）结构**：`skill_loader.load_standards()` 按 keywords 匹配最近 4 条 user 消息，命中 → 全文注入（**保留，这是按需化的正面教材**）；未命中 → injector 追加"## 可用的项目标准（当前未命中，以下仅供参考）"清单（**每轮纯租金，删除**）。
3. **GUIDANCE 定稿**在 `docs/GUIDANCE-draft.md`（英文正文 ~850 字符 + 中文评审 memo）。其中 "describe_tool [mechanism E2-2, to be built]" 已过时——E2b 已建成并合并（工具存在，_META_TOOLS 不可裁剪）。
4. 哲学（owner 定）：预付层只放导航（你有什么/在哪/怎么取/何时取），内容层由模型按需自取。GUIDANCE 是唯一预付的 L2 导航。

## 施工清单

### A. GUIDANCE 转正
1. 从 `docs/GUIDANCE-draft.md` 提取英文正文（去掉头部中文说明与尾部 Review memo），定稿为 `docs/GUIDANCE.md`。
2. 更新过时行：describe_tool 的 "[mechanism E2-2, to be built]" 改为正常描述（该工具已上线）。
3. `docs/GUIDANCE-draft.md` 保留归档不动（历史文件）。

### B. GUIDANCE 进预付层（injector）
4. `core/injector.py`：新增 GUIDANCE 注入段，位置紧跟【上下文自查协议】之后（预付层顶部区域）。从 `docs/GUIDANCE.md` 读取注入。
   - 实现纪律：模块级缓存（mtime 检查或启动时读一次），不许每轮无脑 IO；文件缺失时静默跳过（不炸）。
   - `prompt.budget` 事件的 sections 增加 `guidance` 键统计字符数。
   - 段标题用原文 `[CAPABILITY MAP]` 开头即可，不另加中文包装。

### C. 段 9 未命中清单删除
5. `core/injector.py` 段 9 else 分支（未命中时注入"可用的项目标准"清单）整支删除。命中全文注入逻辑一行不动。
6. 检查 `skill_loader.list_available()` 是否还有其他调用方：有则保留，无则连同方法一起退役（汇报给出 grep 证据）。

### D. 段 5 死代码安葬
7. `core/injector.py` 段 5（AGENTS.md 从 vault 读取注入）整段删除。
8. 全项目 grep `AGENTS.md`，确认无其他引用（有则汇报，不动）。

### E. 测试
9. 更新受牵连测试（段 9 else 分支、段 5 相关断言），逐条说明。
10. 新增验收测试：
    - GUIDANCE 注入：build_messages 产物含 `[CAPABILITY MAP]` 且位于自查协议段之后；文件缺失时不注入也不炸。
    - 段 9：无命中时产物不含"可用的项目标准"；有命中时仍含标准全文（回归）。
    - 段 5：产物不含"项目规则 (AGENTS.md)"。
    - prompt.budget 事件含 guidance 段统计。
11. 全量 pytest 零回归（基线 1490）。

## 边界（不许碰）
- `skill_loader.load_standards()` 的匹配算法本身（keywords/excludes/requires 调优是未来的票）。
- GUIDANCE 英文正文的内容措辞（除 A2 那一行外一个字不许改——owner 已定稿）。
- 记忆段、笔记指针段、自查协议段。

## 五查汇报要求
1. A2 改动行的 before/after。
2. B4 缓存实现方式说明（为什么不会每轮重复 IO）。
3. C6 list_available 调用方 grep 证据。
4. D8 AGENTS.md 全项目引用 grep 证据。
5. 测试删改逐条说明 + 全量输出 + 分支/commit/工作区状态原文 + 是否需重启。
