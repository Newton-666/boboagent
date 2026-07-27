"""checkpoint.py — 对话回退系统：保存/查找/恢复历史快照。

从 engine.py 提取，原为 Engine 类的 _save_checkpoint / _find_checkpoint / _do_undo。
"""

import copy
import logging
import os as _os

logger = logging.getLogger(__name__)


class CheckpointManager:
    """管理对话回退快照：保存、查找、恢复历史状态和文件。"""

    MAX_CHECKPOINTS = 20

    def __init__(self, history_getter, file_checkpoints_getter, workspace_dir=""):
        """初始化检查点管理器。

        Args:
            history_getter: 可调用对象，返回 self.history 列表
            file_checkpoints_getter: 可调用对象，返回 self._file_checkpoints 字典
            workspace_dir: 工作区目录（保留，供未来使用）
        """
        self._get_history = history_getter
        self._get_file_checkpoints = file_checkpoints_getter
        self._workspace_dir = workspace_dir
        self._checkpoints: list[dict] = []

    # ── 保存 ──

    def save(self, label: str = "", current_depth: int = 0, current_tool_round: int = 0):
        """保存当前对话状态快照，用于回退。"""
        files = {}
        for path, content in self._get_file_checkpoints().items():
            if _os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as _f:
                        files[path] = _f.read()
                except Exception:
                    files[path] = content
        self._checkpoints.append({
            "label": label or f"step_{current_depth}",
            "history": copy.deepcopy(self._get_history()),
            "files": files,
            "depth": current_depth,
            "tool_round": current_tool_round,
        })
        # 只保留最近 N 个快照
        if len(self._checkpoints) > self.MAX_CHECKPOINTS:
            self._checkpoints = self._checkpoints[-self.MAX_CHECKPOINTS:]

    # ── 查找 ──

    def find(self, target: str = "") -> int | None:
        """查找快照索引。支持数字（回退 N 步）、关键词匹配 label、默认回退 1 步。"""
        if not self._checkpoints:
            return None
        if not target:
            # 回退一步（倒数第二个快照）；只有一个快照时回到它（恢复之前状态）
            return max(0, len(self._checkpoints) - 2)
        # 数字
        try:
            steps = int(target)
            idx = len(self._checkpoints) - 1 - steps
            return max(0, idx)
        except ValueError:
            pass
        # 关键词
        for i in range(len(self._checkpoints) - 1, -1, -1):
            if target.lower() in self._checkpoints[i]["label"].lower():
                return i
        return None

    # ── 回退 ──

    def undo(self, target: str = "") -> tuple:
        """执行回退，返回 (success, user_message, new_history, new_depth, new_tool_round, label)。

        调用方根据 success 决定是否应用 state 变更：
        - success=False → user_message 是错误提示，其余为 None
        - success=True  → 需将 new_history/new_depth/new_tool_round 写入 engine
        """
        if not self._checkpoints:
            return (False, "没有可回退的操作。", None, None, None, "")
        idx = self.find(target)
        if idx is None:
            return (False, f"未找到匹配的快照: {target}", None, None, None, "")

        cp = self._checkpoints[idx]
        # 恢复文件
        restored = []
        for path, content in cp.get("files", {}).items():
            try:
                _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding="utf-8") as _f:
                    _f.write(content)
                restored.append(_os.path.basename(path))
            except Exception as e:
                logger.debug("回退恢复文件失败 (%s): %s", path, e)
        # 截断后续快照
        self._checkpoints = self._checkpoints[:idx + 1]

        label = cp["label"]
        file_info = f"\n文件已恢复: {', '.join(restored)}" if restored else ""
        msg = f"已回退到: {label}{file_info}\n\n要继续对话吗？"

        return (True, msg, cp["history"], cp["depth"], cp["tool_round"], label)

    # ── 管理 ──

    def clear(self):
        """清空所有快照（重置时调用）。"""
        self._checkpoints.clear()

    def __bool__(self):
        return bool(self._checkpoints)

    @property
    def checkpoints(self) -> list[dict]:
        """公开快照列表，供序列化/反序列化使用。"""
        return self._checkpoints
