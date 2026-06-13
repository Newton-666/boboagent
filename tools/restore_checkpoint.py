"""Restore a file from its last checkpoint (before file_writer changed it)."""

TOOL_NAME = "restore_checkpoint"

TOOL_FUNC = None  # wired via engine

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "撤销上一次 file_writer 对某个文件的修改，将其恢复为修改前的内容。"
            "不传 path 参数时列出所有可回滚的文件。"
            "适用场景：代码或文档被误修改后，需要快速回退。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径，为空则列出检查点"}
            },
            "required": []
        }
    }
}

def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
