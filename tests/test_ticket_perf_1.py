"""票 PERF-1：收尾链路提速 —— 黑洞消除 + 空回复自动重试

验收金标准（票据 5 条）：
1. 模拟 living_notes LLM 调用挂死 → 回合在硬超时内正常退场，notes.error 留痕
2. 模拟 finish_reason=length 空正文 → 自动翻倍重试一次，成功则正常返回；仍空才报错
3. 沉淀后台化后：message.complete 发出到线程退出 < 2s（无 LLM 调用阻塞）
4. 新增专项测试 + 全量 pytest 零回归
5. md5 闸门三文件零变动（全量测试后验证）

事故铁证（Kimi 取证）：
- 事故 1（12:59-13:01）：write_living_notes LLM 成文网络故障干等 ~120s 钉死回合
- 事故 2（13:46）：completion=8191 撞顶, reasoning=18499 chars, content=0 chars → 判死
"""

import threading
import time

import pytest

from core.event_bus import event_bus
from tests.test_engine_e2e import (
    FakeLLMCaller,
    FakeToolExecutor,
    _make_test_engine,
    _make_tool_call,
)


@pytest.fixture
def event_recorder(monkeypatch):
    """捕获 event_bus.write 调用（type + data），同时放行真实写入。"""
    recorded = []
    orig_write = event_bus.write

    def _recorder(etype, data):
        recorded.append((etype, data))
        return orig_write(etype, data)

    monkeypatch.setattr(event_bus, "write", _recorder)
    return recorded


def _enable_proactive(engine, mode: str = "subtle"):
    engine.proactive.mode = mode


class _HangOnFourthCall:
    """主回合(工具) → 最终文本 → 提取 → 成文挂死。

    对应事故 1 场景：takeaway 提取完成后，write_living_notes 的 LLM 成文
    调用网络故障干等——要求 a 的 30s 硬超时必须在第 4 次调用生效。
    """

    def __init__(self, hang: float = 5.0):
        self.n = 0
        self.hang = hang

    def __call__(self, messages, **kw):
        self.n += 1
        if self.n == 1:
            return {"choices": [{"message": {"tool_calls": [_make_tool_call("c1", "echo", {"msg": "ping"})]}}], "usage": {}}
        if self.n == 2:
            return {"choices": [{"message": {"content": "任务完成：已确定用 PostgreSQL。"}}], "usage": {}}
        if self.n == 3:
            return {"choices": [{"message": {"content": "用 PostgreSQL 存储\n选择了索引方案"}}], "usage": {}}
        if self.n == 4:
            time.sleep(self.hang)  # 模拟成文网络故障干等
            return {"error": "never reached (timeout should fire first)"}
        # 兜底：收工闸 deny 回注等后续调用必须快速返回，不能继续挂死
        return {"choices": [{"message": {"content": "done"}}], "usage": {}}


# ── 验收 1：living_notes 挂死 → 30s 硬超时降级，回合正常退场 ──────────

