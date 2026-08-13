"""
core/llm_caller.py — 票 N2 + R：应用层 headers 看门狗 + 流式看门狗 + 断流重试

票 N2：requests 的 timeout=(connect, read) 只对单次 read() 系统调用生效，
对 iter_lines() 块间间隙无效。服务端挂起不发数据时，iter_lines()
永远阻塞，requests 超时不会触发。
修复：读者线程 + 队列架构。daemon 线程在 socket 上裸阻塞读，
主循环 q.get(timeout=1.0) 轮询；距上一内容块超过
BOBO_SSE_READ_TIMEOUT (默认 120s) 无数据时，主动抛
ConnectionError → 按断流重试。

票 R：READ_TIMEOUT=30 只保护"初始响应首字节前的单次 read"，服务器/网关
每 <30s 滴漏一个字节即可重置 read 计时器，状态行永远等不齐。SSE 看门狗
只在响应头到达后上岗，管不到 headers 阶段。
修复：requests.post 放进 worker 线程，主线程 join(timeout=headers_timeout)；
超时则关闭底层 socket 打断阻塞，按断流重试通道处理（硬上限 1 次）。

铁律（探针实证 /tmp/sse_probe.py）：socket 上设 1s 轮询超时是死路——
第一次 read 超时会污染 httplib 状态机，后续所有 read 立即返回 b''（EOF 假象），
僵尸流被误判为"干净读完返回空内容"。socket 上绝不设超时，隔离只能靠线程。
"""

import os as _os
import json
import queue as _queue
import socket as _socket
import time
import logging as _logging
import requests
import threading as _threading
import urllib3.connection as _urllib3_connection

_logger = _logging.getLogger(__name__)


class LLMInterrupted(Exception):
    """票 INT-1：用户中断（stop/cancel）——流式读循环发现中断标志置位时抛出。

    引擎捕获后走既有 interrupted 路径（STATE interrupted、回合正常退场、
    message.complete 带中断标记）；与网络/超时错误本质不同，绝不重试。
    """


def _force_close(response: requests.Response):
    """强行打断流式响应的阻塞读并关闭连接。

    铁律 2（探针实证 /tmp/n2_debug.py）：直接 response.close() 会与读者线程
    死锁——reader 持 SocketIO 锁阻塞在 readinto，close() 抢同一把锁，双双卡死。
    必须先 sock.shutdown(SHUT_RDWR) 打断阻塞读，再 best-effort close。
    """
    try:
        _sock = response.raw._fp.fp.raw._sock  # urllib3 → httplib → 真 socket
        _sock.shutdown(_socket.SHUT_RDWR)
    except Exception:
        pass
    try:
        response.close()
    except Exception:
        pass


# ── 票 R：headers 阶段总预算看门狗 ──

_HEADERS_TIMEOUT_DEFAULT = 90  # 秒


class HeadersStallError(requests.exceptions.ConnectionError):
    """headers 阶段在总预算内未收到响应头。"""


def _get_headers_timeout() -> int:
    """获取 headers 阶段总预算（秒），默认 90s，可被 BOBO_HEADERS_TIMEOUT 覆盖。"""
    try:
        return int(_os.environ.get("BOBO_HEADERS_TIMEOUT", str(_HEADERS_TIMEOUT_DEFAULT)))
    except (ValueError, TypeError):
        return _HEADERS_TIMEOUT_DEFAULT


def _emit_headers_stall(event_bus, session_id: str, elapsed_ms: int, action: str):
    """向事件总线写入 llm.headers_stall 事件。"""
    if event_bus is None:
        return
    try:
        event_bus.write("llm.headers_stall", {
            "session_id": session_id,
            "elapsed_ms": elapsed_ms,
            "action": action,  # "retry" | "fail"
        })
    except Exception:
        _logger.warning("llm.headers_stall event write failed", exc_info=True)


def _close_socket(sock):
    """票 R：强行打断 headers 阶段阻塞的 socket（_force_close 同款铁律 2）。

    必须先 shutdown(SHUT_RDWR) 打断阻塞读，再 best-effort close。
    """
    try:
        sock.shutdown(_socket.SHUT_RDWR)
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass


