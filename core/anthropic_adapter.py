"""Anthropic Messages API adapter (GitHub #9).

`llm_caller` and the engine speak OpenAI `chat/completions` + `tool_calls`.
Direct Anthropic (`/v1/messages`) does not. This module is the explicit
adapter: OpenAI-shaped request/response/stream in, native Messages API on
the wire, OpenAI-shaped result back out so engine/tool_runner stay unchanged.

Selection (see `uses_anthropic_protocol`):
  - provider registry `protocol == "anthropic_messages"` (anthropic)
  - OR URL is a native `/v1/messages` endpoint
  - NEVER when the URL is OpenAI-compatible `/chat/completions`
    (OpenRouter and API_BASE_URL overrides must not regress)

Omitted `protocol` defaults to `openai_chat` (conservative, matches runtime).
"""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_ANTHROPIC = "anthropic_messages"
PROTOCOL_OPENAI = "openai_chat"
ANTHROPIC_VERSION = "2023-06-01"

# Sentinel: Anthropic SSE `message_stop` → treat as OpenAI `data: [DONE]`
ANTHROPIC_STREAM_DONE = object()

_STOP_REASON_MAP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "pause_turn": "stop",
}


def uses_anthropic_protocol(provider_proto: dict | None = None, api_url: str = "") -> bool:
    """Whether this caller should speak native Anthropic Messages API.

    `/chat/completions` in the URL always wins (OpenRouter, proxies, overrides).
    Otherwise honor `protocol=anthropic_messages`, or fall back to a native
    `/v1/messages` URL so callers that omit provider_proto still work.
    """
    url = api_url or ""
    if "/chat/completions" in url:
        return False
    proto = (provider_proto or {}).get("protocol") or PROTOCOL_OPENAI
    if proto == PROTOCOL_ANTHROPIC:
        return True
    return "/v1/messages" in url


def build_anthropic_headers(api_key: str = "") -> dict:
    """Anthropic uses `x-api-key` + `anthropic-version`, not Bearer."""
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
    }
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def to_anthropic_payload(openai_payload: dict) -> dict:
    """Convert an OpenAI chat/completions payload to Anthropic Messages body."""
    system, messages = _to_anthropic_messages(openai_payload.get("messages") or [])
    body: dict[str, Any] = {
        "model": openai_payload.get("model"),
        "messages": messages,
        "max_tokens": openai_payload.get("max_tokens") or 8192,
    }
    if system:
        body["system"] = system
    if "temperature" in openai_payload and openai_payload["temperature"] is not None:
        body["temperature"] = openai_payload["temperature"]
    if openai_payload.get("stream"):
        body["stream"] = True
    tools = openai_payload.get("tools")
    if tools:
        body["tools"] = to_anthropic_tools(tools)
        tc = openai_payload.get("tool_choice")
        if tc is not None:
            body["tool_choice"] = to_anthropic_tool_choice(tc)
    thinking = openai_payload.get("thinking")
    if thinking:
        body["thinking"] = thinking
    return body


def to_anthropic_tools(openai_tools: list) -> list:
    """OpenAI `{type:function, function:{name,parameters}}` → Anthropic tools."""
    out = []
    for t in openai_tools or []:
        if not isinstance(t, dict):
            continue
        if t.get("name") and "input_schema" in t:
            out.append(t)
            continue
        fn = t.get("function") if isinstance(t.get("function"), dict) else t
        name = fn.get("name") if isinstance(fn, dict) else None
        if not name:
            continue
        params = fn.get("parameters") or {"type": "object", "properties": {}}
        out.append({
            "name": name,
            "description": fn.get("description") or "",
            "input_schema": params,
        })
    return out


def to_anthropic_tool_choice(tool_choice) -> dict:
    if tool_choice is None or tool_choice == "auto":
        return {"type": "auto"}
    if tool_choice == "none":
        return {"type": "none"}
    if tool_choice == "required":
        return {"type": "any"}
    if isinstance(tool_choice, dict):
        name = (
            (tool_choice.get("function") or {}).get("name")
            if isinstance(tool_choice.get("function"), dict)
            else None
        ) or tool_choice.get("name")
        if name:
            return {"type": "tool", "name": name}
        if tool_choice.get("type") in ("auto", "none", "any", "tool"):
            return tool_choice
    return {"type": "auto"}


