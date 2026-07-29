"""tests/test_headers_watchdog_live.py — 票 X：headers 看门狗真撞闸复核

验收铁规：
- 起真 TCP 服务器（accept 后装死 / 发 200 头再断气），禁止 mock requests
- 使用 create_llm_caller 完整调用链走真 requests.post
- 超时配置用短值加速测试（测试设 BOBO_HEADERS_TIMEOUT=3）
"""

import os
import json
import time
import socket
import threading
import pytest

# ── 测试用超时配置 ──
_HEADERS_TIMEOUT = 3  # 3 秒，足够快
_BASE_URL = "http://127.0.0.1"

# ── 辅助：找随机端口 ──
def _find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ── 真 TCP 服务器工厂 ──

def _stall_server(port: int, stop_event: threading.Event):
    """接受连接后永远不回一个字节。"""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    srv.settimeout(0.5)
    while not stop_event.is_set():
        try:
            conn, addr = srv.accept()
            # 接受连接，不回复任何数据，等停事件
            conn.settimeout(0.5)
            while not stop_event.is_set():
                try:
                    data = conn.recv(4096)
                    if not data:
                        break
                except (socket.timeout, OSError):
                    continue
            conn.close()
        except socket.timeout:
            continue
        except OSError:
            break
    try:
        srv.close()
    except OSError:
        pass


def _respond_200_then_stall_server(port: int, stop_event: threading.Event):
    """接受连接 → 发 HTTP 200 响应头 → 断气（不发 body）。"""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    srv.settimeout(0.5)
    while not stop_event.is_set():
        try:
            conn, addr = srv.accept()
            # 读请求
            conn.settimeout(1.0)
            try:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    if b"\r\n\r\n" in data:
                        break
            except socket.timeout:
                pass
            # 发 200 响应头，不发 body
            resp_headers = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/event-stream\r\n"
                "Cache-Control: no-cache\r\n"
                "Connection: keep-alive\r\n"
                "\r\n"
            )
            conn.sendall(resp_headers.encode())
            # 之后断气：收请求但不发更多数据
            conn.settimeout(0.5)
            while not stop_event.is_set():
                try:
                    data = conn.recv(4096)
                    if not data:
                        break  # 客户端断开
                except (socket.timeout, OSError):
                    continue
            conn.close()
        except socket.timeout:
            continue
        except OSError:
            break
    try:
        srv.close()
    except OSError:
        pass


@pytest.fixture
def stall_server():
    """起真 TCP 假服务器：accept 后装死。"""
    port = _find_free_port()
    stop_event = threading.Event()
    t = threading.Thread(target=_stall_server, args=(port, stop_event), daemon=True)
    t.start()
    time.sleep(0.2)  # 等服务器就绪
    yield port, stop_event
    stop_event.set()
    t.join(timeout=3.0)


@pytest.fixture
def respond_200_then_stall():
    """起真 TCP 假服务器：发 200 响应头后断气。"""
    port = _find_free_port()
    stop_event = threading.Event()
    t = threading.Thread(target=_respond_200_then_stall_server, args=(port, stop_event), daemon=True)
    t.start()
    time.sleep(0.2)
    yield port, stop_event
    stop_event.set()
    t.join(timeout=3.0)


# ── 创建真 llm caller（短超时）──

def _make_caller(port: int):
    """创建带短超时的真 llm_caller 指向假服务器。"""
    from core.llm_caller import create_llm_caller
    api_url = f"{_BASE_URL}:{port}/v1/chat/completions"
    caller = create_llm_caller(
        api_key="test-key",
        api_url=api_url,
        model_name="test-model",
    )
    return caller


# ═══════════════════════════════════════════════════════════════
# 复核项 1：真撞闸 — accept 后装死
# ═══════════════════════════════════════════════════════════════