def _post_with_headers_watchdog(
    url,
    json=None,
    headers=None,
    timeout=None,
    stream=False,
    headers_timeout=None,
    event_bus=None,
    session_id=None,
):
    """在 headers 阶段总预算保护下执行 requests.post。

    实现：把 requests.post 放进 worker 线程，主线程 join(timeout=headers_timeout)。
    超时则通过 monkeypatch urllib3.connection.HTTPConnection._new_conn 捕获的
    socket 执行 shutdown(SHUT_RDWR) 打断阻塞，然后按断流重试通道处理（硬上限 1 次）。

    返回 response（正常）或抛出 HeadersStallError（headers 阶段超时且已重试失败）。
    其他异常直接抛出，交给外层重试逻辑处理。
    """
    if headers_timeout is None:
        headers_timeout = _get_headers_timeout()

    _original_new_conn = _urllib3_connection.HTTPConnection._new_conn

    for _headers_attempt in range(2):  # 初始 1 次 + 硬上限 1 次重试
        _start = time.time()
        _q = _queue.Queue(maxsize=1)
        _sock_holder = {"sock": None}
        _retried = _headers_attempt > 0

        def _patched_new_conn(conn):
            sock = _original_new_conn(conn)
            _sock_holder["sock"] = sock
            return sock

        def _worker():
            try:
                _urllib3_connection.HTTPConnection._new_conn = _patched_new_conn
                _resp = requests.post(
                    url,
                    json=json,
                    headers=headers,
                    timeout=timeout,
                    stream=stream,
                )
                _q.put(("ok", _resp))
            except Exception as _exc:  # noqa: BLE001
                _q.put(("err", _exc))
            finally:
                _urllib3_connection.HTTPConnection._new_conn = _original_new_conn

        _t = _threading.Thread(target=_worker)
        _t.start()
        _t.join(timeout=headers_timeout)

        if not _t.is_alive():
            # 正常完成（或 worker 自己先抛异常）
            try:
                _kind, _payload = _q.get(timeout=0.0)
            except _queue.Empty:
                continue
            _urllib3_connection.HTTPConnection._new_conn = _original_new_conn
            if _kind == "ok":
                return _payload
            raise _payload

        # headers 阶段总预算耗尽：打断 socket
        _elapsed_ms = int((time.time() - _start) * 1000)
        _sock = _sock_holder["sock"]
        if _sock is not None:
            _close_socket(_sock)
        _t.join(timeout=2.0)
        _emit_headers_stall(event_bus, session_id, _elapsed_ms, "retry" if not _retried else "fail")

        if _retried:
            _urllib3_connection.HTTPConnection._new_conn = _original_new_conn
            raise HeadersStallError(
                f"headers 阶段总预算 {headers_timeout}s 耗尽，已重试仍失败"
            )

        # 首次 headers stall → 重试 1 次（继续下一轮循环）
        _logger.warning(
            "headers 阶段超时: elapsed=%dms, session=%s, 准备重试",
            _elapsed_ms, session_id or "?",
        )

    # 理论上不会到达这里
    _urllib3_connection.HTTPConnection._new_conn = _original_new_conn
    raise HeadersStallError("headers 阶段看门狗异常退出")


def _get_sse_read_timeout() -> int:
    """获取 SSE 流式读超时（秒），默认 120s，可被环境变量 BOBO_SSE_READ_TIMEOUT 覆盖。

    120s 依据：DeepSeek 实测块间隔秒级；reasoning 模型（K3）思考期可能 30-90s 无块，
    120s 留足余量又保证假死 2 分钟内必被发现。
    """
    try:
        return int(_os.environ.get("BOBO_SSE_READ_TIMEOUT", "120"))
    except (ValueError, TypeError):
        return 120


