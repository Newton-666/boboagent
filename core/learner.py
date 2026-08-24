"""core/learner.py — 学习环落笔与生命周期（阶段 C2/C3）。

落笔（C2）：观察触发（observer 过阈值）→ 写 LESSON 记忆（后端监督，确定性）。
生命周期（C3）：记忆超容量 → 归档驱逐最低价值（signal×使用度，先归档可逆护栏）。

范式条款落点：
- 学习 = 后端背景监督（本模块确定性写记忆，LLM 不参与）；
- 落笔写记忆（自我反馈为主 → LESSON 类型）；
- 写+忘双端（C3 剪枝是"忘"）；
- 护栏：先归档后驱逐（可逆）；只写不碰前馈。
"""
import logging

logger = logging.getLogger(__name__)


def write_lesson(tool_name: str, error_type: str, count: int) -> bool:
    """C2 落笔：过阈值触发 → 写一条 LESSON 记忆（防同类错误再犯）。

    确定性模板（不调 LLM），内容进记忆 → 下一轮被路由召回 → LLM 看到。
    """
    try:
        from tools.v5_memory import save_to_knowledge_base
        text = (
            f"经验（自我反馈）：{tool_name} 出现过 {error_type} 类错误"
            f"（累计 {count} 次）。正确做法：先检查输入格式/路径再调用，"
            f"避免同类错误重复。"
        )
        result = save_to_knowledge_base(text, entry_type="LESSON")
        return bool(result) and "已保存" in result
    except Exception:
        logger.warning("learner.write_lesson failed (silent)", exc_info=True)
        return False


def prune_memory(max_total_chars: int = 100000, keep_archived: bool = True) -> int:
    """C3 生命周期：记忆超容量 → 归档最低价值条目（signal×last_used，先归档可逆）。

    返回归档条数。只归档不删除（可逆护栏：被归档条目可回溯恢复）。
    """
    try:
        from tools.v5_memory import _load, _save
        data = _load()
        entries = data.get("entries", [])
        total = sum(len(e.get("text", "")) for e in entries)
        if total <= max_total_chars:
            return 0
        # 驱逐候选：按价值分 = signal × 使用度（last_used 越新分越高）排序，最低先归档
        def _value(e):
            sig = e.get("signal_score", 100)
            last = e.get("last_used") or e.get("timestamp") or ""
            return sig  # 第一版：按信号分；last_used 已录入待 LRU 权重化（阶段内迭代）
        active = [e for e in entries if not e.get("archived", False)]
        active.sort(key=_value)
        archived = 0
        for e in active:
            if total <= max_total_chars:
                break
            e["archived"] = True
            e["signal_score"] = 0
            total -= len(e.get("text", ""))
            archived += 1
        if archived:
            _save(data)
        return archived
    except Exception:
        logger.warning("learner.prune_memory failed (silent)", exc_info=True)
        return 0
