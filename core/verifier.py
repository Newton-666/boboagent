"""verifier.py — LLM 响应验证：检测空口声称完成但没有工具证据的情况。"""


class Verifier:
    """检测 LLM 是否声称完成任务但没有调用任何工具来证明。"""

    def __init__(self):
        self.attempted = False

    def needs_verification(self, content: str) -> bool:
        """Check if the LLM's response needs verification."""
        # 移除 round 限制，所有轮次都检测（第二里程碑修复）
        # 票 R3-c：完成词收紧——宽泛两字词（"完成"/"阶段"）改短语匹配。
        # 任何回复都可能含"完成"/"阶段"（如"完成项""阶段"），此前必然误触发；
        # 收紧为明确的完成短语，且仅在无工具证据时触发（check_and_inject 判定）。
        completion_markers = ["已完成", "已经完成", "全部完成", "已全部完成",
                              "已创建", "已写入",
                              "done", "finished", "created", "written",
                              "fixed", "已修复", "已修改", "已添加", "已删除"]
        text_lower = content.lower()
        for marker in completion_markers:
            if marker.lower() in text_lower:
                return True
        return False

    def check_and_inject(self, history: list, content: str, tool_exec_count: int = 0):
        """检查并注入验证提示：如果声称完成且本回合零 tool.exec，注入验证请求。

        票 R3-c：仅当声称完成 AND 本回合零 tool.exec（无任何施工证据）才触发——
        干完活正常收尾（有工具执行）不触发，问答回合有实质回答但零工具也不误伤。
        """
        if (content and self.needs_verification(content)
                and not self.attempted and tool_exec_count == 0):
            self.attempted = True
            history.append({"role": "assistant", "content": content})
            note = (
                "[验证] 你声称完成了操作，但本轮没有调用任何工具。\n"
                "如果你确实完成了，请提供具体证据（文件路径、返回值、截图等）。\n"
                "如果你实际上没有执行操作，请如实告知用户。\n"
                "如果你需要重新执行，请使用对应的工具。"
            )
            history.append({"role": "system", "content": note})
            return True
        return False
