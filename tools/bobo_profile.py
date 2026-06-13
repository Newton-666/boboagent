"""View or update user profile — preferences that persist across sessions."""

TOOL_NAME = "bobo_profile"


def execute(action: str = "view", key: str = "", value: str = "") -> str:
    """View or update user profile."""
    from tools.v5_memory import save_user_profile, get_user_profile

    if action == "view":
        profile = get_user_profile()
        if not profile:
            return "当前没有用户资料。可以说 '记住我的名字是 Newton' 来添加。"
        lines = ["当前用户资料:"]
        for k, entry in sorted(profile.items()):
            lines.append(f"  {k}: {entry['value']}")
        return "\n".join(lines)

    if action == "set":
        if not key or not value:
            return "请提供 key 和 value"
        return save_user_profile(key, value)

    return "支持: view (查看), set (设置)"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "查看或更新用户资料（偏好、语言、风格等，跨会话持久化）。action='view' 查看当前资料，action='set' 设置资料项。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作: view 或 set"},
                "key": {"type": "string", "description": "资料键名，如 name, language, timezone"},
                "value": {"type": "string", "description": "资料值（action=set 时需要）"}
            },
            "required": ["action"]
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
