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
