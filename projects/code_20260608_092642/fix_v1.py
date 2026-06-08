def calculate_average(numbers):
    total = sum(numbers)
    count = len(numbers)
    return total / count

result = calculate_average([1, 2, 3, 4, 5])
print(f'平均值: {result}')