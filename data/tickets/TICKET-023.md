# 票 TICKET-023：压缩快赢三件套——窗口修正 + 空转防护 + 零摘要兜底

## 背景（pi agent 数据审计 + Kimi 复核实锤）

- `core/provider.py` 两个模型 context_length 写 1,000,000，token 预算算出
  ≈69 万 → token 触发器永久失效，只剩"60 条消息"这个和 token 无关的触发器
- 61 次压缩平均保留率 75%，大量 98~100% 保留的纯空转；根因是 split 对齐
  user 边界后每次只归档 3~5 条，反复触发反复烧一次 LLM 调用（6~40K token/次）
- 18/61 次 summary_length=0：LLM 摘要没产出时原文直接删（只归档 JSONL），
  活上下文零兜底——这是失忆案的主凶
- 受害会话 20260731_225819：317 次调用烧 5,306,553 prompt tokens

## 目标（三件套，全部小改动）

### A. 窗口修正（core/provider.py 或模型配置通道）

- 按当前实际使用的模型填真实 context_length（1M → 128K 或模型文档值；
  不确定的模型一律保守 128K）
- 加一行注释：错误的高估会让 token 预算失效，宁可低估

### B. 空转防护（core/context.py _compress_history 入口）

- 压缩前先算"可归档段 token 占 history 总 token 比例"，< 15% 直接不压
  （记 context.compress_skipped 事件：reason=archivable_too_small, ratio）
- user 边界对齐改为：在可归档 token ≥15% 的候选区间里选最近的 user 边界；
  **向前推进加上限——最多推进到 budget 的 50% 处**（pi 核查补充，
  防止边界对齐把不该压的也压了）
- 现有孤儿 tool_calls 对齐保护逻辑保持不变
- **compress_skipped 分支也重建工作锚点**（pi 核查发现的交互缝隙：
  空转防护上线后压缩次数骤降，若锚点只在压缩时重建，失忆防护反而变弱。
  调 TICKET-020 的 _build_work_anchor + 替换旧锚点即可，不新增逻辑）
- 窗口数值须按当前实际模型文档核实（pi 提醒：1M→128K 是保守安全值，
  但施工时以 API 文档为准并在 commit 里写明依据）

### C. 零摘要本地兜底（_compress_history 的 text_parts 空分支 + LLM 摘要失败分支）

LLM 摘要失败或无文本可摘要时，不再"零摘要直接删"，改生成本地机械摘要：

```
[对话历史摘要 · 本地兜底]
## 用户发言（逐条，截断 200 字）
## 助手结论（最后一条非工具文本，截断 400 字）
## 工具动作（名称 + 结果前 50 字）
```

- 宁可机械，不丢数据；兜底摘要同样进 existing_summaries 保留链
- context.compressed 事件补字段 summary_source: "llm" | "local_fallback"

### D. 估算器补丁（本票只做小修，彻底校准留给 TICKET-024）

- `_estimate_tokens` 注释与实际偏差修正：CJK 按 1.2 字符/token、
  JSON/代码按 3 字符/token、每条消息 +4 token 固定开销

## 边界（不碰）

- 三层分层压缩、摘要合并、压缩沉淀记忆 → TICKET-024
- 60 条消息预算值本票不动（B 项空转防护上线后，触发频率自然下降）
- TICKET-020 工作锚点若已合并，锚点逻辑不动；若未合并，本票基于含 020 的 main

## 验收

1. 窗口修正：token 预算计算用修正后窗口，断言不再出现 >200K 的预算
2. 空转防护：构造"最后一条 user 在末尾 3 条"的 61 条历史 → 不压缩 +
   context.compress_skipped 事件；构造可归档段 30% 的历史 → 正常压缩
3. 零摘要兜底：mock LLM 摘要返回空 → history 出现"本地兜底"摘要且含
   用户发言条目，事件 summary_source=local_fallback
4. 估算器：构造已知字符构成的历史，估算值与公式期望误差 <10%
5. 全量 pytest 零回归（基线以合并时 main 为准）
6. 改 core/ → 五查第 6 项填"是，需重启"

## 纪律

- 从最新 main 切 `fix/ticket-023-compression-quickfix`，开工先 `git branch --show-current`
- ⛔ 禁止 merge、禁止 push 到 main，完成后 `git checkout main` 归位，等 Kimi 终审
- 五查汇报含 git status 原文 + git branch --show-current 原文
