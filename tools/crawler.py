"""
crawler.py - 网页搜索和抓取
"""

import re
import time
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

# ── URL 内容缓存（30 秒内相同 URL 复用） ──
_URL_CACHE: dict[str, tuple[float, str, str]] = {}
_CACHE_TTL = 30


def _cache_get(url: str) -> tuple[str, str] | None:
    entry = _URL_CACHE.get(url)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1], entry[2]
    return None


def _cache_set(url: str, title: str, clean_text: str):
    _URL_CACHE[url] = (time.time(), title, clean_text)
    if len(_URL_CACHE) > 50:
        old = sorted(_URL_CACHE.keys(), key=lambda k: _URL_CACHE[k][0])[:20]
        for k in old:
            _URL_CACHE.pop(k, None)


# ── 搜索 ──

SEARCH_TIMEOUT = 10


def web_search(query: str, max_results: int = 5) -> str:
    """执行网络搜索，返回标题、摘要和链接列表"""

    for attempt in range(2):
        # 主引擎：DuckDuckGo（通过 ddgs 库）
        try:
            from ddgs import DDGS

            results = []
            with DDGS(timeout=SEARCH_TIMEOUT) as ddgs:
                for i, r in enumerate(ddgs.text(query, max_results=max_results), 1):
                    results.append(
                        f"[{i}] {r['title']}\n   摘要: {r['body']}\n   链接: {r['href']}"
                    )
            if results:
                return "\n\n".join(results)
        except ImportError:
            return "请安装 duckduckgo-search: pip install duckduckgo-search"
        except Exception:
            pass  # 走 fallback

        # Fallback: DuckDuckGo Lite HTML 版（无需第三方库）
        fb = _search_lite(query, max_results)
        if fb:
            return fb

        time.sleep(2)

    # 二次尝试后仍无结果
    fb = _search_lite(query, max_results)
    if fb:
        return fb
    return "没有找到相关结果。"


def _search_lite(query: str, max_results: int = 5) -> str | None:
    """DuckDuckGo Lite HTML 搜索（无第三方依赖）"""
    try:
        resp = requests.get(
            "https://lite.duckduckgo.com/lite/",
            params={"q": query},
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for i, link in enumerate(soup.select("a.result-link"), 1):
            if i > max_results:
                break
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if title and href:
                results.append(f"[{i}] {title}\n   链接: {href}")
        return "\n\n".join(results) if results else None
    except Exception:
        return None


# ── 网页抓取 ──

WEB_FETCH_MAX_CHARS = 8000


def _fetch_page(url: str) -> tuple[str | None, str | None]:
    """内部：获取网页并清洗，返回 (title, clean_text)。失败时 (error_msg, None)。"""
    cached = _cache_get(url)
    if cached:
        return cached[0], cached[1]

    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                if attempt == 0:
                    time.sleep(1)
                    continue
                msg = f"无法访问: {url}（状态码: {resp.status_code}）"
                _cache_set(url, msg, "")
                return msg, None

            soup = BeautifulSoup(resp.text, "html.parser")
            title_tag = soup.find("title")
            title = title_tag.get_text().strip() if title_tag else "无标题"

            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)

            clean = re.sub(r"\s+", "", text)
            if len(clean) < 100:
                msg = f"页面无有效内容: {url}"
                _cache_set(url, msg, "")
                return msg, None

            result = _clean_text(text)
            _cache_set(url, title, result)
            return title, result

        except requests.exceptions.Timeout:
            if attempt == 0:
                time.sleep(1)
                continue
            return f"访问超时: {url}", None
        except Exception as e:
            if attempt == 0:
                time.sleep(1)
                continue
            return f"获取失败: {str(e)[:100]}", None

    return f"多次尝试失败: {url}", None


def web_fetch(url: str) -> str:
    """获取网页文本内容"""
    title, text = _fetch_page(url)
    if text is None:
        return title  # 错误信息
    return f"📄 {url}\n\n{text}"


def web_fetch_markdown(url: str) -> str:
    """获取网页并转为 Markdown 格式"""
    title, text = _fetch_page(url)
    if text is None:
        return title  # 错误信息
    md = f"# {title}\n\n" if title else ""
    md += text
    return md


def _extract_domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", url)
    return match.group(1) if match else url


def _clean_text(text: str, max_len: int = WEB_FETCH_MAX_CHARS) -> str:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    text = "\n".join(lines)
    if len(text) > max_len:
        text = text[:max_len] + "\n...(内容截断)"
    return text


def register(reg):
    pass
