# TICKET-AUTO-B：灰名单风险评估与命令回滚（AUTO MODE 票 B，核心硬票）

> 立案：2026-08-09 · 依据《AUTO MODE 定稿 v0.6》+《v0.6.1 施工前置项》
> 前置：票 A 已合并（68bc330）。分支自最新 main 切出：feat/ticket-auto-b
> 纪律：branch 施工、五查汇报、未终审不 merge 不 push
> 建议施工方式：开 /auto 做本票（票 A 实弹狗食）

---

## 一、施工内容（4 项）

### B-1. 命令副作用三级（按命令族 × 子命令分，v0.6 B④）

新增分级模块（建议 core/command_side_effect.py 或并入 command_safety.py）：

| 级别 | 定义 | auto 下行为 | 例子 |
|---|---|---|---|
| **pure-read** | 纯读，零副作用 | 直接放行（票 A 已覆盖，本票归口复用） | git status/log/diff、ls、cat、pytest |
| **local-reversible** | 改本地状态，可回滚 | 先快照后放行（B-2） | git commit/add、edit_file、mkdir/touch、pip install（记录 before） |
| **external-irreversible** | 改外部/远程状态，不可回滚 | 仍弹窗（auto 唯一合法打断） | git push、npm publish、curl POST/PUT/DELETE、scp、brew upgrade |

判定复用 split_shell_segments 逐段判定（防 `git commit && git push` 整链误放）。任何一段 external-irreversible → 整条转弹窗。

### B-2. 本地可回滚类的快照（phase 1 串行决策时完成，v0.6 B⑤）

- 快照必须在**决策时刻**（_auto_decide 串行路径）完成，**禁止**挪到 phase 2 ThreadPool 并行执行时做（竞态）；
- 文件类：复用现有 checkpoint 机制（file_writer 已有）；
- git 类：执行前记录 `git rev-parse HEAD` + `git status --porcelain` 摘要入审计（轻量，不做真 stash）；
- 包管理类：记录 before 状态（如 `pip list --format=freeze` 相关包行）；
- 快照引用写入审计事件，作为回滚路径字段。

### B-3. 外部不可逆类：弹窗 + 超时默认拒绝（v0.6.1 火 2，安全默认）

- auto 下 external-irreversible 命令转弹窗；
- **无人应答超时必须默认 deny**——先核实既有 120s 超时行为是 deny 还是 allow：
  - 若已是 deny：写测试钉死该行为（防回归），本项即为验证+测试；
  - 若是 allow 或无超时：改为超时 deny；
- 拒绝原因明示："auto 模式：外部不可逆操作超时无人确认，已安全拒绝"。

### B-4. 审计字段扩展

auto.decide 事件增加：`side_effect_level`（三级之一）+ `snapshot_ref`（快照引用/描述）+ `rollback_path`（回滚方式描述）。弹窗转交也留痕（verdict=escalated）。

## 二、验收（终审口径）

1. 三级分类实测：git status → 放行；git commit（feat 分支）→ 快照后放行；git push → 弹窗；
2. 逐段：`git add . && git commit -m x`（local-reversible 链）→ 快照放行；`git commit && git push` → 弹窗；
3. 快照时序：测试断言快照在决策阶段完成（不在执行线程内）；
4. 超时 deny：模拟弹窗无人应答（或直接单测超时路径），断言结果为拒绝且留痕；
5. **auto 关闭时行为零变化**回归断言（强制）；
6. test_mode → auto → _all_confirmed 顺序不被破坏（票 A 测试全过）；
7. 审计事件四新字段齐全；
8. 全量 pytest 零回归（基线 1629 passed / 2 skipped）；真实库 md5 闸门照旧。

## 三、边界（明确不做）

- 不做台账字段（票 C）；
- 不做真·命令回滚执行器（本票只记录快照与回滚路径，自动回滚是以后的事）;
- 不改白名单/黑名单全局名单；
- 不碰票 A 已定的决策树顺序。

## 四、五查汇报要求

照旧：改了什么 / 验收逐条 / 测试输出原文 / commit 与分支 / git status 原文 / 是否需重启。
禁止项：未终审不 merge、不 push、不碰 main。
