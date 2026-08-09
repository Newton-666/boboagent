"""票 D2 终审补刀验收：session 级闸门挡住真实记忆库写入。

终审场景：core/proactive.py:161 的 decay_all/time_decay 按日衰减，
一天只犯一次，所以复跑测不出来；第一轮复跑时真实信号 85→80、
186 条被打上今日衰减标记。

验收方式（与终审口径一致）：备份真实库后，把某条记忆的 last_time_decay
改成昨天（制造"该衰减了"的状态），跑引擎驱动的衰减全链路，断言真实库
那条记忆不被消耗（last_time_decay 未被更新为今天）、信号不变——
这才能证明闸真的装上了。
"""

import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from config import BOBO_DATA_DIR


def _real_db() -> Path:
    return Path(BOBO_DATA_DIR) / "knowledge_base.json"


def test_session_gate_blocks_real_memory_decay():
    """真实库被改到"该衰减"状态后，跑衰减链路，真实库纹丝不动。"""
    real_db = _real_db()
    if not real_db.exists():
        pytest.skip("验收依赖真实记忆库存在（本环境无真实库时跳过）")

    # 1. 备份真实库 + 记录原始字节指纹
    backup_dir = Path(tempfile.mkdtemp(prefix="d2_gate_verify_"))
    backup = backup_dir / "knowledge_base.backup.json"
    shutil.copy2(real_db, backup)
    original_bytes = real_db.read_bytes()

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 2. 在真实库上制造"该衰减了"的状态：选一条非人手编辑、非归档的条目，
    #    last_time_decay 改成昨天 + timestamp 改到 30 天前（age≥7 必命中衰减）
    data = json.loads(real_db.read_text(encoding="utf-8"))
    target = None
    for e in data.get("entries", []):
        if not e.get("human_edited") and not e.get("archived"):
            target = e
            break
    assert target is not None, "真实库没有任何可用条目，验收无法进行"
    target_id = target.get("id")
    assert target_id is not None, "目标条目缺少 id，验收无法进行"
    original_score = target.get("signal_score", 100)
    target["last_time_decay"] = yesterday
    target["timestamp"] = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    real_db.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        # 3. 触发引擎驱动的衰减全链路（proactive.py:161 的调用序列 + 镜像同步）
        import tools.v5_memory as v5
        from tools.memory_mirror import sync_mirror
        v5.decay_all()
        v5.time_decay()
        sync_mirror()

        # 4. 断言真实库未被消耗：last_time_decay 仍是昨天、信号不变
        after = json.loads(real_db.read_text(encoding="utf-8"))
        found = next((e for e in after.get("entries", []) if e.get("id") == target_id), None)
        assert found is not None, "真实库目标条目消失"
        assert found.get("last_time_decay") == yesterday, (
            f"闸门失效：真实库条目被消耗，last_time_decay 被更新为 {found.get('last_time_decay')!r}"
        )
        assert found.get("signal_score") == original_score, (
            f"闸门失效：真实库条目信号被衰减 {original_score} -> {found.get('signal_score')}"
        )
    finally:
        # 5. 无论成败都恢复真实库原状
        shutil.copy2(backup, real_db)

    # 6. 恢复后字节指纹与原库一致
    assert real_db.read_bytes() == original_bytes, "真实库恢复后与原始内容不一致"
