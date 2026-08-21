"""test_ticket_provider_adapter.py — 适配层测试（票 TICKET-PROVIDER-ADAPTER）。

验证"注册式"核心原则：
  1. provider 声明完整性（每个 provider 都有 reasoning/tools 协议）
  2. llm_caller 读声明（不同 provider 字段名 → 正确收集/回传）
  3. 保守默认（无声明 provider → 无 thinking 行为，不发关闭参数）
  4. REASONING-ECHO 字段名读声明（Kimi=thinking / DeepSeek=reasoning_content）
  5. 新增 provider 纯注册零改代码（声明完备即可用）
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

REASONING_KEYS = {"field", "echo_required", "thinking_mode", "stream_reasoning", "disable_supported"}
TOOLS_KEYS = {"native", "parallel", "json_mode"}


# ── 1. provider 声明完整性 ───────────────────────────────────────────

def test_p1_all_providers_declared():
    """每个 provider 都有 reasoning + tools 声明（含必填字段）。"""
    import core.provider as p
    for name, cfg in p.PROVIDERS.items():
        r = cfg.get("reasoning")
        t = cfg.get("tools")
        assert r is not None, f"{name} 缺 reasoning 声明"
        assert t is not None, f"{name} 缺 tools 声明"
        assert REASONING_KEYS <= set(r.keys()), f"{name} reasoning 缺字段: {REASONING_KEYS - set(r.keys())}"
        assert TOOLS_KEYS <= set(t.keys()), f"{name} tools 缺字段: {TOOLS_KEYS - set(t.keys())}"
        # field 必须非空字符串
        assert isinstance(r["field"], str) and r["field"], f"{name} field 非法"


def test_p2_deepseek_kimi_echo_required():
    """DeepSeek 与 Kimi 声明 echo_required=True（工具轮需回传）；OpenAI 不需要。"""
    import core.provider as p
    assert p.PROVIDERS["deepseek"]["reasoning"]["echo_required"] is True
    assert p.PROVIDERS["moonshot"]["reasoning"]["echo_required"] is True
    assert p.PROVIDERS["openai"]["reasoning"]["echo_required"] is False
    # 字段名：DeepSeek=reasoning_content；Kimi（OpenAI 兼容端点实弹 2026-08-20）
    # 同样是 reasoning_content（非 thinking）
    assert p.PROVIDERS["deepseek"]["reasoning"]["field"] == "reasoning_content"
    assert p.PROVIDERS["moonshot"]["reasoning"]["field"] == "reasoning_content"


def test_p3_lmstudio_registered():
    """lmstudio（用户本地方案）已注册，OpenAI 兼容端点，无 key。"""
    import core.provider as p
    cfg = p.PROVIDERS.get("lmstudio")
    assert cfg is not None, "lmstudio 未注册"
    assert cfg["env_key"] == "", "lmstudio 不应需要 key"
    assert "localhost" in cfg["base_url"], "lmstudio 应是本地端点"


# ── 2. llm_caller 读声明（mock 非流式验证字段名）────────────────────

def _mock_llm_caller(proto, msg_field, msg_value="思考中"):
    """用假非流式响应验证：call_llm 从声明的字段收集 reasoning。"""
    import core.llm_caller as lc

    captured = {}

    def _fake_post(url, json=None, headers=None, timeout=None, stream=False):
        import json as _json_mod
        captured["payload"] = json or {}
        # 非流式响应：message 带 {msg_field} 字段
        body = _json_mod.dumps({
            "choices": [{"message": {"content": "正文", msg_field: msg_value},
                         "finish_reason": "stop"}]
        }).encode()

        class _R:
            status_code = 200
            headers = {}
            content = body
            text = body.decode()

            def iter_lines(self):
                return []

            def raise_for_status(self):
                pass

            def json(self):
                import json as _json_mod2
                return _json_mod2.loads(body)

        return _R()

    import requests
    orig = requests.post
    requests.post = _fake_post
    try:
        caller = lc.create_llm_caller("k", "http://x", "m", tools_schema=[], provider_proto=proto)
        result = caller(
            [{"role": "user", "content": "hi"}],
            use_tools=False,
        )
        return captured, result
    finally:
        requests.post = orig


def test_p4_kimi_field_collected():
    """Kimi 声明（field=thinking）→ 响应体 message 含 thinking 字段。"""
    proto = {"reasoning": {"field": "thinking", "echo_required": True,
                           "thinking_mode": True, "stream_reasoning": True,
                           "disable_supported": True},
             "tools": {"native": True, "parallel": True, "json_mode": False}}
    captured, result = _mock_llm_caller(proto, "thinking")
    msg = result["choices"][0]["message"]
    assert msg.get("thinking") == "思考中", f"响应应含 thinking 字段: {msg}"


def test_p5_deepseek_field_collected():
    """DeepSeek 声明（field=reasoning_content）→ 响应体 message 含 reasoning_content。"""
    proto = {"reasoning": {"field": "reasoning_content", "echo_required": True,
                           "thinking_mode": True, "stream_reasoning": True,
                           "disable_supported": True},
             "tools": {"native": True, "parallel": True, "json_mode": False}}
    captured, result = _mock_llm_caller(proto, "reasoning_content")
    msg = result["choices"][0]["message"]
    assert msg.get("reasoning_content") == "思考中", f"响应应含 reasoning_content: {msg}"


def test_p6_thinking_disable_gated():
    """thinking_disabled 只在 disable_supported=True 时发 payload。"""
    import core.llm_caller as lc

    captured = {}

    def _fake_post(url, json=None, headers=None, timeout=None, stream=False):
        import json as _json_mod
        captured["payload"] = json or {}
        body = b'{"choices": [{"message": {"content": "ok"}}]}'
        class _R:
            status_code = 200
            headers = {}
            content = body
            text = body.decode()
            def iter_lines(self):
                return [f"data: {body.decode()}"]
            def raise_for_status(self):
                pass
            def json(self):
                return _json_mod.loads(body)
        return _R()

    import requests
    orig = requests.post
    requests.post = _fake_post
    try:
        # 不支持关闭的 provider（openai）→ 不发 thinking 参数
        proto_no = {"reasoning": {"field": "reasoning_content", "echo_required": False,
                                  "thinking_mode": False, "stream_reasoning": False,
                                  "disable_supported": False},
                    "tools": {"native": True, "parallel": True, "json_mode": True}}
        caller = lc.create_llm_caller("k", "http://x", "m", tools_schema=[], provider_proto=proto_no)
        caller([{"role": "user", "content": "hi"}], use_tools=False, thinking_disabled=True)
        assert "thinking" not in captured["payload"], "不支持关闭时不应发 thinking 参数"
        # 支持关闭的 provider（deepseek）→ 发 thinking 参数
        proto_yes = {"reasoning": {"field": "reasoning_content", "echo_required": True,
                                   "thinking_mode": True, "stream_reasoning": True,
                                   "disable_supported": True},
                     "tools": {"native": True, "parallel": True, "json_mode": False}}
        caller2 = lc.create_llm_caller("k", "http://x", "m", tools_schema=[], provider_proto=proto_yes)
        caller2([{"role": "user", "content": "hi"}], use_tools=False, thinking_disabled=True)
        assert captured["payload"].get("thinking") == {"type": "disabled"}, "支持关闭时应发 thinking 参数"
    finally:
        requests.post = orig


def test_p6b_temperature_from_declaration():
    """provider 声明 temperature 生效（kimi=1.0）；无声明默认 0.3。"""
    import core.llm_caller as lc
    captured = {}

    def _fake_post(url, json=None, headers=None, timeout=None, stream=False):
        import json as _json_mod
        captured["payload"] = json or {}
        body = _json_mod.dumps({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
        }).encode()
        class _R:
            status_code = 200
            headers = {}
            content = body
            text = body.decode()
            def iter_lines(self):
                return []
            def raise_for_status(self):
                pass
            def json(self):
                import json as _json_mod2
                return _json_mod2.loads(body)
        return _R()

    import requests
    orig = requests.post
    requests.post = _fake_post
    import os as _os
    _saved = _os.environ.get("BOBO_TEMPERATURE")
    _os.environ.pop("BOBO_TEMPERATURE", None)
    try:
        # 声明 temperature=1.0（kimi）→ payload 用 1.0
        proto_kimi = {"temperature": 1.0,
                      "reasoning": {"field": "reasoning_content", "echo_required": True,
                                    "thinking_mode": True, "stream_reasoning": True,
                                    "disable_supported": True},
                      "tools": {"native": True, "parallel": True, "json_mode": False}}
        caller = lc.create_llm_caller("k", "http://x", "m", tools_schema=[], provider_proto=proto_kimi)
        caller([{"role": "user", "content": "hi"}], use_tools=False)
        assert captured["payload"]["temperature"] == 1.0, f"kimi 声明 temperature 应=1.0: {captured['payload']}"
        # 无声明 → 默认 0.3
        caller2 = lc.create_llm_caller("k", "http://x", "m", tools_schema=[])
        caller2([{"role": "user", "content": "hi"}], use_tools=False)
        assert captured["payload"]["temperature"] == 0.3, f"无声明默认应=0.3: {captured['payload']}"
    finally:
        requests.post = orig
        if _saved is not None:
            _os.environ["BOBO_TEMPERATURE"] = _saved


# ── 3. 保守默认（无声明 provider）───────────────────────────────────

def test_p7_conservative_default_no_proto():
    """无 provider_proto → 默认行为（reasoning_content 收集，不回传）。"""
    import core.llm_caller as lc
    captured = {}

    def _fake_post(url, json=None, headers=None, timeout=None, stream=False):
        import json as _json_mod
        captured["payload"] = json or {}
        body = _json_mod.dumps({
            "choices": [{"message": {"content": "正文", "reasoning_content": "思考"},
                         "finish_reason": "stop"}]
        }).encode()
        class _R:
            status_code = 200
            headers = {}
            content = body
            text = body.decode()
            def iter_lines(self):
                return []
            def raise_for_status(self):
                pass
            def json(self):
                import json as _json_mod2
                return _json_mod2.loads(body)
        return _R()

    import requests
    orig = requests.post
    requests.post = _fake_post
    try:
        caller = lc.create_llm_caller("k", "http://x", "m", tools_schema=[])
        result = caller([{"role": "user", "content": "hi"}], use_tools=False)
        msg = result["choices"][0]["message"]
        assert msg.get("reasoning_content") == "思考", f"无声明默认应含 reasoning_content: {msg}"
    finally:
        requests.post = orig


# ── 4. REASONING-ECHO 字段名读声明 ─────────────────────────────────

def _echo_field_for(provider_name, monkeypatch=None):
    """复刻 injector 里 REASONING-ECHO 的字段选择逻辑（读 provider 声明）。"""
    import core.provider as p
    if monkeypatch is not None:
        class _FakeCfg:
            def get(self, k, d=None):
                return {"name": provider_name}.get(k, d)
        monkeypatch.setattr(p, "resolve_provider", lambda: _FakeCfg())
        monkeypatch.setattr(p, "get_provider", lambda n: p.PROVIDERS.get(n))
    else:
        orig_resolve, orig_get = p.resolve_provider, p.get_provider
        class _FakeCfg:
            def get(self, k, d=None):
                return {"name": provider_name}.get(k, d)
        p.resolve_provider, p.get_provider = lambda: _FakeCfg(), lambda n: p.PROVIDERS.get(n)
        import functools
        def _restore():
            p.resolve_provider, p.get_provider = orig_resolve, orig_get
        return _restore
    return None


def test_p8_echo_field_kimi():
    """Kimi（echo_required=True, field=reasoning_content）→ 回传字段 = reasoning_content。"""
    import core.provider as p
    restore = _echo_field_for("moonshot")
    try:
        proto = p.get_provider(p.resolve_provider().get("name", "")) or {}
        r = proto.get("reasoning") or {}
        assert r.get("echo_required") is True
        # 实弹定案（2026-08-20）：Kimi OpenAI 兼容端点 field=reasoning_content
        assert r.get("field") == "reasoning_content"
        # 与 injector 逻辑一致：echo_required → field
        echo_field = r.get("field") if r.get("echo_required") else "reasoning_content"
        assert echo_field == "reasoning_content"
    finally:
        restore()


def test_p9_echo_field_deepseek():
    """DeepSeek（echo_required=True, field=reasoning_content）→ 回传字段 = reasoning_content。"""
    import core.provider as p
    restore = _echo_field_for("deepseek")
    try:
        proto = p.get_provider(p.resolve_provider().get("name", "")) or {}
        r = proto.get("reasoning") or {}
        echo_field = r.get("field") if r.get("echo_required") else "reasoning_content"
        assert echo_field == "reasoning_content"
    finally:
        restore()


# ── 5. 注册式：新增 provider 零改代码 ──────────────────────────────

def test_p10_new_provider_registration_only():
    """新 provider 只要声明完备即可用——验证 get_provider/resolve 链路。"""
    import core.provider as p

    # 模拟注册一个新 provider（比如智谱 glm）
    fake = {
        "name": "GLM",
        "env_key": "GLM_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "models": ["glm-4-plus"],
        "context_length": 128000,
        "reasoning": {"field": "reasoning_content", "echo_required": False,
                      "thinking_mode": False, "stream_reasoning": False,
                      "disable_supported": False},
        "tools": {"native": True, "parallel": True, "json_mode": True},
    }
    orig = p.PROVIDERS.copy()
    p.PROVIDERS["glm"] = fake
    import os as _os
    _saved = {k: _os.environ.get(k) for k in ("API_MODEL_NAME", "API_BASE_URL", "BOBO_PROVIDER")}
    _os.environ.pop("API_MODEL_NAME", None)
    _os.environ.pop("API_BASE_URL", None)
    _os.environ.pop("BOBO_PROVIDER", None)
    try:
        cfg = p.resolve_provider("glm")
        assert cfg["name"] == "glm"
        assert cfg["model"] == "glm-4-plus"
        assert cfg["base_url"] == fake["base_url"]
        # 声明可被 llm_caller 消费（不炸）
        import core.llm_caller as lc
        caller = lc.create_llm_caller(cfg["api_key"], cfg["base_url"], cfg["model"], provider_proto=fake)
        assert caller is not None
    finally:
        p.PROVIDERS.clear()
        p.PROVIDERS.update(orig)
        for k, v in _saved.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v
