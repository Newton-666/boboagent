# 票 TICKET-E2b：describe_tool 取件通道（Harness 重构 · 唯一新基建）

## 背景（宪法与图纸）

熵减计划第二阶段 Harness 重构（纲领：Obsidian《BOBO Entropy Reduction Plan》）。
GUIDANCE.md v1.0 已定稿（docs/GUIDANCE-draft.md），其中向模型承诺了一条
取件路径："Need a tool that is not mounted: describe_tool(\"<tool-name>\")"。
本票兑现这个承诺。它是 L2 按需化（E2-③）的前置：没有取件通道，
工具 schema 就无法从"全量预付"改为"点名补挂"。

现状：79 个工具 ≈31.5K 字符，未命中分类时全量挂载（闲聊也背）。
已有零件：context.py `_get_filtered_tools(extra_categories)` 支持类别扩张，
`_used_categories` 集合已存在。本票在其上加"按名单点扩张"。

## 目标

### A. 新工具 describe_tool

```
describe_tool(tool_name: str) -> str
```

- 从 TOOLS_SCHEMA 按名查找，返回该工具的 description + parameters 摘要
  （截断 ~800 字符，防单个 schema 爆上下文）
- 找到 → 把该工具名注册进 `engine._extra_tools: set[str]`（会话级，只增不删）
- 未找到 → 返回错误 + difflib 模糊匹配的最接近 3 个工具名（"你是不是想要…"）
- 发射事件 `tool.describe`（session_id, tool_name, found）——监控取件行为
- **必须永远在基础挂载集里**：无论分类过滤如何裁剪，
  describe_tool / load_result / read_local_file 等"元工具"不可被裁掉

### B. 补挂逻辑

`_get_filtered_tools` 返回前：`_extra_tools` 里的名字 union 进允许集。
返回 None（全量）时无需处理。压缩/塌缩不影响 `_extra_tools`
（与 _session_written_files 同纪律：__init__ 初始化，终身只增）。

## 边界（不碰）

- 不改现有分类过滤规则、不改默认全量挂载行为（按需化是 E2-③ 的事）
- 不动 identity prompt、不动 GUIDANCE（v1.0 已定稿，注入在 E2-③）

## 验收

1. describe_tool("grep_code") 返回其 schema 摘要，且下一轮 LLM 请求
   的工具列表含 grep_code（即使在分类裁剪场景下）
2. describe_tool("grep_cd") → 错误 + 建议含 grep_code
3. 分类裁剪场景（如命中 code 类）下 describe_tool 本身始终可用
4. 压缩发生后 _extra_tools 不清空
5. 事件 tool.describe 写入 events.jsonl
6. 全量 pytest 零回归（基线 1474 passed / 2 skipped）
7. 改 core/ → 五查第 6 项填"是，需重启"

## 纪律

- 从最新 main 切 `feat/ticket-e2b-describe-tool`，开工先 `git branch --show-current`
- ⛔ 禁止 merge、禁止 push 到 main，完成后停手等 Kimi 终审
- 五查汇报含 git status 原文 + git branch --show-current 原文
