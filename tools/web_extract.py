"""抓取网页并转换为 Markdown"""

import re
from bs4 import BeautifulSoup
import requests

TOOL_NAME = "web_extract"

def execute(url: str) -> str:
    """抓取网页并转换为 Markdown 格式"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 移除脚本和样式
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        # 提取标题
        title = soup.find('title')
        title_text = title.get_text().strip() if title else "无标题"
        
        # 提取正文
        main = soup.find('article') or soup.find('main') or soup.find('body')
        text = main.get_text(separator='\n', strip=True) if main else soup.get_text(separator='\n', strip=True)
        
        # 简单转换为 Markdown
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        markdown = f"# {title_text}\n\n"
        markdown += "\n\n".join(lines[:200])  # 限制长度
        
        if len(lines) > 200:
            markdown += f"\n\n... (内容已截断，共 {len(lines)} 行)"
        
        return markdown
    except Exception as e:
        return f"❌ 抓取失败: {str(e)}"

TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "抓取网页内容并转换为 Markdown 格式，便于保存到笔记。适用场景：用户要求'把这个网页保存到笔记'、'提取文章内容'。",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
