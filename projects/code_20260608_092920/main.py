# 测试2：有 bug 的代码（不传 llm_caller，看错误检测是否正常）
def divide(a, b):
    return a / b

print(divide(10, 0))
