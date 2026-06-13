"""智能分类 - 先分析给方案，确认后再移动"""

import re

TOOL_NAME = "classify"

CATEGORY_RULES = {
    "编程/技术": {
        "keywords": ["python", "代码", "编程", "装饰器", "函数", "算法", "数据结构", "api"],
        "folder": "03_Resources/编程"
    },
    "数学": {
        "keywords": ["数学", "微积分", "线性代数", "概率", "统计", "公式", "定理", "矩阵"],
        "folder": "02_Areas/数学"
    },
    "化学": {
        "keywords": ["化学", "反应", "分子", "原子", "有机", "无机", "酸碱"],
        "folder": "02_Areas/化学"
    },
    "AI/机器学习": {
        "keywords": ["ai", "人工智能", "机器学习", "深度学习", "神经网络", "gpt", "模型"],
        "folder": "03_Resources/AI"
    },
    "文学": {
        "keywords": ["文学", "小说", "诗歌", "散文", "作家", "阅读", "书评", "litcharts"],
        "folder": "02_Areas/文学"
    },
}


def analyze(filename: str, content: str = None) -> str:
    """分析笔记应该放哪里"""
    from tools.read_obsidian import execute as read_note
    
    if content is None:
        content = read_note(filename)
        if content.startswith("❌"):
            return f"❌ 无法读取文件: {filename}"
    
    content_lower = content.lower()
    
    suggestions = []
    for category, rule in CATEGORY_RULES.items():
        matched = [kw for kw in rule["keywords"] if kw in content_lower]
        if matched:
            suggestions.append({
                "category": category,
                "folder": rule["folder"],
                "matched": matched[:3],
                "score": len(matched)
            })
    
    if not suggestions:
        return f"⚠️ 无法确定《{filename}》的分类，请手动处理。"
    
    suggestions.sort(key=lambda x: x["score"], reverse=True)
    best = suggestions[0]
    
    result = f"📝 《{filename}》\n"
    result += f"🏷️ 建议分类: {best['category']}\n"
    result += f"📁 目标文件夹: {best['folder']}\n"
    result += f"🔑 匹配: {', '.join(best['matched'])}\n"
    result += f"\n❓ 确认移动？回复「确认」"
    
    return result


def confirm_move(filename: str, folder: str = None) -> str:
    """确认移动"""
    from tools.move_note import execute as move_note
    
    if folder is None:
        # 从分析结果中提取文件夹
        analysis = analyze(filename)
        import re
        match = re.search(r'目标文件夹: (\S+)', analysis)
        if match:
            folder = match.group(1)
        else:
            return "❌ 无法确定目标文件夹"
    
    base_name = filename.split("/")[-1]
    destination = f"{folder}/{base_name}"
    result = move_note(filename, destination)
    
    if "✅" in result:
        return f"✅ 已将《{filename}》移动到 {folder}"
    return f"❌ 移动失败: {result}"


_check = lambda: bool(__import__('os').environ.get('OBSIDIAN_VAULT', ''))

def register(reg):
    reg("classify_analyze", analyze, {
        "type": "function",
        "function": {
            "name": "classify_analyze",
            "description": "【必须使用】当用户问'应该放哪里'、'放哪个文件夹'、'归类到哪里'时，必须调用此工具。不要自己分析。",
            "parameters": {"type": "object", "properties": {
                "filename": {"type": "string"},
                "content": {"type": "string"}
            }, "required": ["filename"]}
        }
    }, check_fn=_check)
    
    reg("classify_confirm", confirm_move, {
        "type": "function",
        "function": {
            "name": "classify_confirm",
            "description": "用户确认后移动笔记",
            "parameters": {"type": "object", "properties": {
                "filename": {"type": "string"},
                "folder": {"type": "string"}
            }, "required": ["filename"]}
        }
    }, check_fn=_check)
