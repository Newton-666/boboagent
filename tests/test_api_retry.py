#!/usr/bin/env python3
"""
测试 13: API 错误重试
"""

import sys
import os
import time


from core.llm_caller import create_llm_caller
from config import API_KEY, API_BASE_URL, API_MODEL_NAME
from tools import TOOLS_SCHEMA

# 创建一个会出错的请求（故意传错误格式）
def test_bad_request():
    print("测试: 错误请求")
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    
    # 故意传空消息
    response = llm([], use_tools=True)
    if "error" in response:
        print(f"  ✅ 正确返回错误: {response.get('error')}")
        return True
    else:
        print(f"  ❌ 应该返回错误")
        return False

# 测试正常请求
def test_good_request():
    print("测试: 正常请求")
    llm = create_llm_caller(API_KEY, API_BASE_URL, API_MODEL_NAME, TOOLS_SCHEMA)
    
    response = llm([{"role": "user", "content": "Hi"}], use_tools=False)
    if "error" in response:
        print(f"  ❌ 失败: {response}")
        return False
    else:
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"  ✅ 成功: {content[:50]}...")
        return True

print("API 错误处理测试")
print("=" * 40)
r1 = test_bad_request()
r2 = test_good_request()

if r1 and r2:
    print("\n✅ 测试通过")
else:
    print("\n❌ 测试失败")