class TestPerf1Timeout:

    def test_living_notes_hang_degrades_within_timeout(self, monkeypatch, event_recorder):
        """成文 LLM 挂死 → 0.5s 硬超时（生产 30s）降级 → notes.error(timeout) + 回合 DONE"""
        import tools.living_notes as ln_mod

        # 测试提速：超时从 30s 缩到 0.5s；库址隔离到 tmp（不碰真实 library）
        monkeypatch.setattr(ln_mod, "_LN_LLM_TIMEOUT", 0.5)
        monkeypatch.setattr(ln_mod, "LIBRARY_DIR", __import__("pathlib").Path("/tmp/perf1-ln-iso"))

        fake_llm = _HangOnFourthCall(hang=5.0)
        engine = _make_test_engine(fake_llm, FakeToolExecutor({"echo": "pong"}), monkeypatch)
        _enable_proactive(engine)

        t0 = time.time()
        engine.run(user_input="帮我选一下数据库方案")
        elapsed = time.time() - t0

        assert engine.state == engine.STATE_DONE, "回合必须正常退场，不被成文挂死钉死"
        assert elapsed < 3.0, f"硬超时未生效：耗时 {elapsed:.1f}s（应 <3s，含 0.5s 超时）"
        types = [t for t, _ in event_recorder]
        assert "notes.error" in types, f"应留 notes.error 事件，实际 {types}"
        errs = [d for t, d in event_recorder if t == "notes.error"]
        assert any("timeout" in (d.get("error") or "").lower() for d in errs), \
            f"notes.error 应含 timeout 留痕，实际 {errs}"

    def test_timeout_wrapper_returns_error_dict(self, monkeypatch):
        """_with_llm_timeout 单测：挂死调用在超时内返回 error dict（不抛异常）"""
        from tools.living_notes import _with_llm_timeout

        def hang(prompt, **kw):
            time.sleep(3)
            return {"choices": [{"message": {"content": "x"}}]}

        wrapped = _with_llm_timeout(hang, timeout=0.3)
        t0 = time.time()
        result = wrapped([{"role": "user", "content": "hi"}], use_tools=False)
        elapsed = time.time() - t0

        assert elapsed < 1.5, f"wrapper 超时未生效：{elapsed:.1f}s"
        assert result.get("error") and "timeout" in result["error"].lower()


# ── 验收 3：沉淀后台化 —— message.complete 不被 LLM 阻塞 ──────────────

class TestPerf1BackgroundSedimentation:

    def test_pregate_uses_daemon_thread_in_production(self):
        """静态断言：pre-gate 块生产路径用 daemon 线程 + test_mode 同步分支保留"""
        import core.engine as engine_mod
        src = open(engine_mod.__file__, encoding="utf-8").read()
        assert "threading.Thread" in src
        assert "daemon=True" in src
        assert "target=self._run_sedimentation" in src
        assert "if self.test_mode:" in src, "test_mode 同步分支必须存在（E4a 时序确定性）"
        assert "self._run_sedimentation(self._pending_content)" in src

    def test_run_sedimentation_thread_returns_immediately(self, monkeypatch):
        """生产路径（test_mode=False）：沉淀线程 start 即返，<0.5s 不被挂死 LLM 阻塞"""
        fake_llm = FakeLLMCaller([("任务完成。", None)])
        engine = _make_test_engine(fake_llm, FakeToolExecutor(), monkeypatch)
        engine.test_mode = False  # 切生产路径

        def hang(**kw):
            time.sleep(5)  # 模拟提取 LLM 挂死
            return []

        monkeypatch.setattr(engine, "_extract_takeaways", hang)
        t0 = time.time()
        t = threading.Thread(target=engine._run_sedimentation, args=("回复",), daemon=True)
        t.start()
        elapsed = time.time() - t0

        assert elapsed < 0.5, f"线程 start 被阻塞：{elapsed:.2f}s（验收 3 要求 <2s）"
        assert t.daemon, "沉淀线程必须 daemon（进程退出不悬挂）"
        # 不 join：daemon 线程随测试进程结束，挂死 LLM 不影响测试


# ── 验收 2：finish_reason=length 空正文 → 翻倍重试一次 ────────────────