def _read_stream_lines(response: requests.Response, read_timeout: int, vitals: dict, _interrupt_event=None):
    """读者线程 + 队列方式产出 SSE 原始字节行。

    daemon 线程在 response.raw.read(4096) 上裸阻塞（socket 无超时），
    往队列放 ("data", chunk) / ("eof", None) / ("err", exc)。
    主循环 q.get(timeout=1.0) 轮询，用 vitals["last_chunk"] 判定看门狗。

    vitals["last_chunk"] 由调用方在收到内容行（content / reasoning_content /
    tool_calls）时刷新——裸字节、注释行不刷新，防僵尸流滴 keep-alive 骗过看门狗。

    Yields:
        bytes: 一行原始字节（不含换行）。

    Raises:
        requests.exceptions.ConnectionError: 看门狗引爆（内容块静默超 read_timeout）
            或底层读异常（重试通道统一处理）。
    """
    q: _queue.Queue = _queue.Queue()

    def _reader():
        # 用 read1 而非 read：read(4096) 会攒满 4096 字节才返回（_fp_read 循环），
        # 服务器发小块后静默时数据永远卡在线程里；read1 单次 socket 读即返回。
        # decode_content=True：requests 流模式下 raw 默认不解压，裸读拿到的是
        # brotli/gzip 压缩字节（moonshot SSE 回 Content-Encoding: br），必须开解压。
        response.raw.decode_content = True
        _read_once = getattr(response.raw, "read1", None) or response.raw.read
        try:
            while True:
                chunk = _read_once(4096)
                if not chunk:
                    q.put(("eof", None))
                    return
                q.put(("data", chunk))
        except Exception as exc:  # noqa: BLE001 — 任何读异常都上报主循环
            q.put(("err", exc))

    _t = _threading.Thread(target=_reader, daemon=True)
    _t.start()

    def _kill_and_raise(msg: str):
        # 看门狗引爆/读异常：先 shutdown 打断读者线程，再走断流重试
        _force_close(response)
        raise requests.exceptions.ConnectionError(msg)

    _sse_buf = b""
    while True:
        if time.time() - vitals["last_chunk"] > read_timeout:
            _kill_and_raise("SSE流看门狗: 服务端停止发送数据")
        try:
            kind, payload = q.get(timeout=1.0)
        except _queue.Empty:
            # 票 INT-1：完全静默（模型思考中零 chunk）时，q.get 每秒空转一次——
            # 在此检查中断标志，保证 stop 在无数据流下也 ≤1s 断流响应
            # （推理模型思考期可能整段不发字节，仅靠循环体每 chunk 检查不够）。
            if _interrupt_event is not None and _interrupt_event.is_set():
                _force_close(response)
                raise LLMInterrupted("user interrupt during stream (silent)")
            continue
        if kind == "eof":
            # 残留半行也吐出来（非 SSE 兜底需要完整字节）
            if _sse_buf:
                yield _sse_buf
            return
        if kind == "err":
            exc = payload
            if isinstance(
                exc,
                (
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ConnectionError,
                ),
            ):
                _force_close(response)
                raise exc
            _kill_and_raise(f"SSE 读取异常: {exc}")
        # data
        _sse_buf += payload
        if "raw" in vitals:
            vitals["raw"] += payload  # 票 P：累积原始字节，非 SSE 兜底用
        while b"\n" in _sse_buf:
            line, _sse_buf = _sse_buf.split(b"\n", 1)
            yield line


def _emit_stream_stall(event_bus, session_id: str, received_chunks: int, elapsed_ms: int, action: str):
    """向事件总线写入 llm.stream_stall 事件。"""
    if event_bus is None:
        return
    try:
        event_bus.write("llm.stream_stall", {
            "session_id": session_id,
            "received_chunks": received_chunks,
            "elapsed_ms": elapsed_ms,
            "action": action,  # "retry" | "fail"
        })
    except Exception:
        _logger.warning("llm.stream_stall event write failed", exc_info=True)