def from_anthropic_response(body: dict) -> dict:
    """Convert a non-stream Anthropic message to OpenAI `choices` shape."""
    if not isinstance(body, dict):
        return body
    if "choices" in body:
        return body
    if body.get("type") == "error":
        err = body.get("error") or {}
        msg = err.get("message") or str(err) or "anthropic error"
        return {
            "error": msg,
            "error_type": "bad_request",
            "retryable": False,
            "detail": json.dumps(body, ensure_ascii=False),
        }
    content_blocks = body.get("content") or []
    if isinstance(content_blocks, str):
        content_blocks = [{"type": "text", "text": content_blocks}]
    texts: list[str] = []
    thinking: list[str] = []
    tool_calls: list[dict] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            texts.append(block.get("text") or "")
        elif btype == "thinking":
            thinking.append(block.get("thinking") or "")
        elif btype == "tool_use":
            tool_calls.append(_tool_use_to_openai(block))
    content = "".join(texts)
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    if thinking:
        message["thinking"] = "".join(thinking)
    finish = _STOP_REASON_MAP.get(body.get("stop_reason"), body.get("stop_reason") or "stop")
    usage = _openai_usage(body.get("usage") or {})
    result: dict[str, Any] = {
        "id": body.get("id"),
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish,
        }],
        "finish_reason": finish,
        "usage": usage,
    }
    if thinking:
        result["reasoning"] = "".join(thinking)
    return result


class AnthropicStreamState:
    """Mutable state for mapping Anthropic SSE events to OpenAI chunks."""

    def __init__(self):
        self.blocks: dict[int, dict] = {}
        self.input_tokens = 0
        self.output_tokens = 0


def anthropic_event_to_openai_chunk(event: dict, state: AnthropicStreamState):
    """Map one Anthropic SSE JSON event to an OpenAI-style chunk.

    Returns:
      - dict: OpenAI SSE payload (`choices` / `usage`)
      - ANTHROPIC_STREAM_DONE: `message_stop` (caller should treat as [DONE])
      - None: ignore (ping, block_stop, unknown)
    """
    if not isinstance(event, dict):
        return None
    etype = event.get("type")
    if etype == "message_start":
        msg = event.get("message") or {}
        usage = msg.get("usage") or {}
        state.input_tokens = int(usage.get("input_tokens") or 0)
        if state.input_tokens:
            return {"usage": _openai_usage(usage, output_tokens=0)}
        return None
    if etype == "content_block_start":
        idx = int(event.get("index") or 0)
        block = event.get("content_block") or {}
        state.blocks[idx] = block
        if block.get("type") == "tool_use":
            return {
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "index": idx,
                            "id": block.get("id") or "",
                            "type": "function",
                            "function": {
                                "name": block.get("name") or "",
                                "arguments": "",
                            },
                        }]
                    }
                }]
            }
        return None
    if etype == "content_block_delta":
        idx = int(event.get("index") or 0)
        delta = event.get("delta") or {}
        dtype = delta.get("type")
        if dtype == "text_delta":
            text = delta.get("text") or ""
            if not text:
                return None
            return {"choices": [{"delta": {"content": text}}]}
        if dtype == "thinking_delta":
            thought = delta.get("thinking") or ""
            if not thought:
                return None
            # Anthropic registry field is `thinking`; also fill reasoning_content
            # so callers that only look at the DeepSeek-shaped name still work.
            return {"choices": [{"delta": {
                "thinking": thought,
                "reasoning_content": thought,
            }}]}
        if dtype == "input_json_delta":
            partial = delta.get("partial_json") or ""
            return {
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "index": idx,
                            "function": {"arguments": partial},
                        }]
                    }
                }]
            }
        return None
    if etype == "message_delta":
        d = event.get("delta") or {}
        usage = event.get("usage") or {}
        chunk: dict[str, Any] = {"choices": [{"delta": {}}]}
        stop = d.get("stop_reason")
        if stop:
            mapped = _STOP_REASON_MAP.get(stop, stop)
            chunk["choices"][0]["delta"]["finish_reason"] = mapped
            chunk["choices"][0]["finish_reason"] = mapped
        if usage:
            if usage.get("output_tokens") is not None:
                state.output_tokens = int(usage.get("output_tokens") or 0)
            chunk["usage"] = _openai_usage(
                {"input_tokens": state.input_tokens, "output_tokens": state.output_tokens}
            )
        return chunk
    if etype == "message_stop":
        return ANTHROPIC_STREAM_DONE
    if etype == "error":
        err = event.get("error") or {}
        msg = err.get("message") or str(err) or "anthropic stream error"
        raise ValueError(msg)
    # ping / content_block_stop / unknown
    return None


def _openai_usage(usage: dict, output_tokens: int | None = None) -> dict:
    prompt = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    completion = (
        output_tokens
        if output_tokens is not None
        else int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    )
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _tool_use_to_openai(block: dict) -> dict:
    args = block.get("input") if "input" in block else {}
    if isinstance(args, str):
        arguments = args
    else:
        try:
            arguments = json.dumps(args or {}, ensure_ascii=False)
        except (TypeError, ValueError):
            arguments = "{}"
    return {
        "id": block.get("id") or "",
        "type": "function",
        "function": {
            "name": block.get("name") or "",
            "arguments": arguments,
        },
    }


