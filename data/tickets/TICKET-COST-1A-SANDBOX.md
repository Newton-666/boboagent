# TICKET-COST-1A-SANDBOX —— 工具配置效率实验沙盒（外置，核心引擎零改动）

> 施工前必读 docs/GUI-LESSONS.md。分支 feat/ticket-cost-1a-sandbox。未终审不 commit。
> 前置数据：reports/tool_profile_report.md（画像：82 工具/64% 税白交/重复 4.4%/平均 50,752 tokens 每轮）。
> owner 铁律：**核心引擎一行不动**，实验全在外置沙盒；难点不是证明"少=快"，是证明砍/并哪些不掉能力。

## 沙盒结构（全部新文件，不动 core/）

`experiments/cost1a/` 下新建：
- `runner.py`：最小 agent loop（直接打真实 API，读 data/.env 的 key，只读不外传），支持流式、记录每轮 usage
- `tools_impl.py`：8 个核心工具的本地最小实现（read_local_file/edit_file/execute_terminal(限 sandbox 子进程白名单)/grep_code/list_directory/load_result/save_memory/web_search）——合并配置里亲缘工具用 `action` 参数分发到这 8 个实现
- `configs.py`：四档工具配置（见下）
- `tasks.py`：5 道固定任务（见下），每题带确定性判分（文件内容断言/命令输出断言，不看模型自评）
- `report.py`：跑完出 reports/cost1a_sandbox_report.md

## 四档配置（schema 全部从我们 tools/TOOLS_SCHEMA 原样取，合并档改写 name/action）

- **A 现状档**：PARK-1 后 31 个在线工具（对照组）
- **B 合并档**：31 → 14：obsidian 13→1、notion 6→1、github 6→1、web 5→1、email 4→1、日历提醒 4→1、剪贴板 2→1（各并为一个工具+action 枚举参数，描述合并原文）
- **C 极简档**：8 个核心工具（Pi 风格毛坯房）
- **D 全量档**：82 个（外挂仓全放出，历史对照）

## 五道固定任务（覆盖真实使用 TOP 场景）

1. 读文件改 bug 跑测试（read+edit+terminal，画像 TOP3 场景）
2. 代码库搜索定位（grep+read）
3. 多文件重构小改（read×N+edit×2+run_tests）
4. 记忆存取（save_memory+search）
5. 笔记写入（obsidian 系——**专门测合并档 action 分发准确率**：B 档用合并工具，A/D 档用原始工具）

## 测量指标（每档 × 每题 × 5 次，取中位数）

- prompt_tokens 总量 + **prompt_cache_hit_tokens**（DeepSeek usage 原生返回缓存命中，算命中率）
- 首 token 延迟 / 总耗时
- 工具调用次数 + 重复调用率
- 任务成功率（确定性判分）
- B 档专项：action 参数选错率（合并代价的量化）

## 验收

- 报告含四档对比表 + 效率×能力散点（成功率 vs 总 tokens）+ 明确结论：哪个配置是平衡点
- 全程不改 core/ 任何文件（git diff core/ 必须为空）
- API key 只从 data/.env 读，不落盘不进 git（.gitignore 检查 experiments/cost1a/results/）
- 专项测试：判分器自身测试 + 合并 schema 合法性断言；全量零回归；md5 闸门
- 收工汇报按 L12
