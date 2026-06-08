"""读取本地文件内容"""

import os
from pathlib import Path

TOOL_NAME = "read_local_file"

def execute(filepath: str, max_chars: int = 5000) -> str:
    """读取本地文件内容"""
    path = Path(filepath).expanduser()
    
    if not path.exists():
        return f"❌ 文件不存在: {filepath}"
    
    if path.is_dir():
        return f"❌ 路径是目录，不是文件: {filepath}"
    
    # 根据扩展名选择读取方式
    ext = path.suffix.lower()
    
    try:
        if ext == '.pdf':
            # PDF 需要额外处理
            return "❌ PDF 读取需要安装 pypdf: pip install pypdf"
        elif ext in ['.md', '.txt', '.py', '.json', '.yaml', '.yml']:
            content = path.read_text(encoding='utf-8')
        else:
            # 尝试作为文本读取
            content = path.read_text(encoding='utf-8', errors='ignore')
        
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n... (内容已截断，共 {len(content)} 字符)"
        
        return f"📄 {filepath}\n\n{content}"
    except Exception as e:
        return f"❌ 读取失败: {str(e)}"

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "读取本地文件内容。支持 .md, .txt, .py, .json, .yaml 等格式。适用场景：用户要求'读取某个文件'、'看看这个文件内容'。",
        "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "max_chars": {"type": "integer"}}, "required": ["filepath"]}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
