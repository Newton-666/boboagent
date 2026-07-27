"""内部模块：URL 安全检查，防止 SSRF 攻击。不对外暴露为工具。"""

import ipaddress
from urllib.parse import urlparse

BLOCKED_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("::1/128"),
]


def is_url_safe(url: str) -> tuple:
    """返回 (is_safe: bool, reason: str)。

    主机名是域名（非 IP 地址）→ 安全。
    主机名是 IP 地址但在内网段 → 危险。
    """
    if not url or not isinstance(url, str):
        return False, "URL 为空"
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False, "无法解析主机名"
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return True, ""  # 域名，安全
        for net in BLOCKED_NETS:
            if addr in net:
                return False, f"禁止访问内网地址: {host}"
        return True, ""
    except Exception:
        return False, "URL 解析失败"
