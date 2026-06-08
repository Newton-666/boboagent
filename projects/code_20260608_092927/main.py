# 测试3：多文件项目能力 — 写一个简单的数据处理脚本
import csv
import json
from pathlib import Path

# 生成示例数据
data = [
    {"name": "Alice", "score": 95},
    {"name": "Bob", "score": 87},
    {"name": "Charlie", "score": 92},
    {"name": "Diana", "score": 78},
]

# 保存为 CSV
csv_path = "/tmp/scores.csv"
with open(csv_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["name", "score"])
    writer.writeheader()
    writer.writerows(data)

# 读取并分析
with open(csv_path, 'r') as f:
    reader = csv.DictReader(f)
    scores = [int(row["score"]) for row in reader]

print(f"学生人数: {len(scores)}")
print(f"平均分: {sum(scores)/len(scores):.1f}")
print(f"最高分: {max(scores)}")
print(f"最低分: {min(scores)}")
print(f"\n数据已保存到: {csv_path}")
