#!/usr/bin/env python3
"""
复杂渲染测试 - 一次性测试所有渲染功能
"""

import sys

from tools.render import render_table, render_markdown

print("=" * 70)
print("复杂渲染测试")
print("=" * 70)

# 1. 大表格
print("\n1. 大表格 (5x5):")
print("-" * 40)
big_table = """| 序号 | 姓名 | 年龄 | 城市 | 职业 |
|------|------|------|------|------|
| 1 | 张三 | 25 | 北京 | 工程师 |
| 2 | 李四 | 30 | 上海 | 设计师 |
| 3 | 王五 | 28 | 深圳 | 产品经理 |
| 4 | 赵六 | 35 | 广州 | 架构师 |
| 5 | 钱七 | 32 | 杭州 | 运营 |"""
print(render_table(big_table))

# 2. 混合格式（粗体 + 斜体 + 代码）
print("\n2. 混合格式:")
print("-" * 40)
mixed = """这是 **粗体文字**，这是 *斜体文字*，这是 `代码块`。

**重要提示**：请确保 `config.py` 中的 `API_KEY` 已正确配置。

*注意*：修改配置后需要 **重启程序** 才能生效。"""
print(render_markdown(mixed))

# 3. 数学公式集
print("\n3. 数学公式集:")
print("-" * 40)
math_formulas = """### 常用公式

1. 欧拉公式：$e^{i\\pi} + 1 = 0$

2. 二次方程求根公式：$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$

3. 正态分布：$f(x) = \\frac{1}{\\sigma\\sqrt{2\\pi}} e^{-\\frac{(x-\\mu)^2}{2\\sigma^2}}$

4. 傅里叶变换：$F(\\omega) = \\int_{-\\infty}^{\\infty} f(t) e^{-i\\omega t} dt$"""
print(render_markdown(math_formulas))

# 4. 嵌套结构（表格 + 列表）
print("\n4. 表格内嵌套列表:")
print("-" * 40)
nested = """| 功能 | 说明 | 示例 |
|------|------|------|
| 搜索 | 使用 `web_search` 工具 | `web_search(query="Python")` |
| 笔记 | 使用 `write_obsidian` 工具 | `write_obsidian(filename="test.md", content="内容")` |
| 邮件 | 使用 `read_recent` 工具 | `read_recent(limit=5)` |"""
print(render_table(nested))

print("\n" + "=" * 70)
print("测试完成")
print("=" * 70)
