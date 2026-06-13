"""
core/llm_caller.py - 修复版
"""

import requests
import json
import time


def _classify_error(exception: Exception = None, status_code: int = None) -> tuple:
    """
    对 API 调用错误进行分类，判断是否可重试。
    
    Args:
        exception:  请求抛出的异常对象，如 ConnectionError、Timeout 等
        status_code: HTTP 响应状态码，如 401、429、500 等
        
    Returns:
        tuple: (error_type: str, retryable: bool, message: str)
            - error_type: 错误类型标识
                "timeout"       — 连接超时或读取超时
                "rate_limit"    — 限流 (429)
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
        if status_code == 401:
            return ("auth_error", False, "认证失败，请检查 API Key 是否正确")
        
        if status_code == 403:
            return ("auth_error", False, "权限不足，API Key 无权限访问此资源")
        
        if status_code == 429:
            return ("rate_limit", True, "请求过于频繁，已被限流")
        
        if 500 <= status_code < 600:
            return ("server_error", True, f"服务暂不可用 (HTTP {status_code})")
        
        if 400 <= status_code < 500:
            return ("bad_request", False, f"请求错误 (HTTP {status_code})")
        
        return ("unknown", False, f"未知状态码: {status_code}")
    
    return ("unknown", False, "未知错误")


# 超时配置（秒）
CONNECT_TIMEOUT = 10   # 建立连接的超时时间
READ_TIMEOUT = 50      # 接收响应的超时时间

# 重试配置
MAX_RETRIES = 2        # 最大重试次数（初始请求 + 2 次重试 = 共 3 次尝试）
RETRY_DELAY_BASE = 1   # 基础等待时间（秒），指数退避


def create_llm_caller(api_key: str, api_url: str, model_name: str, tools_schema: list = None):
    def call_llm(messages, use_tools=True, stream_callback=None, retry_callback=None, tools_override=None):
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 8192,
        }
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

        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = requests.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                    stream=bool(stream_callback),
                )

                # ── HTTP 状态码检查 ──
                if response.status_code != 200:
                    error_type, retryable, message = _classify_error(
                        status_code=response.status_code
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
                    full_content = ""
                    tool_calls_buffer = []
                    usage = {}
                    for line in response.iter_lines():
                        if not line:
                            continue
                        line = line.decode("utf-8")
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        # 捕获 usage（部分 API 在流结束前返回）
                        if "usage" in chunk:
                            usage = chunk["usage"]
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_content += content
                            stream_callback(content)
                        tc = delta.get("tool_calls")
                        if tc:
                            tool_calls_buffer.extend(tc)

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
                    return result

                # ── 非流式模式 ──
                return response.json()

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
                    return {
                        "error": message,
                        "error_type": error_type,
                        "retryable": retryable
                    }

        # ── 所有重试耗尽 ──
        return last_error or {"error": "请求失败，已耗尽所有重试次数", "retryable": False}
    return call_llm