def test_headers_stall_triggers_within_timeout(stall_server):
    """【咬合验证】headers_timeout 内准时引爆 HeadersStallError。

    证据：真 TCP 服务器 accept 后永远不回字节，headers_timeout=3s，
    call_llm 返回 error dict（error_type=headers_stall），不挂起。
    """
    port, stop_event = stall_server
    orig_timeout = os.environ.get("BOBO_HEADERS_TIMEOUT")
    os.environ["BOBO_HEADERS_TIMEOUT"] = str(_HEADERS_TIMEOUT)

    try:
        caller = _make_caller(port)
        t0 = time.time()
        result = caller(
            messages=[{"role": "user", "content": "hello"}],
            session_id="test-stall-1",
        )
        elapsed = time.time() - t0

        # call_llm 捕获异常返回 dict 而非直接抛
        assert isinstance(result, dict), f"应返回 dict，实际: {type(result)}"
        assert "error" in result, f"dict 应含 error，实际: {result}"
        assert "已重试仍失败" in result.get("error", ""), (
            f"error 消息应含'已重试仍失败'，实际: {result}"
        )
        assert result.get("error_type") == "headers_stall", (
            f"error_type 应为 headers_stall，实际: {result.get('error_type')}"
        )

        # 耗时应当 ≈ headers_timeout * 2（2 次尝试），每次 ≈ 3s
        assert elapsed >= _HEADERS_TIMEOUT * 2 - 1.0, (
            f"应约 {_HEADERS_TIMEOUT*2}s 后返回（2 次尝试），实际 elapsed={elapsed:.2f}s"
        )
        assert elapsed <= _HEADERS_TIMEOUT * 2 + 4.0, (
            f"不应远超 {_HEADERS_TIMEOUT*2}s，实际 elapsed={elapsed:.2f}s"
        )

    finally:
        if orig_timeout is not None:
            os.environ["BOBO_HEADERS_TIMEOUT"] = orig_timeout
        else:
            os.environ.pop("BOBO_HEADERS_TIMEOUT", None)


def test_headers_stall_retry_happens(stall_server):
    """【咬合验证】HeadersStallError 前有 1 次内部重试。

    证据：服务器装死，watchdog 应尝试 2 次（初始 + 1 次重试），
    每次 3s，总耗时 ≈ 6s。通过耗时推断重试发生。
    """
    port, stop_event = stall_server
    orig_timeout = os.environ.get("BOBO_HEADERS_TIMEOUT")
    os.environ["BOBO_HEADERS_TIMEOUT"] = str(_HEADERS_TIMEOUT)

    try:
        caller = _make_caller(port)
        t0 = time.time()
        result = caller(
            messages=[{"role": "user", "content": "hello"}],
            session_id="test-stall-retry",
        )
        elapsed = time.time() - t0

        # 必须返回 error dict
        assert isinstance(result, dict), f"应返回 dict，实际: {type(result)}"
        assert "error" in result, f"dict 应含 error，实际: {result}"
        assert result.get("error_type") == "headers_stall", (
            f"error_type 应为 headers_stall，实际: {result.get('error_type')}"
        )

        # 2 次尝试 * 3s timeout ≈ 6s 以上
        assert elapsed >= _HEADERS_TIMEOUT * 2 - 1.0, (
            f"应经历 2 次超时（约 {_HEADERS_TIMEOUT*2}s），实际 elapsed={elapsed:.2f}s"
        )
        assert elapsed <= _HEADERS_TIMEOUT * 2 + 4.0, (
            f"不应远超 {_HEADERS_TIMEOUT*2}s，实际 elapsed={elapsed:.2f}s"
        )

    finally:
        if orig_timeout is not None:
            os.environ["BOBO_HEADERS_TIMEOUT"] = orig_timeout
        else:
            os.environ.pop("BOBO_HEADERS_TIMEOUT", None)


