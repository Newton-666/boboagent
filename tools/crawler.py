"""
crawler.py - 网页搜索和抓取（稳定版）
"""

import re
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from config import TOOL_TIMEOUT

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

def _extract_domain(url):
    match = re.search(r'https?://([^/]+)', url)
    return match.group(1) if match else url

def _is_empty_content(text, min_length=100):
    clean = re.sub(r'\s+', '', text)
    return len(clean) < min_length

def _clean_text(text, max_len=3000):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    text = '\n'.join(lines)
    if len(text) > max_len:
        text = text[:max_len] + "\n...(内容截断)"
    return text

def web_search(query: str) -> str:
    """执行网络搜索"""
    original_query = query
    
    # 搜索词优化
    weather_keywords = ['天气', 'weather', '气温', 'temperature', '预报', 'forecast']
    if any(word in query.lower() for word in weather_keywords):
        cities = {
            '上海': 'Shanghai', '北京': 'Beijing', '深圳': 'Shenzhen',
            '广州': 'Guangzhou', '杭州': 'Hangzhou', '南京': 'Nanjing',
            '成都': 'Chengdu', '重庆': 'Chongqing', '武汉': 'Wuhan',
        }
        for cn, en in cities.items():
            if cn in query:
                location = en
                date_str = datetime.now().strftime("%B %d %Y")
                query = f"{location} weather {date_str}"
                print(f"  🔍 搜索词优化: '{original_query}' -> '{query}'")
                break
    
    for attempt in range(3):
        try:
            from ddgs import DDGS
            results = []
            with DDGS() as ddgs:
                for i, r in enumerate(ddgs.text(query, max_results=5), 1):
                    results.append(f"[{i}] {r['title']}\n   摘要: {r['body']}\n   链接: {r['href']}")
            if results:
                return "\n\n".join(results)
            time.sleep(2)
        except ImportError:
            return "❌ 请安装 duckduckgo-search: pip install duckduckgo-search"
        except Exception as e:
            if attempt == 2:
                return f"❌ 搜索失败: {str(e)}"
            time.sleep(3)
    return "没有找到相关结果。"

def web_fetch(url: str) -> str:
    """获取网页内容"""
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TOOL_TIMEOUT)
            if resp.status_code != 200:
                if attempt == 0:
                    time.sleep(1)
                    continue
                return f"❌ 无法访问: {url} (状态码: {resp.status_code})"
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                tag.decompose()
            text = soup.get_text(separator='\n', strip=True)
            
            if _is_empty_content(text):
                return f"❌ 页面无有效内容: {url}"
            
            return f"📄 {url}\n\n{_clean_text(text)}"
            
        except requests.exceptions.Timeout:
            if attempt == 0:
                time.sleep(1)
                continue
            return f"❌ 访问超时: {url}"
        except Exception as e:
            if attempt == 0:
                time.sleep(1)
                continue
            return f"❌ 获取失败: {str(e)[:100]}"
    
    return f"❌ 多次尝试失败: {url}"



def register(reg):
    pass
