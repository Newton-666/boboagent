# 模型与 Provider 切换指南

> 适用范围：boboagent 全部（gateway / TUI / 工具链）
> 适配层：TICKET-PROVIDER-ADAPTER（注册式——provider 自描述协议差异，
> 代码只读声明，新 provider 纯注册零改代码）

---

## 一、快速切换（日常操作）

所有切换都发生在 `data/.env`，**改完重启后端生效**。

### 切到 LM Studio（本地模型）

```bash
# data/.env
BOBO_PROVIDER=lmstudio
API_MODEL_NAME=qwen/qwen3.6-35b-a3b     # 换成你要的模型名
API_BASE_URL=http://localhost:1234/v1/chat/completions
```

- LM Studio 模型名格式：`厂商/模型`（如 `qwen/qwen3.6-35b-a3b`、`google/gemma-4-31b`）
- 模型未加载时 LM Studio 会自动加载（等待几秒~几十秒）
- 已加载模型可通过 LM Studio 界面或 `/v1/models` 查看

### 切到 Kimi（Moonshot）

```bash
BOBO_PROVIDER=moonshot
MOONSHOT_API_KEY=sk-***                  # 填入你的 key
# API_MODEL_NAME 可留空 → 用默认 kimi-k3；或指定 kimi-k2.6 等
```

### 切到 OpenAI / 其他

```bash
BOBO_PROVIDER=openai
OPENAI_API_KEY=sk-***
# 或 anthropic / google / openrouter / ollama / custom
```

### 通用规则

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `BOBO_PROVIDER` | 选 provider | `deepseek` |
| `API_MODEL_NAME` | 指定模型（留空用 provider 默认第一个） | 各 provider 默认 |
| `API_BASE_URL` | 覆盖端点（一般不用，provider 已配） | 各 provider 内置 |
| `BOBO_TEMPERATURE` | 覆盖 temperature（显式设置时优先于声明） | 声明值或 0.3 |
| `BOBO_MAX_TOKENS` | 覆盖 max_tokens | 8192 |
| `BOBO_CONTEXT_LENGTH` | 覆盖上下文窗口 | 声明值或 128k |

---

## 二、已注册 Provider（9 个）

| provider | 说明 | protocol | reasoning 字段 | echo_required | 实弹验证 |
|---|---|---|---|---|---|
| `deepseek` | 主力 | `openai_chat` | `reasoning_content` | ✅ | ✅ |
| `moonshot` | Kimi（OpenAI 兼容） | `openai_chat` | `reasoning_content` | ✅ | ✅ |
| `lmstudio` | 本地（无 key） | `openai_chat` | `reasoning_content` | ❌ | ✅ |
| `openai` | GPT 系 | `openai_chat` | `reasoning_content` | ❌ | 未实弹 |
| `anthropic` | Claude 直连 | **`anthropic_messages`** | `thinking` | ❌ | 适配器单测（#9） |
| `google` | Gemini | `openai_chat` | `reasoning_content` | ❌ | 未实弹 |
| `openrouter` | 聚合（含 Claude） | `openai_chat` | `reasoning_content` | ❌ | 未实弹 |
| `ollama` | 本地（无 key） | `openai_chat` | `reasoning_content` | ❌ | 未实弹 |
| `glm` | 智谱（OpenAI 兼容，动态拉模型） | `openai_chat` | `reasoning_content` | ❌ | ✅ 实弹 2026-08-21 |
| `custom` | 自定义端点 | `openai_chat` | `reasoning_content` | ❌ | 未实弹 |

> echo_required = 工具轮后必须回传 thinking 内容（DeepSeek/Kimi 要求，否则 400）。

---

## 三、添加新 Provider（注册式，零改代码）

在 `core/provider.py` 的 `PROVIDERS` 加一个条目：

```python
"glm": {
    "name": "GLM",
    "env_key": "GLM_API_KEY",            # API key 环境变量名（本地可 ""）
    "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "models": ["glm-4-plus"],            # 第一个是默认
    "context_length": 128000,
    "protocol": "openai_chat",            # 缺省 = openai_chat；直连 Claude 用 anthropic_messages
    "temperature": 1.0,                  # 可选：模型 temperature 约束（如 kimi 只允许 1.0）
    "reasoning": {                        # 思考协议声明（缺省 = 保守无 thinking）
        "field": "reasoning_content",    # 思考字段名（DeepSeek/Kimi/Qwen3 = reasoning_content）
        "echo_required": False,          # 工具轮后是否必须回传
        "thinking_mode": False,          # 默认是否开 thinking
        "stream_reasoning": False,       # 流式是否单独发 reasoning 块
        "disable_supported": False,      # 是否支持显式关 thinking
    },
    "tools": {                            # 工具协议声明（缺省 = 保守）
        "native": True,                  # 原生工具调用
        "parallel": False,               # 并行工具调用
        "json_mode": False,              # 原生 JSON 模式
    },
},
```

