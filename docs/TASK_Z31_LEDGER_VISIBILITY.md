# 票 Z3.1：task_ledger 可见性双保险

> 状态：待开工
> 来源：票 Z v3 撞闸演习复盘（2026-07-29 22:21 会话 20260729_112249）
> 分支：`feat/ledger-visibility`（从最新 main 新建）

## 病灶（演习暴露的两个真实问题）

1. **潜伏 bug**：`core/context.py` 的 `TOOL_CATEGORIES` 八个分类里都没有
   `task_ledger`。查询一旦被 `_classify_query` 归类（如含"文件"→file、
   含"代码"→code），`_get_filtered_tools` 只放行该分类 + general 兜底，
   `task_ledger` 直接对模型隐形——此时票 Z v3 无账硬闸回注"请用
   task_ledger 建账"，等于命令模型调用一个它看不见的工具。
2. **行为问题**：演习中模型明明看得见 task_ledger（未触发分类，79 工具全量
   下发），仍声称"项目中不存在该工具"，转而用 file_operation 写 md 交差。
   说明回注文案的权威度不够，模型会怀疑指令而非自己的工具清单。

## 处方（两处小改，禁止扩 scope）

### 1. core/context.py — general 分类补登记

`TOOL_CATEGORIES["general"]` 列表追加 `"task_ledger"`。
理由：general 是 `_FALLBACK_CATEGORIES` 唯一成员，登记后任何分类过滤
路径下 task_ledger 恒可见；未触发分类时本来就是全量下发，无影响。

### 2. core/engine.py — 回注文案加"工具在册"声明

票 Z v3 无账硬闸的回注消息（约 1137 行）改为：

```
本回合调用了工具但没有建立任务台账。task_ledger 就在你的可用工具列表中，请直接调用它建账（已完成的列 done，未完成的列 pending），然后继续。不要说明、不要道歉，直接做。
```

缝1 提醒（约 1017 行）的 system 消息同样补"task_ledger 在你的可用工具列表中"。

## 验收金标准（tests/ 追加）

1. 对 `_CLASSIFY_RULES` 每个分类的代表性输入（如"读文件"/"写代码"/"搜索"），
   `_get_filtered_tools` 结果都包含 `task_ledger`。
2. 无分类输入时 `_get_filtered_tools` 返回 None（全量），行为不变。
3. 票 Z v3 的 TestNoLedgerHardGate 5 条 + 票 Z v2 全部测试不动、全绿。
4. 全量 pytest 通过。

## 纪律

- 只动 `core/context.py` 一处列表、`core/engine.py` 两处文案、测试文件。
- 开工前 `git branch --show-current` 确认在 feat 分支。
- 完成后五查汇报（含 git status 原文 + git branch --show-current 原文），
  ⛔️ 禁止 merge、禁止 push，等 Kimi 终审。
- 改了 core/ → 五查第 6 项填"是，需重启生效"。