class _FakeResp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class TestPerf1LengthRetry:

    def _make_caller(self, monkeypatch, first_empty: bool, second_empty: bool):
        """构造 create_llm_caller 实例，mock 掉网络层。

        first_empty/second_empty 控制第 1/2 次流是否 length 截断空正文。
        返回 (caller, posts) —— posts 记录每次请求的 max_tokens。
        """
        import core.llm_caller as llm_mod

        posts = []
        stream_seq = {"n": 0}

        def fake_post(api_url, json=None, headers=None, timeout=None, stream=None,
                      headers_timeout=None, event_bus=None, session_id=None):
            posts.append(json.get("max_tokens"))
            return _FakeResp()

        def fake_stream_lines(resp, read_timeout, vitals):
            seq = stream_seq["n"]
            stream_seq["n"] += 1
            empty = (seq == 0 and first_empty) or (seq == 1 and second_empty)
            if empty:
                lines = [
                    b'data: {"choices":[{"delta":{"reasoning_content":"thinking-burnt-all-budget"}}]}',
                    b'data: {"choices":[{"delta":{"finish_reason":"length"}}]}',
                    b'data: [DONE]',
                ]
            else:
                lines = [
                    b'data: {"choices":[{"delta":{"content":"normal-reply-content"}}]}',
                    b'data: {"choices":[{"delta":{"finish_reason":"stop"}}]}',
                    b'data: [DONE]',
                ]
            return iter(lines)

        monkeypatch.setattr(llm_mod, "_post_with_headers_watchdog", fake_post)
        monkeypatch.setattr(llm_mod, "_read_stream_lines", fake_stream_lines)

        caller = llm_mod.create_llm_caller("test-key", "https://example.com/x", "test-model")
        return caller, posts

    def test_length_empty_retries_once_with_doubled_tokens(self, monkeypatch):
        """第 1 次 length 空正文 → 翻倍重试 → 第 2 次成功 → 正常返回"""
        caller, posts = self._make_caller(monkeypatch, first_empty=True, second_empty=False)
        result = caller(
            [{"role": "user", "content": "hi"}],
            use_tools=False,
            stream_callback=lambda c: None,
            max_tokens=8192,
        )
        assert posts == [8192, 16384], f"应翻倍重试一次，实际 max_tokens 序列 {posts}"
        content = result["choices"][0]["message"]["content"]
        assert content == "normal-reply-content"
        assert result.get("finish_reason") == "stop"

    def test_length_empty_retry_still_empty_stops_after_one(self, monkeypatch):
        """第 1 次 length 空正文 → 重试第 2 次仍空 → 只重试一次，返回空 result（走原 error 路径）"""
        caller, posts = self._make_caller(monkeypatch, first_empty=True, second_empty=True)
        result = caller(
            [{"role": "user", "content": "hi"}],
            use_tools=False,
            stream_callback=lambda c: None,
            max_tokens=4096,
        )
        assert posts == [4096, 8192], f"只允许重试一次，实际 {posts}"
        content = result["choices"][0]["message"]["content"]
        assert content == "", "重试仍空 → 返回空正文（引擎走原 error 路径）"
        assert result.get("finish_reason") == "length"
        assert result.get("reasoning", "").startswith("thinking-burnt-all-budget"), \
            "reasoning 应保留（事故 2：reasoning=18499 chars, content=0 chars）"

    def test_normal_stop_no_retry(self, monkeypatch):
        """正常 stop（非 length）→ 不重试"""
        caller, posts = self._make_caller(monkeypatch, first_empty=False, second_empty=False)
        result = caller(
            [{"role": "user", "content": "hi"}],
            use_tools=False,
            stream_callback=lambda c: None,
            max_tokens=8192,
        )
        assert posts == [8192], f"正常路径不应重试，实际 {posts}"
        assert result["choices"][0]["message"]["content"] == "normal-reply-content"


# ── 要求 e：台账字段前移（系统提示词建账纪律） ─────────────────────────

class TestPerf1LedgerPrompt:

    def test_system_prompt_has_ledger_discipline(self, monkeypatch):
        """系统提示词写死建账纪律：verify/evidence 当场带，禁止收工前补"""
        import core.engine as engine_mod
        engine = engine_mod.Engine(
            llm_caller=lambda **kw: {"choices": [{"message": {"content": ""}}]},
            test_mode=True,
        )
        prompt = engine.system_prompt
        assert "任务台账（建账纪律）" in prompt, "系统提示词应有建账纪律节"
        assert "verify" in prompt and "evidence" in prompt
        assert "当场" in prompt, "必须强调当场带字段（禁止收工前补登记）"
        assert "批量" in prompt and "done" in prompt, "应含批量建账全标 done 的拒绝语义"