def _classify_error(exception: Exception = None, status_code: int = None,
                    response_body: str = None) -> tuple:
    """
    对 API 调用错误进行分类，判断是否可重试。
    
    Args:
        exception:  请求抛出的异常对象，如 ConnectionError、Timeout 等
        status_code: HTTP 响应状态码，如 401、429、500 等
        response_body: 响应体文本（用于区分同状态码不同错误，如 429 余额不足 vs 限流）
        
    Returns:
        tuple: (error_type: str, retryable: bool, message: str)
            - error_type: 错误类型标识
                "timeout"       — 连接超时或读取超时
                "rate_limit"    — 限流 (429)
                "fatal_insufficient_quota" — 余额不足 (429 + insufficient_quota)
                "server_error"  — 服务器错误 (5xx)
                "auth_error"    — 认证失败 (401/403)
                "bad_request"   — 请求错误 (400/其他4xx)
                "network_error" — 网络连接失败
                "unknown"       — 未知错误
            - retryable: 是否可重试
            - message:   人类可读的错误描述
    """
    # ── 基于异常分类 ──
    if exception is not None:
        exc_class = exception.__class__.__name__

        if isinstance(exception, HeadersStallError):
            return ("headers_stall", False, str(exception))

        if isinstance(exception, requests.exceptions.Timeout):
            return ("timeout", True, "请求超时，服务器未在预期时间内响应")

        if isinstance(exception, requests.exceptions.ConnectionError):
            return ("network_error", True, "网络连接失败，请检查网络")
        
        if isinstance(exception, requests.exceptions.HTTPError):
            return ("server_error", True, f"HTTP 错误: {str(exception)}")
        
        if isinstance(exception, (ValueError, json.JSONDecodeError)):
            return ("bad_request", False, f"响应解析失败: {str(exception)}")
        
        return ("unknown", False, f"未知错误: {exc_class}: {str(exception)}")
    
    # ── 基于状态码分类 ──
    if status_code is not None:
        # 余额不足关键词（小写匹配，同覆盖 401/403/429）
        _body_lower = response_body.lower() if response_body else ""
        _has_insufficient = any(kw in _body_lower for kw in
                                ["insufficient balance", "insufficient_quota", "余额不足", "balance insufficient"])
        
        if status_code == 401:
            if _has_insufficient:
                return ("fatal_insufficient_quota", False, "API 余额不足，请检查账户余额或充值")
            return ("auth_error", False, "认证失败，请检查 API Key 是否正确")
        
        if status_code == 403:
            if _has_insufficient:
                return ("fatal_insufficient_quota", False, "API 余额不足，请检查账户余额或充值")
            return ("auth_error", False, "权限不足，API Key 无权限访问此资源")
        
        if status_code == 429:
            if _has_insufficient:
                return ("fatal_insufficient_quota", False, "API 余额不足，请检查账户余额或充值")
            return ("rate_limit", True, "请求过于频繁，已被限流")
        
        if 500 <= status_code < 600:
            return ("server_error", True, f"服务暂不可用 (HTTP {status_code})")
        
        if 400 <= status_code < 500:
            return ("bad_request", False, f"请求错误 (HTTP {status_code})")
        
        return ("unknown", False, f"未知状态码: {status_code}")
    
    return ("unknown", False, "未知错误")


# 超时配置（秒）
CONNECT_TIMEOUT = 10   # 建立连接的超时时间
READ_TIMEOUT = 30      # 初始 POST 读超时（接收首字节够用，不再用于 SSE 流块间间隙）
# SSE 流块间间隙看门狗由 _SseWatchdog + BOBO_SSE_READ_TIMEOUT 管理

# 重试配置
MAX_RETRIES = 2        # 最大重试次数（初始请求 + 2 次重试 = 共 3 次尝试）
RETRY_DELAY_BASE = 1   # 基础等待时间（秒），指数退避