def _to_anthropic_messages(openai_messages: list) -> tuple[str | None, list]:
    """Split system prompts out; convert roles/content/tool_calls."""
    system_parts: list[str] = []
    converted: list[dict] = []
    for msg in openai_messages or []:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "system":
            system_parts.extend(_flatten_text(msg.get("content")))
            continue
        if role == "tool":
            tool_result = {
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id") or "",
                "content": _tool_result_content(msg.get("content")),
            }
            if converted and converted[-1]["role"] == "user" and _is_tool_result_user(converted[-1]):
                converted[-1]["content"].append(tool_result)
            else:
                converted.append({"role": "user", "content": [tool_result]})
            continue
        if role == "assistant":
            blocks = _convert_content(msg.get("content"))
            blocks = [b for b in blocks if not (b.get("type") == "text" and not (b.get("text") or ""))]
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    blocks.append(_openai_tool_call_to_tool_use(tc))
            if not blocks:
                continue
            converted.append({"role": "assistant", "content": blocks})
            continue
        # user (and any unknown role treated as user text)
        blocks = _convert_content(msg.get("content"))
        if not blocks:
            continue
        converted.append({"role": "user", "content": blocks})

    merged = _merge_consecutive_roles(converted)
    if merged and merged[0]["role"] != "user":
        merged.insert(0, {"role": "user", "content": [{"type": "text", "text": "(continue)"}]})
    system = "\n\n".join(p for p in system_parts if p) or None
    return system, merged


def _openai_tool_call_to_tool_use(tc: dict) -> dict:
    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
    args = fn.get("arguments") if fn else tc.get("arguments")
    if isinstance(args, dict):
        input_obj = args
    elif isinstance(args, str) and args.strip():
        try:
            input_obj = json.loads(args)
        except json.JSONDecodeError:
            input_obj = {}
    else:
        input_obj = {}
    if not isinstance(input_obj, dict):
        input_obj = {}
    return {
        "type": "tool_use",
        "id": tc.get("id") or "",
        "name": (fn.get("name") if fn else None) or tc.get("name") or "",
        "input": input_obj,
    }


def _convert_content(content) -> list:
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                if part:
                    out.append({"type": "text", "text": part})
                continue
            if not isinstance(part, dict):
                out.append({"type": "text", "text": str(part)})
                continue
            ptype = part.get("type")
            if ptype == "text":
                text = part.get("text") or ""
                if text:
                    out.append({"type": "text", "text": text})
            elif ptype == "image_url":
                converted = _image_url_to_anthropic(part)
                if converted:
                    out.append(converted)
            elif ptype in ("image", "tool_use", "tool_result", "thinking"):
                out.append(part)
            else:
                text = part.get("text") or part.get("content")
                if text:
                    out.append({"type": "text", "text": str(text)})
        return out
    return [{"type": "text", "text": str(content)}]


def _image_url_to_anthropic(part: dict) -> dict | None:
    image = part.get("image_url")
    url = ""
    if isinstance(image, dict):
        url = image.get("url") or ""
    elif isinstance(image, str):
        url = image
    url = url or part.get("url") or ""
    if not url:
        return None
    if url.startswith("data:"):
        header, _, data = url.partition(",")
        media = "image/png"
        if header.startswith("data:"):
            media = header[5:].split(";")[0] or "image/png"
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media, "data": data},
        }
    if url.startswith("http://") or url.startswith("https://"):
        return {"type": "image", "source": {"type": "url", "url": url}}
    return None


def _flatten_text(content) -> list[str]:
    if content is None:
        return []
    if isinstance(content, str):
        return [content] if content.strip() else []
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        return parts
    s = str(content)
    return [s] if s.strip() else []


def _tool_result_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_flatten_text(content))
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _is_tool_result_user(msg: dict) -> bool:
    content = msg.get("content")
    if not isinstance(content, list) or not content:
        return False
    return all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def _merge_consecutive_roles(messages: list) -> list:
    merged: list[dict] = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            prev = merged[-1]["content"]
            extra = msg["content"]
            if not isinstance(prev, list):
                prev = _convert_content(prev)
                merged[-1]["content"] = prev
            if not isinstance(extra, list):
                extra = _convert_content(extra)
            prev.extend(extra)
        else:
            merged.append({
                "role": msg["role"],
                "content": list(msg["content"]) if isinstance(msg["content"], list) else msg["content"],
            })
    return merged