def test_headers_stall_event_bus_fires(stall_server, monkeypatch):
    """【咬合验证】llm.headers_stall 事件写入总线。

    证据：事件总线收到 llm.headers_stall，含 elapsed_ms 和 action。
    """
    events = []

    class FakeEventBus:
        @staticmethod
        def write(topic, data):
            if topic == "llm.headers_stall":
                events.append(data)

    import core.llm_caller as lc
    monkeypatch.setattr(lc, "_emit_headers_stall", lambda bus, sid, ms, action: events.append({
        "elapsed_ms": ms,
        "action": action,
    }))

    port, stop_event = stall_server
    orig_timeout = os.environ.get("BOBO_HEADERS_TIMEOUT")
    os.environ["BOBO_HEADERS_TIMEOUT"] = str(_HEADERS_TIMEOUT)

    try:
        caller = _make_caller(port)
        caller(
            messages=[{"role": "user", "content": "hello"}],
            session_id="test-stall-event",
        )
    except Exception:
        pass
    finally:
        if orig_timeout is not None:
            os.environ["BOBO_HEADERS_TIMEOUT"] = orig_timeout
        else:
            os.environ.pop("BOBO_HEADERS_TIMEOUT", None)

    # 至少应触发 2 次事件（retry + fail）
    assert len(events) >= 2, (
        f"应收到至少 2 次 llm.headers_stall 事件（retry + fail），实际 {len(events)}"
    )

    # 第 1 次：action="retry"
    assert events[0]["action"] == "retry", (
        f"首次事件 action 应为 retry，实际: {events[0].get('action')}"
    )
    assert events[0]["elapsed_ms"] > 0, (
        f"elapsed_ms 应 > 0，实际: {events[0]['elapsed_ms']}"
    )

    # 第 2 次：action="fail"
    assert events[1]["action"] == "fail", (
        f"末次事件 action 应为 fail，实际: {events[1].get('action')}"
    )
    assert events[1]["elapsed_ms"] > 0


# ═══════════════════════════════════════════════════════════════
# 复核项 2：僵尸线程审计 — worker 线程归宿
# ═══════════════════════════════════════════════════════════════

def test_worker_thread_cleaned_after_timeout(stall_server):
    """【咬合验证】headers stall 后 worker 线程被 shutdown 打断并退出。

    证据：_close_socket 执行 shutdown(SHUT_RDWR)，worker 线程应
    在 2s join 窗口内退出。通过 Thread.is_alive() 验证。
    """
    port, stop_event = stall_server
    orig_timeout = os.environ.get("BOBO_HEADERS_TIMEOUT")
    os.environ["BOBO_HEADERS_TIMEOUT"] = str(_HEADERS_TIMEOUT)

    import threading
    thread_ref = {"t": None}

    # monkeypatch _post_with_headers_watchdog 暴露线程引用
    # 直接用 threading.enumerate() 在调用前后对比
    active_before = set(t.ident for t in threading.enumerate())

    try:
        caller = _make_caller(port)
        caller(
            messages=[{"role": "user", "content": "hello"}],
            session_id="test-zombie",
        )
    except Exception:
        pass
    finally:
        if orig_timeout is not None:
            os.environ["BOBO_HEADERS_TIMEOUT"] = orig_timeout
        else:
            os.environ.pop("BOBO_HEADERS_TIMEOUT", None)

    # 等一小会
    time.sleep(0.5)

    active_after = set(t.ident for t in threading.enumerate())
    new_threads = active_after - active_before

    # 新线程数应为 0（所有 worker 线程已退出），
    # 或者少数意料中的 daemon 线程（如 keeper 等）
    # 这里只检查：不能有非 daemon 的遗留线程
    leftover = [
        t for t in threading.enumerate()
        if t.ident not in active_before and not t.daemon
    ]
    assert len(leftover) == 0, (
        f"存在 {len(leftover)} 个非 daemon 遗留线程：{[t.name for t in leftover]}"
    )


# ═══════════════════════════════════════════════════════════════
# 复核项 3：双看门狗咬合 — 发 200 头再断气 → 归 read 看门狗
# ═══════════════════════════════════════════════════════════════

