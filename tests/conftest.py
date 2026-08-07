"""Shared fixtures and configuration for the Bobo test suite."""

import os
import sys
import tempfile
from pathlib import Path
import pytest

# Ensure the project root is on sys.path so we can import core, tools, etc.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Force test mode for the engine — no real API calls, no user prompts
os.environ["BOBO_TEST_MODE"] = "1"


@pytest.fixture(autouse=True, scope="session")
def _redirect_event_bus():
    """重定向 EventBus 单例到临时目录，防止测试污染生产 events.jsonl（票 J）。"""
    import tempfile
    from pathlib import Path
    from core.event_bus import EventBus

    tmpdir = Path(tempfile.mkdtemp(prefix="bobo_test_events_"))
    EventBus.reset(log_dir=str(tmpdir))


@pytest.fixture
def project_root():
    """Return the absolute project root path."""
    return Path(_project_root)


@pytest.fixture
def temp_dir():
    """Create a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def temp_vault(temp_dir):
    """Create a temporary Obsidian vault with a few note files."""
    vault = temp_dir / "vault"
    vault.mkdir()
    # Create a few .md files
    (vault / "note1.md").write_text("# Note 1\n\nContent about Python programming.", encoding="utf-8")
    (vault / "note2.md").write_text("# Note 2\n\nContent about AI agents and machine learning.", encoding="utf-8")
    (vault / "note3.md").write_text("# Note 3\n\nRandom thoughts about coffee.", encoding="utf-8")

    bobodir = vault / "Bobo"
    bobodir.mkdir()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("OBSIDIAN_VAULT", str(vault))
        yield vault


@pytest.fixture
def isolated_memory_db(tmp_path, monkeypatch):
    """共享隔离记忆库（票 LN-4）：不依赖真实 knowledge_base.json。

    test_injector.py 以 autouse 复用；test_e3a_skill_zombie.py 显式请求。
    保证 injector 相关断言跑在干净记忆下，不受真实记忆库内容影响
    （真实记忆库随时可能出现"推荐技能"等字样，泛匹配断言会误伤）。
    注入两条固定记忆（其中一条含 "skill" 字样，让依赖该字样的断言稳定成立）。
    """
    import json
    import tools.v5_memory as v5

    kb = tmp_path / "knowledge_base.json"
    payload = json.dumps({
        "entries": [
            {
                "id": 1,
                "text": "保存为 skill 的流程：说『开始教学』录制，完成后说『保存为 skill <名称>』",
                "timestamp": "2026-07-31 10:00:00",
                "signal_score": 150,
                "folder": "general", "type": "general",
                "tags": [], "last_time_decay": "",
            },
            {
                "id": 2,
                "text": "记忆库隔离测试条目二",
                "timestamp": "2026-07-30 10:00:00",
                "signal_score": 80,
                "folder": "general", "type": "general",
                "tags": [], "last_time_decay": "",
            },
        ],
        "folders": [],
    }, ensure_ascii=False)
    kb.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(v5, "MEMORY_DB", str(kb))
    monkeypatch.setattr(v5, "_MEMORY_BACKUP", str(kb) + ".bak")
    return kb


@pytest.fixture
def engine():
    """Create an Engine instance with a mock LLM caller for testing."""
    from core.engine import Engine
    from core.tool_executor import execute_tool
    from tests.mock_llm import MockLLMCaller, text_response

    caller = MockLLMCaller([text_response("Hello! I am Bobo.")])
    engine = Engine(caller, execute_tool, test_mode=True)
    return engine


@pytest.fixture
def mock_engine(engine):
    """Alias for 'engine' fixture. Both names work."""
    return engine