### 保守默认（声明缺省时）

```
reasoning 缺省 → 按无 thinking 处理（不设字段、不回传）——保证能跑但不用错协议
tools 缺省     → native=False, parallel=False, json_mode=False
temperature 缺省 → 0.3（环境变量 BOBO_TEMPERATURE 可覆盖）
```

### 添加后建议做一次冒烟实弹

```bash
# 临时切过去测试（不动 .env）
BOBO_PROVIDER=glm API_MODEL_NAME=glm-4-plus \
  PYTHONPATH=. .venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv('data/.env')
from core.provider import get_provider, resolve_provider
from core.llm_caller import create_llm_caller
cfg = resolve_provider(); proto = get_provider(cfg['name']) or {}
caller = create_llm_caller(cfg['api_key'], cfg['base_url'], cfg['model'], provider_proto=proto)
r = caller([{'role':'user','content':'你好'}], use_tools=False, max_tokens=200)
print('OK' if not r.get('error') else r['error'][:200])
"
```

- 200 → 声明正确，可靠可用
- 400/502 → 改声明的值（字段名 / temperature / 代理），不用改代码

---

## 四、已知协议差异（实测记录）

| 差异 | DeepSeek | Kimi | LM Studio(Qwen3) | 说明 |
|---|---|---|---|---|
| thinking 字段名 | `reasoning_content` | `reasoning_content` | `reasoning_content` | 三家 OpenAI 兼容都是这个名字（曾误判 kimi 为 thinking，实弹修正） |
| echo_required | ✅ | ✅ | ❌ | DeepSeek/Kimi 工具轮后必须回传 thinking，否则 400 |
| temperature | 0.3 自由 | **只能 1.0**（否则 400） | 自由 | kimi 的约束在 provider 声明 `temperature: 1.0` |
| 关 thinking | `{"thinking":{"type":"disabled"}}` | 同左 | 不支持 | 信号精判/冷调用用（P5-400 教训） |
| 本地代理 | — | — | **requests 走系统代理会 502** | 已修：本地端点自动禁代理 |

---

## 四.b、直连 Anthropic（GitHub #9）

引擎与 `llm_caller` 内部始终是 OpenAI `chat/completions` + `tool_calls` 形状。
`BOBO_PROVIDER=anthropic` 登记的端点是官方 `/v1/messages`，**不是** OpenAI 兼容面。

适配层 `core/anthropic_adapter.py` 在发送前把请求转成 Messages API，响应/SSE/工具调用再转回 OpenAI 形状，引擎不用改。

| 路径 | 怎么选 | 线上形态 |
|---|---|---|
| 直连 Anthropic | `protocol=anthropic_messages` 且 URL 不含 `/chat/completions` | `x-api-key` + `/v1/messages` + `tool_use`/`tool_result` |
| OpenRouter 上的 Claude | `protocol=openai_chat`（OpenRouter 登记） | Bearer + `/chat/completions` + `tool_calls`（**不进适配器**） |
| 把 Anthropic 的 `API_BASE_URL` 改成 OpenAI 兼容代理 | URL 含 `/chat/completions` 优先 | 走 OpenAI 路径，避免误转换 |

不要把 Anthropic 直连登记改成 `chat/completions` 来"绕过"——那只是掩盖根因。Claude 经 OpenRouter 本来就是兼容路径，保持原样。

---

## 五、注意事项

1. **改 .env 后必须重启后端**（gateway 缓存 provider 配置）
2. **本地模型性能**：35b-a3b 首 token ~5-7s（MoE 激活 3B）；27b 全量更慢；agent 回合（10-30 次调用）会拖到分钟级——断网/隐私场景才推荐
3. **thinking 吃 max_tokens**：Qwen3 思考过程长，小 max_tokens 可能正文为空（PERF-1 会自动重试一次）
4. **换 provider 后建议先聊一句测试**，确认协议匹配再干正事
5. 新增 provider 的字段**以实弹为准**——文档里的声明值是实测校准过的，新加的要实测
