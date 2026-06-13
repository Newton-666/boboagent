"""Bobo TUI Gateway 入口"""

import json
import logging
import os
import signal
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from bobo_tui_gateway.server import dispatch
from bobo_tui_gateway.transport import write_json

logger = logging.getLogger(__name__)


def _shutdown(signum, frame):
    """SIGINT/SIGTERM 处理：保存会话后退出"""
    from bobo_tui_gateway.server import shutdown_sessions
    shutdown_sessions()
    sys.exit(0)


signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


def resolve_skin() -> dict:
    """返回 TUI 皮肤配置（Bobo 品牌）"""
    return {
        "colors": {
            "ui_primary": "#FFD700",
            "ui_accent": "#FFBF00",
            "ui_border": "#CD7F32",
            "ui_text": "#FFF8DC",
            "banner_title": "#FFD700",
            "banner_accent": "#FFBF00",
            "banner_dim": "#CC9B1F",
            "banner_border": "#CD7F32",
        },
        "branding": {
            "agent_name": "Bobo Agent",
            "prompt_symbol": ">",
            "welcome": "你好！我是 Bobo，你的智能助手。",
            "goodbye": "再见！",
            "help_header": "Bobo 命令帮助",
        },
        "banner_logo": "",
        "banner_hero": "",
        "tool_prefix": "|",
    }


def main():
    # 启动前检查：API Key 是否存在
    from config import API_KEY
    if not API_KEY:
        write_json({
            "jsonrpc": "2.0",
            "method": "event",
            "params": {
                "type": "gateway.error",
                "payload": {
                    "message": (
                        "DEEPSEEK_API_KEY 未配置。\n"
                        "请在 ~/.bobo/.env 中添加:\n"
                        "  DEEPSEEK_API_KEY=sk-你的密钥"
                    )
                }
            },
        })
        sys.exit(1)

    # 发送 ready 事件（包含皮肤配置）
    if not write_json({
        "jsonrpc": "2.0",
        "method": "event",
        "params": {
            "type": "gateway.ready",
            "payload": {"skin": resolve_skin()}
        },
    }):
        sys.exit(0)

    # 读取并处理请求
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            write_json({
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "parse error"},
                "id": None,
            })
            continue

        resp = dispatch(req)
        if resp is not None:
            if not write_json(resp):
                break  # stdout 写入失败，TUI 已断开

    # stdin 关闭（TUI 断开），保存所有活跃会话
    from bobo_tui_gateway.server import shutdown_sessions
    shutdown_sessions()


if __name__ == "__main__":
    main()
