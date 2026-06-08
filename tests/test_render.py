#!/usr/bin/env python3
"""
测试独立渲染工具
"""

import sys

from tools.render import execute as render

print("=" * 60)
print("测试独立渲染工具")
print("=" * 60)

# 1. 测试纯文本
print("\n1. 纯文本 (流式):")
render({
    "type": "text",
    "content": "这是一段普通文本，没有任何格式。",
    "stream": True
})

# 2. 测试粗体
print("\n\n2. 粗体渲染:")
render({
    "type": "markdown",
    "content": "这是 **粗体文字** 和 *斜体文字* 以及 `代码块`。",
    "stream": False
})

# 3. 测试表格
print("\n3. 表格渲染:")
table_content = """| 姓名 | 年龄 | 城市 |
|------|------|------|
| 张三 | 25 | 北京 |
| 李四 | 30 | 上海 |
| 王五 | 28 | 深圳 |"""
render({
    "type": "table",
    "content": table_content,
    "stream": False
})

# 4. 测试错误
print("\n4. 错误渲染:")
render({
    "type": "error",
    "content": "这是一个错误信息",
    "stream": False
})

# 5. 测试数学公式（LaTeX）
print("\n5. 数学公式（需要终端支持）:")
render({
    "type": "markdown",
    "content": "欧拉公式：$e^{i\\pi} + 1 = 0$",
    "stream": False
})

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
