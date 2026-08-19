# 票 P0-3：缓存实测——尾部动态块变化对 DeepSeek 前缀缓存的影响（P2 经济模型开门闸）

分支 `feat/ticket-p0-3-cache-probe`，自最新 main（`f5044977`）切出。
回滚标签 `rollback/pre-p0-3` 先打再动工。
六步工作流 + GUI-LESSONS 全程，未 commit/merge/push，收工等终审。

---

## 背景（SELF-EVOLVING-PLAN.md P0-3；DISCUSSION 22/40/72/188-189 节）

自进化系统 P0 系列第三票。**P0-3 = 缓存实测**：量化"**尾部动态块内容变化**
对 DeepSeek 前缀缓存命中率的影响。**本票不改任何功能，只做测量实验 + 结论**，
产出物是测量报告，决定 P2 经济模型可行性。

**为什么是 P2 开门闸**（DISCUSSION 未闭合项 #1 缓存红线）：
- P2-1 evolved 投影层要把"用户模型片段"（≤800 tokens）**实时注入**上下文尾部；
- 若尾部一变化 → 前缀缓存命中率塌（如从 90%+ 掉到个位数）→ 每次注入都要
  全量重算 → token 成本爆炸 → P2 经济上不可行，**设计必须改**（注入频率/
  位置/分层）；
- 反之若命中率保持 → P2 实时注入方案可行。
- **这是纯实验，不改代码**——"prompt 演化毁缓存"（DISCUSSION 15 批判点）的
  量化证据。

**已有相关取证（区分边界，施工不必重复但可引用）**：
- COST-2/3 探针（scripts/e2e_cost2_probe.py / e2e_cost3_probe.py）测的是
  **稳定前缀**相邻轮命中率（R2→R3，实测 99.8% / 长会话 ≥85%）；
- REASONING-ECHO 报告补字段缓存取证（两连发 92%）；
- **P0-3 与它们不同**：显式**改变尾部动态块内容**（模拟 P2 注入），观察
  命中率如何变化——这是现有探针没覆盖的维度。

## 施工项

### 1. 测量方法（实验设计，核心交付）

构造对照实验，量化"尾部动态块变化"的影响：

- **基线组**：稳定前缀（不改变量）连发 N 轮，记录每轮
  `prompt_cache_hit_tokens / prompt_tokens`（llm.usage 事件，落盘
  data/metrics/rounds.jsonl 或直接读 llm.usage 事件）；
- **实验组**：同样的前缀，但每轮在**尾部动态块位置**注入不同内容
  （模拟 P2 evolved 片段变化：同主题微调 / 完全不同主题 / 长度 ±），
  记录命中率；
- **变量拆解**（回答"变化到什么程度会塌"）：
  - 尾部块内容**改几个字**（同主题微调）→ 命中率？
  - 尾部块内容**完全替换**（不同主题）→ 命中率？
  - 尾部块**长度变化**（增删 tokens）→ 命中率？
  - 对照：头部/中段插入同等变化 → 命中率（验证"尾部是否在前缀外"假设）；
- 每场景 ≥3 次取样取中位数（DeepSeek 自动缓存有随机性，cost3 实测 R3
  波动 57-90% 佐证）。

### 2. 测量脚本

新增 `scripts/probe_p0_3_cache.py`（或复用/扩展既有 e2e_cost3_probe.py 骨架）：
- 直连 DeepSeek API（真 key，复用 probe_reasoning_echo.py 的连接模式）；
- 可注入 messages 结构（system + 历史 + 尾部动态块）；
- 逐轮输出：prompt_tokens / cache_hit_tokens / cache_miss_tokens / 命中率；
- 落盘 `data/logs/cache_probe_p03.json`（原始数据）+ 终端表格摘要。

### 3. 结论报告（最终交付物）

`library/agent开发/TICKET-P0-3缓存实测报告.md`：
- 四场景命中率数据表（原始 + 中位数）；
- **结论**：尾部动态块变化是否破坏前缀缓存？破坏阈值在哪？
  （如"同主题微调保持 ≥80%，完全替换塌到 <30%"之类具体数字）；
- **对 P2 的建议**：evolved 注入频率/位置/分层的可行区间
  （如"每次注入须在尾部且同主题微调可接受；完全替换须低频"等）。

## 验收标准（终审逐条复跑）

1. 测量脚本可复跑：`python scripts/probe_p0_3_cache.py` 输出四场景命中率；
2. 数据落盘 data/logs/cache_probe_p03.json（原始值，非只摘要）；
3. 每场景 ≥3 次取样（中位数报告，注明原始值波动）；
4. 报告含：四场景数据表 + 明确结论（破坏/不破坏 + 阈值）+ P2 建议；
5. 全量 pytest 零失败（基线 2781 passed / 2 skipped / 1 xpassed；本票若
   加测试则 +N，不加不强求——核心交付是实验不是代码）；
6. 收工汇报落 `library/agent开发/TICKET-P0-3缓存实测报告.md`。

## 风险自查点

- **不改功能**：本票零引擎改动（除非测量需要最小 hook，需 TEL-8 特批登记）；
- **API 成本**：每次实验调用真实 DeepSeek API 有 token 成本——脚本设计
  复用前缀（每场景 base 前缀只发一次，只变尾部），控制总调用量；
- **缓存随机性**：DeepSeek 自动缓存对新增段有随机（cost3 实证）——取样
  ≥3 次取中位数，报告注明原始波动；
- **区分"前缀内/外"**：结论必须说清尾部块在前缀内还是外（决定 P2 注入
  位置假设是否成立）——这是 P2-1 的关键输入；
- **别踩 COST-2 战果**：探针只读不改引擎，不破坏现有前缀稳定机制。

## 已完成取证（Kimi 开票前核实，施工不必重复）

- 既有探针：scripts/e2e_cost2_probe.py（稳定前缀 99.8%）、
  scripts/e2e_cost3_probe.py（长会话 ≥85%，短会话 R3 波动 57-90% 随机性
  实证）、scripts/probe_reasoning_echo.py（直连 API 模式参考）；
- 数据来源：llm.usage 事件 prompt_cache_hit_tokens / prompt_tokens（落盘
  data/metrics/rounds.jsonl）；
- 引擎无 cache_control 控制权（cost3 报告：全库 0 匹配）——只能靠
  前缀稳定性，P0-3 结论直接决定 P2 注入策略；
- 基线 pytest：2781 passed / 2 skipped / 1 xpassed。
