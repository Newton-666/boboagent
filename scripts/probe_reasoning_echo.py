# -*- coding: utf-8 -*-
"""REASONING-ECHO 实弹验证：DeepSeek 是否接受 reasoning_content:"" 的空串回传。

场景（压缩路径）：两个 user 之间夹工具轮，中间 assistant 带 tool_calls 但
thinking 缺失（压缩归档剔除）→ 发送侧补 reasoning_content:""。
结论写入收工报告；若拒绝（400）→ 压缩路径改跳过。

用法：.venv/bin/python scripts/probe_reasoning_echo.py
"""
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions"
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")


def _probe(label, messages):
    body = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 16,
        "stream": False,
    }
    t0 = time.time()
    try:
        r = requests.post(URL, json=body, timeout=60, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        })
        if r.status_code == 200:
            data = r.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            usage = data.get("usage", {})
            print(f"[{label}] ACCEPT ({time.time()-t0:.1f}s) content={msg.get('content','')[:30]!r} "
                  f"usage={usage.get('prompt_tokens')}/{usage.get('completion_tokens')} "
                  f"cache_hit={usage.get('prompt_cache_hit_tokens')}")
            return True
        print(f"[{label}] REJECT ({time.time()-t0:.1f}s) HTTP {r.status_code}: {r.text[:300]}")
        return False
    except Exception as e:
        print(f"[{label}] ERROR: {e}")
        return False


if __name__ == "__main__":
    if not API_KEY:
        print("无 DEEPSEEK_API_KEY，跳过实弹（改走离线定案）")
        sys.exit(0)

    # 场景 A：带 thinking 的 assistant（有值回传）——对照组应接受
    a = _probe("A 有值回传", [
        {"role": "user", "content": "1+1=？"},
        {"role": "assistant", "content": "", "reasoning_content": "简单加法"},
        {"role": "user", "content": "2"},
    ])

    # 场景 B：压缩路径——assistant 带 tool_calls 但 reasoning_content:""（空串）
    b = _probe("B 空串+tool_calls", [
        {"role": "user", "content": "读文件并总结"},
        {"role": "assistant", "content": None,
         "reasoning_content": "",
         "tool_calls": [{"id": "call_p1", "type": "function",
                         "function": {"name": "read_file", "arguments": "{\"path\": \"x\"}"}}]},
        {"role": "tool", "tool_call_id": "call_p1", "name": "read_file",
         "content": "file x content"},
        {"role": "user", "content": "继续"},
    ])

    # 场景 C：无 tool_calls 纯文本 assistant 带 reasoning_content:""（对照组边界）
    c = _probe("C 空串无tool_calls", [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，我是 Bobo", "reasoning_content": ""},
        {"role": "user", "content": "再见"},
    ])

    # 场景 D：对照组——tool_calls 轮完全不带 reasoning_content（修复前行为）。
    # 注意：D 离线构造也会被接受（服务端无法感知"模型是否输出过 thinking"），
    # 400 只在模型真实输出过 reasoning_content 且后续未回传时触发（服务端
    # 有状态记忆，票背景 17:23 实弹已实锤）。D 接受不推翻修复必要性——
    # bobo 真实施工时 thinking 模式开启，服务端记得每个 tool_calls 轮，
    # 不回传即 400。本探针结论：空串回传被接受，压缩路径补空串可行。
    d = _probe("D 无字段(tool_calls)", [
        {"role": "user", "content": "读文件并总结"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "call_p2", "type": "function",
                         "function": {"name": "read_file", "arguments": "{\"path\": \"x\"}"}}]},
        {"role": "tool", "tool_call_id": "call_p2", "name": "read_file",
         "content": "file x content"},
        {"role": "user", "content": "继续"},
    ])

    print("\n=== 结论 ===")
    print(f"A 有值回传: {'接受' if a else '拒绝'}")
    print(f"B 空串+tool_calls: {'接受' if b else '拒绝'}")
    print(f"C 空串无tool_calls: {'接受' if c else '拒绝'}")
    print(f"D 无字段(tool_calls): {'接受' if d else '拒绝（修复必要性实锤）'}")
    verdict = "压缩路径统一补空串" if (a and b) else ("压缩路径跳过不补" if a else "发送侧有值回传本身被拒，需复查")
    print(f"定案: {verdict}")
