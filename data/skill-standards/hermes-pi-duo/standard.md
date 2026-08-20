# Hermes-PI Duo Standard v1

> keywords: hermes 讨论, hermes 审查, 让 hermes 看, hermes 挑刺, hermes pi 讨论, 让 hermes 和 pi 商讨, 双 agent 讨论, @hermes @pi, 调用 hermes 和 pi, hermes+pi
> 价值: 用户要 hermes/pi 参与讨论审查时命中 → 约束多 agent 协作与审查流程（平时不注入）
> status: draft
> **注意：/hermes-pi-duo 让 Bobo 与本地 Hermes agent 进行双角色审查讨论。PI 为预留扩展位，当前版本暂不自动调用。**

## 目标场景

用户希望 Bobo 担任**方案提出者 + 最终执行者**，本地 **Hermes agent** 担任**独立审查者**，围绕一个任务进行多轮讨论、交叉验证，输出更优结论。

本 skill 当前阶段只实现 Bobo ↔ Hermes 的自动双人讨论。PI（https://pi.dev/）保留为第二审查者，待确认可调用方式后升级到 v2。

## 角色分工

| 角色 | 职责 | 当前实现 |
|------|------|----------|
| **Bobo（用户）** | 提出初始方案/问题，接收 Hermes 审查反馈，修正方案，最终执行 | Bobo 自己 |
| **Hermes** | 对 Bobo 的方案进行独立审查、挑刺、提出风险与改进建议 | 本地 `hermes-agent-main` 自动调用 |
| **PI** | 第二独立审查者（预留） | 当前不自动调用，v2 接入 |

## 触发词

任意包含以下意图的指令：

- `hermes 讨论`
- `hermes 审查`
- `让 hermes 看`
- `hermes 挑刺`
- `hermes pi 讨论`
- `让 hermes 和 pi 商讨`
- `双 agent 讨论`
- `@hermes @pi`
- `调用 hermes 和 pi`
- `hermes+pi`

## 执行流程

### Step 1: 提取任务

从用户输入中提取：
- `USER_QUERY`：原始问题/任务
- `USER_PLAN`（可选）：用户已有的方案或思路

如果用户只给问题没给方案，Bobo 先自己给出一个初步方案，再进入审查。

### Step 2: Bobo 提出初始方案

Bobo 基于 `USER_QUERY` 给出初始方案 `PLAN_0`，要求：
- 结构清晰
- 包含关键决策点和假设
- 明确范围边界

### Step 3: 调用 Hermes 审查

在本地 Hermes 目录下执行：

```bash
cd ~/Desktop/hermes-agent-main
python3 run_agent.py \
  -q "You are an independent reviewer. Review the following plan and identify: risks, missing considerations, incorrect assumptions, and concrete improvements. Be critical but constructive.\n\nPlan to review:\n${PLAN_N}" \
  --model deepseek-v4-pro \
  --max_turns 1
```

捕获输出，称为 `HERMES_REVIEW_N`。

### Step 4: Bobo 吸收反馈并修正方案

Bobo 阅读 `HERMES_REVIEW_N`，更新方案为 `PLAN_N+1`，并明确说明：
- 接受了哪些建议
- 拒绝了哪些建议及原因
- 新增的风险控制

### Step 5: 循环审查

重复 Step 3 → Step 4，最多 4 轮，或直到用户喊停。

每轮开始前询问用户："是否继续第 N 轮 Hermes 审查？"如果用户不指定，默认执行最多 4 轮。

### Step 6: 最终执行

讨论结束后，Bobo 输出：
1. **最终方案**（吸收所有审查意见后的版本）
2. **审查摘要**（Hermes 的主要贡献）
3. **下一步行动**（Bobo 将直接执行的具体动作，需用户确认后再执行）

## 参数与默认值

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `model` | Hermes 使用的模型 | `deepseek-v4-pro` |
| `max_turns` | Hermes 单次调用最大轮次 | `1` |
| `max_review_rounds` | Bobo-Hermes 讨论总轮次 | `4` |
| `hermes_path` | Hermes 安装目录 | `~/Desktop/hermes-agent-main` |

## 失败处理

- **Hermes 命令执行失败**：
  - 立即向用户报告："Hermes 当前不可用，原因：{具体错误}。"
  - 不模拟 Hermes 输出。
  - 不继续假装执行讨论。
  - 提供可选的下一步：检查 Hermes 配置、换用 Bobo 内部分析、稍后重试。

- **API 返回错误（如 400/401/429/500）**：
  - 直接展示 API 错误信息。
  - 如果是模型名问题，提示当前使用 `deepseek-v4-pro`。
  - 如果是余额/API key 问题，提示用户检查 DeepSeek 控制台。

- **Hermes 输出为空或超时**：
  - 视为失败，向用户说明。
  - 询问是否重试或中止。

## PI 扩展说明（v2）

当前版本不自动调用 PI。当用户提到 PI 时，Bobo 应说明：

> "PI 已预留为第二审查者，但我当前无法直接调用它（pi.dev 没有公开 API/CLI）。你可以手动把 Hermes 的审查结果复制到 PI，然后把 PI 的反馈贴给我，我会继续下一轮。"

若未来 PI 提供可调用接口，本标准将升级为 v2：
- Step 3 同时调用 Hermes + PI
- Step 4 让 Bobo 吸收两套反馈
- Step 5 支持三方交叉讨论

## 输出格式

### 每轮输出

```markdown
## 第 N 轮讨论

### Bobo 的方案
[PLAN_N]

### Hermes 的审查
[HERMES_REVIEW_N]

### Bobo 的回应
- 接受：...
- 拒绝：...
- 更新后的方案要点：...
```

### 最终输出

```markdown
## 最终结论

### 最终方案
[PLAN_FINAL]

### Hermes 审查贡献
- 风险 1
- 改进 1
...

### 下一步行动（待你确认）
1. ...
2. ...
```

## 示例对话

**用户**：让 hermes 审查一下我想用 Python CLI + SQLite 做任务管理器的方案。

**Bobo**：
> 我先给出我的初步方案，然后调用 Hermes 进行独立审查。
>
> ## 初步方案
> ...
>
> 现在调用 Hermes...
>
> ## 第 1 轮讨论
> ### Bobo 的方案
> ...
> ### Hermes 的审查
> ...
> ### Bobo 的回应
> ...
>
> 是否继续第 2 轮审查？

## 关联标准

- 继承 [Duo Standard v1](../duo/standard.md) 的"双员商讨"思想。
- 区别于 Duo：Duo 是 Bobo 内部模拟两个角色；本标准调用真实的外部 Hermes agent。