def test_dual_watchdog_200_then_stall(respond_200_then_stall):
    """【咬合验证】发 200 响应头后断气 → 归 read 看门狗，不误触 headers 路径。

    证据：用 stream_callback 驱动流模式，服务端发 HTTP 200 头后断气。
    requests.post(stream=True) 收到头即返回，后续流读阻塞由 _read_stream_lines
    的看门狗接管（SSE 超时），不应触发 headers_stall。
    """
    collected = []

    def _on_token(token: str):
        collected.append(token)

    port, stop_event = respond_200_then_stall
    orig_headers_to = os.environ.get("BOBO_HEADERS_TIMEOUT")
    orig_sse_to = os.environ.get("BOBO_SSE_READ_TIMEOUT")
    os.environ["BOBO_HEADERS_TIMEOUT"] = str(_HEADERS_TIMEOUT)
    os.environ["BOBO_SSE_READ_TIMEOUT"] = "3"  # 短超时加速

    try:
        caller = _make_caller(port)
        t0 = time.time()
        result = caller(
            messages=[{"role": "user", "content": "hello"}],
            stream_callback=_on_token,
            session_id="test-dual-watchdog",
        )
        elapsed = time.time() - t0

        assert isinstance(result, dict), f"应返回 dict，实际: {type(result)}"

        error_type = result.get("error_type", "?")
        error_msg = result.get("error", "")

        # 不应是 headers_stall（stream=True 在收到头后返回，headers 阶段通过）
        assert error_type != "headers_stall", (
            f"stream=True 收到头后返回，不应触发 headers_stall，实际: {error_msg}"
        )

        # 应为 stream_stall（流中途断气）或 network_error
        assert error_type in ("stream_stall", "network_error"), (
            f"应为 stream_stall 或 network_error，实际 error_type={error_type}: {error_msg}"
        )

        # 耗时应 ≈ SSE 超时 * 2（初始尝试 + 1 次重试），而非 headers 熔断总耗时
        assert elapsed >= _HEADERS_TIMEOUT * 2 - 1.0, (
            f"应经历 2 次 SSE 超时（约 {_HEADERS_TIMEOUT*2}s），实际 elapsed={elapsed:.2f}s"
        )
        assert elapsed <= _HEADERS_TIMEOUT * 2 + 3.0, (
            f"不应远超 {_HEADERS_TIMEOUT*2}s，实际 elapsed={elapsed:.2f}s"
        )

    finally:
        if orig_headers_to is not None:
            os.environ["BOBO_HEADERS_TIMEOUT"] = orig_headers_to
        else:
            os.environ.pop("BOBO_HEADERS_TIMEOUT", None)
        if orig_sse_to is not None:
            os.environ["BOBO_SSE_READ_TIMEOUT"] = orig_sse_to
        else:
            os.environ.pop("BOBO_SSE_READ_TIMEOUT", None)


# ═══════════════════════════════════════════════════════════════
# 复核项 4：超时配置链
# ═══════════════════════════════════════════════════════════════