def create_llm_caller(api_key: str, api_url: str, model_name: str, tools_schema: list = None):
    def call_llm(messages, use_tools=True, stream_callback=None, retry_callback=None, tools_override=None, session_id=None, reasoning_callback=None, max_tokens=None, _interrupt_event=None):
        # 票 INT-1：非流式/流式共用入口前检查——中断已置位则直接抛异常短路
        # （仿 execute_terminal 的 _interrupt_event 注入方式，tool_runner/engine 注入，
        # 不暴露在 schema，LLM 无法伪造）
        if _interrupt_event is not None and _interrupt_event.is_set():
            raise LLMInterrupted("user interrupt before llm call")
        # 支持环境变量覆盖（reasoning 模型需要 temperature=1.0, max_tokens 更大）
        import os as _os
        _temperature = float(_os.environ.get("BOBO_TEMPERATURE", "0.3"))
        _max_tokens = (max_tokens if max_tokens is not None
                       else int(_os.environ.get("BOBO_MAX_TOKENS", "8192")))
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": _temperature,
            "max_tokens": _max_tokens,
        }
        # 票 PERF-1 事故 2：length 空正文翻倍重试标志（调用级，跨 attempt/流式非流式只重试一次）
        _length_retried = False
        # 如果调用方传了 tools_override，用它替换默认的 tools_schema
        active_tools = tools_override if tools_override is not None else tools_schema
        if use_tools and active_tools:
            payload["tools"] = active_tools
            payload["tool_choice"] = "auto"
        
        # 当提供了 stream_callback 时启用流式传输
        if stream_callback is not None:
            payload["stream"] = True
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        # 事件总线用于 headers stall / stream stall / reasoning 事件
        from core.event_bus import event_bus as _event_bus

        last_error = None
        response = None  # 防止 except 块中 UnboundLocalError（P0.2）

        for attempt in range(MAX_RETRIES + 1):
            try:
                # 票 R：headers 阶段总预算看门狗。timeout 的 read 部分只保护
                # 单次 read 调用，可被滴漏字节绕过；应用层用 worker 线程 + join
                # 给整个 headers 阶段加总预算，超时用 shutdown 打断 socket。
                response = _post_with_headers_watchdog(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                    stream=bool(stream_callback),
                    headers_timeout=_get_headers_timeout(),
                    event_bus=_event_bus,
                    session_id=session_id,
                )

                # ── HTTP 状态码检查 ──
                if response.status_code != 200:
                    error_type, retryable, message = _classify_error(
                        status_code=response.status_code,
                        response_body=response.text[:500]
                    )
                    if retryable and attempt < MAX_RETRIES:
                        delay = RETRY_DELAY_BASE * (2 ** attempt)
                        if retry_callback:
                            retry_callback(message, delay)
                        time.sleep(delay)
                        last_error = {"error": message, "error_type": error_type, "retryable": True}
                        continue
                    else:
                        return {
                            "error": message,
                            "error_type": error_type,
                            "retryable": retryable,
                            "detail": response.text
                        }

                # ── 流式模式 ──
                if stream_callback:
                    _stream_start = time.time()
                    _received_chunks = 0
                    _stream_retried = False

                    while True:
                        try:
                            full_content = ""
                            reasoning_buf = ""   # 票 P：reasoning_content 独立缓冲，绝不混入正文
                            tool_calls_buffer = []
                            usage = {}
                            _finish_reason = None   # 票 PERF-1 事故 2：流式 finish_reason 收集
                            _parsed_any = False  # 票 P：是否成功解析过任何 SSE 数据行
                            _got_done = False    # 是否收到 [DONE]（防半截 EOF 冒充完整流）
                            # 票 N2：读者线程 + 队列；看门狗只看"内容行"时间
                            _vitals = {"last_chunk": time.time(), "raw": bytearray()}

                            for _lbytes in _read_stream_lines(
                                response, _get_sse_read_timeout(), _vitals,
                                _interrupt_event=_interrupt_event,
                            ):
                                # ── 票 INT-1：每 chunk 查中断标志 ──
                                # 推理模型单次思考最长 86s（2026-08-13 13:46 实证），
                                # 期间 stop 置位无人可见 → 这里每收到一个 chunk 就检查，
                                # 置位即断流抛 LLMInterrupted（绝不重试，走引擎 interrupted 路径）。
                                # _force_close 先 shutdown 打断读者线程阻塞读再 close，防死锁（铁律 2）。
                                if (_interrupt_event is not None
                                        and _interrupt_event.is_set()):
                                    try:
                                        _force_close(response)
                                    except Exception:
                                        pass
                                    raise LLMInterrupted(
                                        "user interrupt during stream"
                                    )
                                _lstr = _lbytes.decode("utf-8", "replace")
                                if not _lstr.startswith("data: "):
                                    continue
                                _d = _lstr[6:]
                                if _d.strip() == "[DONE]":
                                    _got_done = True
                                    break
                                try:
                                    _parsed = json.loads(_d)
                                except json.JSONDecodeError:
                                    continue
                                _parsed_any = True
                                # 捕获 usage（部分 API 在流结束前返回）
                                if "usage" in _parsed:
                                    usage = _parsed["usage"]
                                _c = _parsed.get("choices", [])
                                if not _c:
                                    continue
                                _dl = _c[0].get("delta", {})
                                # 票 P：reasoning_content 独立收集（reasoning 模型思考过程）
                                # 不混入正文；也是生命体征，收到即刷新看门狗
                                _rc = _dl.get("reasoning_content") or ""
                                if _rc:
                                    reasoning_buf += _rc
                                    if reasoning_callback:
                                        reasoning_callback(_rc)
                                    _vitals["last_chunk"] = time.time()
                                _co = _dl.get("content", "")
                                if _co:
                                    full_content += _co
                                    stream_callback(_co)
                                    _received_chunks += 1
                                    # 票 N2：收到内容块 → 刷新看门狗
                                    _vitals["last_chunk"] = time.time()
                                _tc = _dl.get("tool_calls")
                                if _tc:
                                    tool_calls_buffer.extend(_tc)
                                    _vitals["last_chunk"] = time.time()
                                # 票 PERF-1 事故 2：SSE 最后一个 chunk 的 delta 带 finish_reason
                                _fr = _dl.get("finish_reason")
                                if _fr:
                                    _finish_reason = _fr

                            # ── 半截 EOF 防线 ──
                            # 解析过 SSE 数据却没等到 [DONE] 就 EOF = 服务器中途死亡，
                            # 半截流绝不能冒充完整响应 → 走断流重试
                            if _parsed_any and not _got_done:
                                raise requests.exceptions.ConnectionError(
                                    "SSE 流被截断: 未收到 [DONE] 连接已终止"
                                )

                            # ── 票 P：非 SSE 兜底解析 ──
                            # 服务端（如 moonshot 部分模型）对 stream=True 可能直接回普通 JSON，
                            # SSE 解析一行 data: 都找不到 → 整个响应体按非流式 JSON 重解析
                            _all_raw = bytes(_vitals["raw"])
                            if not _parsed_any and _all_raw.strip():
                                try:
                                    _body = json.loads(_all_raw.decode("utf-8", "replace"))
                                    _msg = _body.get("choices", [{}])[0].get("message", {})
                                    full_content = _msg.get("content") or ""
                                    reasoning_buf = (_msg.get("reasoning_content") or "") or reasoning_buf
                                    _finish_reason = (_body.get("choices", [{}])[0]
                                                      .get("finish_reason") or _finish_reason)  # 票 PERF-1
                                    if _msg.get("tool_calls"):
                                        tool_calls_buffer.extend(_msg["tool_calls"])
                                    if "usage" in _body:
                                        usage = _body["usage"]
                                    _logger.warning(
                                        "非 SSE 响应兜底命中: content=%d chars, reasoning=%d chars, session=%s",
                                        len(full_content), len(reasoning_buf), session_id or "?",
                                    )
                                    _emit_stream_stall(
                                        _event_bus, session_id,
                                        len(_all_raw), int((time.time() - _stream_start) * 1000),
                                        "non_sse_fallback",
                                    )
                                except (json.JSONDecodeError, ValueError, AttributeError):
                                    pass  # 真空响应，走原有空响应通道

                            # ── 票 PERF-1 事故 2：finish_reason=length 且正文为空 → 翻倍 max_tokens 重试一次 ──
                            # 根因：reasoning 模型思考烧光 max_tokens（content_chars=0、reasoning 有值），
                            # 引擎直接判 error 退出（2026-08-13 13:46 铁证：prompt=78140 tokens,
                            # completion=8191 撞顶, reasoning=18499 chars, content=0 chars）。
                            # 仅重试一次（_length_retried 防死循环）；重试仍空才走原 error 路径。
                            # 错误提示文案的 BOBO_MAX_TOKENS 指引保留不动（要求 d）。
                            # 位置必须在此（break 前、try 内）：continue 作用于 while True，
                            # 回到顶部用新 response 重读流；若放 try 外 continue 会落到外层 for。
                            if (_finish_reason == "length" and not full_content.strip()
                                    and not _length_retried):
                                _length_retried = True
                                _max_tokens = _max_tokens * 2
                                payload["max_tokens"] = _max_tokens
                                _logger.warning(
                                    "PERF-1 length 截断且正文为空（reasoning=%d chars, content=%d chars）"
                                    "— 翻倍 max_tokens 重试一次: %d→%d, session=%s",
                                    len(reasoning_buf), len(full_content),
                                    _max_tokens // 2, _max_tokens, session_id or "?",
                                )
                                try:
                                    _event_bus.write("llm.length_retry", {
                                        "session_id": session_id or "",
                                        "reasoning_chars": len(reasoning_buf),
                                        "content_chars": len(full_content),
                                        "max_tokens": _max_tokens,
                                    })
                                except Exception:
                                    pass
                                response = _post_with_headers_watchdog(
                                    api_url,
                                    json=payload,
                                    headers=headers,
                                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                                    stream=True,
                                    headers_timeout=_get_headers_timeout(),
                                    event_bus=_event_bus,
                                    session_id=session_id,
                                )
                                if response.status_code != 200:
                                    return {
                                        "error": f"length 重试 HTTP {response.status_code}",
                                        "error_type": "http",
                                        "retryable": False,
                                        "detail": response.text[:500],
                                    }
                                continue  # 回到 while True 顶部，用新 response 重读流

                            break  # 正常读完，退出 while

                        except (
                            requests.exceptions.ReadTimeout,
                            requests.exceptions.ChunkedEncodingError,
                            requests.exceptions.ConnectionError,
                        ) as _stall_err:
                            _elapsed_ms = int((time.time() - _stream_start) * 1000)
                            _logger.warning(
                                "SSE 流断流: type=%s, received=%d, elapsed=%dms, session=%s",
                                type(_stall_err).__name__,
                                _received_chunks, _elapsed_ms, session_id or "?",
                            )

                            if _stream_retried:
                                # 已重试过，不再重试
                                _emit_stream_stall(
                                    _event_bus, session_id,
                                    _received_chunks, _elapsed_ms, "fail",
                                )
                                return {
                                    "error": f"SSE 流断流（已重试仍失败）: {_stall_err}",
                                    "error_type": "stream_stall",
                                    "retryable": False,
                                }

                            # 首次断流 → 重试 1 次（丢弃半残流，全新请求）
                            _stream_retried = True
                            _emit_stream_stall(
                                _event_bus, session_id,
                                _received_chunks, _elapsed_ms, "retry",
                            )
                            if retry_callback:
                                retry_callback(
                                    f"SSE 流断流({type(_stall_err).__name__})，已收 {_received_chunks} 块—重试",
                                    0,
                                )
                            # 重置计数，重新发起请求（断流重试仍受 headers 看门狗保护）
                            _received_chunks = 0
                            response = _post_with_headers_watchdog(
                                api_url,
                                json=payload,
                                headers=headers,
                                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                                stream=True,
                                headers_timeout=_get_headers_timeout(),
                                event_bus=_event_bus,
                                session_id=session_id,
                            )
                            if response.status_code != 200:
                                return {
                                    "error": f"SSE 断流重试 HTTP {response.status_code}",
                                    "error_type": "stream_stall",
                                    "retryable": False,
                                    "detail": response.text[:500],
                                }
                            continue  # 回到 while 循环，用新 response 重新读流

                    # 从流中重建完整响应
                    choice = {"message": {"role": "assistant", "content": full_content}}
                    if tool_calls_buffer:
                        # 合并流式 tool_calls（OpenAI 流式格式是增量式的）
                        merged = {}
                        for tc in tool_calls_buffer:
                            idx = tc.get("index", 0)
                            if idx not in merged:
                                merged[idx] = {"id": tc.get("id", ""), "type": "function", "function": {"name": "", "arguments": ""}}
                            fn = tc.get("function", {})
                            if "name" in fn:
                                merged[idx]["function"]["name"] = fn["name"]
                            if "arguments" in fn:
                                merged[idx]["function"]["arguments"] += fn["arguments"]
                        choice["message"]["tool_calls"] = list(merged.values())
                    result = {"choices": [choice]}
                    if usage:
                        result["usage"] = usage
                    if _finish_reason:   # 票 PERF-1：finish_reason 透出（调用方/审计可用）
                        result["finish_reason"] = _finish_reason
                    # 票 P：reasoning 独立返回（不混入 content），并留事件
                    if reasoning_buf:
                        result["reasoning"] = reasoning_buf
                        try:
                            _event_bus.write("llm.reasoning", {
                                "session_id": session_id or "",
                                "reasoning_chars": len(reasoning_buf),
                                "content_chars": len(full_content),
                                "duration_ms": int((time.time() - _stream_start) * 1000),
                            })
                        except Exception:
                            pass
                    return result

                # ── 非流式模式 ──
                _body = response.json()
                # ── 票 PERF-1 事故 2：非流式同样检测 finish_reason=length 且正文为空 → 翻倍重试一次 ──
                _fr_ns = _body.get("choices", [{}])[0].get("finish_reason")
                _content_ns = (_body.get("choices", [{}])[0]
                               .get("message", {}).get("content") or "")
                if (_fr_ns == "length" and not _content_ns.strip()
                        and not _length_retried):
                    _length_retried = True
                    _max_tokens = _max_tokens * 2
                    payload["max_tokens"] = _max_tokens
                    _logger.warning(
                        "PERF-1 非流式 length 截断且正文为空 — 翻倍 max_tokens 重试一次: %d→%d, session=%s",
                        _max_tokens // 2, _max_tokens, session_id or "?",
                    )
                    response = _post_with_headers_watchdog(
                        api_url,
                        json=payload,
                        headers=headers,
                        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                        stream=False,
                        headers_timeout=_get_headers_timeout(),
                        event_bus=_event_bus,
                        session_id=session_id,
                    )
                    if response.status_code != 200:
                        return {
                            "error": f"length 重试 HTTP {response.status_code}",
                            "error_type": "http",
                            "retryable": False,
                            "detail": response.text[:500],
                        }
                    continue  # 回到 for attempt 循环（attempt+1，消耗一次重试配额，_length_retried 防循环）
                return _body

            except LLMInterrupted:
                # 票 INT-1：用户中断异常绝不重试、绝不降级为普通错误——
                # 原样上抛给引擎走既有 interrupted 路径（STATE interrupted）。
                raise
            except Exception as e:
                error_type, retryable, message = _classify_error(exception=e)
                if retryable and attempt < MAX_RETRIES:
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    if retry_callback:
                        retry_callback(message, delay)
                    time.sleep(delay)
                    last_error = {"error": message, "error_type": error_type, "retryable": True}
                    continue
                else:
                    detail = ""
                    if response is not None:
                        detail = response.text[:500].strip()
                    detailed_msg = f"{message} — {detail}" if detail else message
                    return {
                        "error": detailed_msg,
                        "error_type": error_type,
                        "retryable": retryable
                    }

        # ── 所有重试耗尽 ──
        return last_error or {"error": "请求失败，已耗尽所有重试次数", "retryable": False}
    return call_llm
