"""压缩必保层验收（B67 两层）——压 6 次后"还记得X"能答出。

保存层验收：压 6 次后 X 的关键事实在记忆里（不被压缩吃掉）
注入层验收：问"还记得X"→ 记忆召回含 X（MoE 路由能捞到）
mock 压缩 LLM（零真实成本），只让 fact_protect 沉淀。
"""
import sys
import tempfile
import unittest.mock as um
from pathlib import Path

import tools.v5_memory as vm


def _mk_env():
    tmp = Path(tempfile.mkdtemp(prefix="cp_acc_"))
    db = tmp / "kb.json"
    return db


def _build_engine(monkeypatch_cm, db):
    """构造 engine，mock 压缩 LLM（返回固定摘要，不沉淀——只让必保层沉淀）。"""
    from core.engine import Engine
    from core.tool_executor import execute_tool
    from tests.mock_llm import MockLLMCaller, text_response

    caller = MockLLMCaller([text_response("ok")])
    eng = Engine(caller, execute_tool, test_mode=True)
    eng.test_mode = True
    # mock 压缩摘要 LLM：固定返回摘要 + 无知识条目（隔离必保层效果）
    with um.patch.object(eng, "_call_summary_llm",
                         return_value="[SUMMARY] 会话摘要\n(无新知识条目)"):
        # 压缩 LLM 输出解析需要特定格式——mock _parse_compression_output 直接返回空记忆
        with um.patch.object(eng, "_parse_compression_output",
                             return_value=("层2摘要", [], [])):
            return eng


def test_six_compressions_still_remembers():
    """核心验收：压 6 次后，用户提到的 X 仍在记忆（保存层）+ 可召回（注入层）。"""
    db = _mk_env()
    with um.patch.object(vm, "_memory_db", lambda: str(db)):
        from core.engine import Engine
        from core.tool_executor import execute_tool
        from tests.mock_llm import MockLLMCaller, text_response

        caller = MockLLMCaller([text_response("ok")])
        eng = Engine(caller, execute_tool, test_mode=True)
        eng.test_mode = True
        # 造 history：含用户明确提及的事实 X
        # 大 history：X 放在旧段（将被压掉），后续大量填充使 layer0 装不下 → 有可压段
        eng.history = [
            {"role": "user", "content": "记住：我的项目跑在 8080 端口"},
            {"role": "assistant", "content": "好的，记住了。"},
        ] + [
            {"role": "user", "content": f"继续讨论第{i}个技术细节话题，这是无关紧要的填充内容" + "内容。" * 500}
            for i in range(80)
        ]
        # 循环压缩 6 次（mock 预算极小强制触发 + mock 摘要 LLM，隔离必保层效果）
        import core.context as ctx
        for _ in range(6):
            with um.patch.object(ctx, "_get_context_budget", return_value=100):
                with um.patch.object(eng, "_call_summary_llm",
                                     return_value="[SUMMARY] 会话摘要\n(无新知识条目)"):
                    with um.patch.object(eng, "_parse_compression_output",
                                         return_value=("层2摘要", [], [])):
                        eng._compress_history()
        # ── 保存层：X 的关键事实在记忆里 ──
        entries = vm._load()["entries"]
        saved_text = " ".join(e["text"] for e in entries)
        assert "8080" in saved_text, f"压 6 次后 8080 丢了: {saved_text[:100]}"
        # ── 注入层：问"还记得X"→ 召回含 X ──
        from tools.v5_memory import search_knowledge_base
        out = search_knowledge_base("8080")
        assert "8080" in out, "召回应包含 X（注入层可捞到）"
        print(f"✅ 压6次后：保存层有 8080（{len(entries)} 条记忆）· 注入层召回含 8080")