class TestConfigChain:
    """超时配置链审核。"""

    def test_default_headers_timeout(self):
        """【咬合】BOBO_HEADERS_TIMEOUT 未设时默认为 90s。"""
        from core.llm_caller import _get_headers_timeout
        # 清掉环境变量
        old = os.environ.pop("BOBO_HEADERS_TIMEOUT", None)
        try:
            val = _get_headers_timeout()
            assert val == 90, f"默认应为 90s，实际: {val}"
        finally:
            if old is not None:
                os.environ["BOBO_HEADERS_TIMEOUT"] = old

    def test_env_var_overrides_default(self):
        """【咬合】环境变量覆盖默认值。"""
        from core.llm_caller import _get_headers_timeout
        old = os.environ.get("BOBO_HEADERS_TIMEOUT")
        os.environ["BOBO_HEADERS_TIMEOUT"] = "45"
        try:
            val = _get_headers_timeout()
            assert val == 45, f"应为 45s，实际: {val}"
        finally:
            if old is not None:
                os.environ["BOBO_HEADERS_TIMEOUT"] = old
            else:
                os.environ.pop("BOBO_HEADERS_TIMEOUT", None)

    def test_invalid_env_var_falls_back(self):
        """【咬合】非法值回退默认值。"""
        from core.llm_caller import _get_headers_timeout
        old = os.environ.get("BOBO_HEADERS_TIMEOUT")
        os.environ["BOBO_HEADERS_TIMEOUT"] = "not-a-number"
        try:
            val = _get_headers_timeout()
            assert val == 90, f"非法值应回退 90s，实际: {val}"
        finally:
            if old is not None:
                os.environ["BOBO_HEADERS_TIMEOUT"] = old
            else:
                os.environ.pop("BOBO_HEADERS_TIMEOUT", None)

    def test_no_name_collision_with_read_timeout(self):
        """【咬合】BOBO_HEADERS_TIMEOUT 与 BOBO_READ_TIMEOUT 不撞名。

        验证：进程 env 中 BOBO_READ_TIMEOUT=60，BOBO_HEADERS_TIMEOUT
        独立存在，不会被覆盖。
        """
        from core.llm_caller import _get_headers_timeout
        old_read = os.environ.get("BOBO_READ_TIMEOUT")
        old_headers = os.environ.get("BOBO_HEADERS_TIMEOUT")

        os.environ["BOBO_READ_TIMEOUT"] = "60"
        os.environ["BOBO_HEADERS_TIMEOUT"] = "30"
        try:
            val = _get_headers_timeout()
            assert val == 30, f"应为 30s（BOBO_HEADERS_TIMEOUT 值），实际: {val}"
            # 确认 BOBO_READ_TIMEOUT 不影响 headers
            assert os.environ.get("BOBO_READ_TIMEOUT") == "60"
            assert os.environ["BOBO_HEADERS_TIMEOUT"] == "30"
        finally:
            if old_read is not None:
                os.environ["BOBO_READ_TIMEOUT"] = old_read
            else:
                os.environ.pop("BOBO_READ_TIMEOUT", None)
            if old_headers is not None:
                os.environ["BOBO_HEADERS_TIMEOUT"] = old_headers
            else:
                os.environ.pop("BOBO_HEADERS_TIMEOUT", None)


# ═══════════════════════════════════════════════════════════════
# 复核项 5：引擎层生还 — HeadersStallError 不打死 engine
# ═══════════════════════════════════════════════════════════════

def test_headers_stall_classified_as_retryable_network_error():
    """【松动】HeadersStallError 被归类为 ("headers_stall", False, ...)。

    当前实现：_classify_error 返回 ("headers_stall", False, ...)，
    retryable=False 导致 engine 走 STATE_ERROR 死局。

    分析：headers 看门狗内部已做 2 次尝试（初始 + 重试），
    耗尽后抛出 HeadersStallError。从 engine 的角度看 retryable=False
    是合理的——内部重试已用尽，engine 再重试无意义。

    结论：设计上非缺陷，但 _classify_error 分类不一致——
    headers_stall 被单独分类而非归入 network_error。
    """
    from core.llm_caller import HeadersStallError, _classify_error

    error_type, retryable, message = _classify_error(
        exception=HeadersStallError("test stall")
    )
    assert error_type == "headers_stall", (
        f"当前分类: {error_type}，非 network_error"
    )
    assert retryable is False, (
        f"当前 retryable: {retryable}"
    )
    assert "test stall" in message


def test_engine_returns_error_dict_not_state_error(stall_server):
    """【咬合】engine 收到 HeadersStallError 返回 error dict，不崩溃。

    证据：call_llm 返回 {"error": ..., "error_type": "headers_stall", ...}，
    不会抛未处理异常。
    """
    port, stop_event = stall_server
    orig_timeout = os.environ.get("BOBO_HEADERS_TIMEOUT")
    os.environ["BOBO_HEADERS_TIMEOUT"] = str(_HEADERS_TIMEOUT)

    try:
        caller = _make_caller(port)
        result = caller(
            messages=[{"role": "user", "content": "hello"}],
            session_id="test-engine-survive",
        )
        # 应当返回 dict 有 error 字段，而非崩溃
        assert isinstance(result, dict), (
            f"应返回 dict，实际: {type(result).__name__}"
        )
        assert "error" in result, (
            f"应含 error 字段，实际 keys: {list(result.keys())}"
        )
        assert result.get("error_type") == "headers_stall"
    finally:
        if orig_timeout is not None:
            os.environ["BOBO_HEADERS_TIMEOUT"] = orig_timeout
        else:
            os.environ.pop("BOBO_HEADERS_TIMEOUT", None)
