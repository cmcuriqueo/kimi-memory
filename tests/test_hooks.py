"""Tests para hooks/memory_hook.py."""

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def _load_hook_module():
    hook_path = PROJECT_ROOT / "hooks" / "memory_hook.py"
    spec = importlib.util.spec_from_file_location("memory_hook", hook_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hook_module(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("KIMI_MEMORY_DB", str(db_path))
    monkeypatch.setenv("KIMI_MEMORY_PLUGIN_DIR", str(PROJECT_ROOT))

    # Eliminar del cache para forzar recarga con nuevas variables de entorno.
    sys.modules.pop("memory_hook", None)
    sys.modules.pop("memory_mcp", None)

    memory_hook = _load_hook_module()
    memory_mcp = memory_hook.memory_mcp
    memory_mcp.reset_db(db_path)
    return memory_hook


def test_post_tool_use_write_file(hook_module):
    hook_module.handle_post_tool_use({
        "hook_event_name": "PostToolUse",
        "tool_name": "WriteFile",
        "tool_input": {"path": "src/auth.py"},
        "cwd": "/home/user/proyecto-x",
    })
    memories = hook_module.memory_mcp.recent_memories(limit=1)
    assert len(memories) == 1
    assert memories[0]["category"] == "file_change"
    assert "src/auth.py" in memories[0]["content"]
    assert set(memories[0]["tags"]) == {"auth.py", "file-change", "py"}


def test_post_tool_use_str_replace_file(hook_module):
    hook_module.handle_post_tool_use({
        "hook_event_name": "PostToolUse",
        "tool_name": "StrReplaceFile",
        "tool_input": {"path": "README.md"},
        "cwd": "/home/user/proyecto-x",
    })
    memories = hook_module.memory_mcp.recent_memories(limit=1)
    assert memories[0]["category"] == "file_change"
    assert set(memories[0]["tags"]) == {"file-change", "md", "readme.md"}


def test_user_prompt_submit_interesting(hook_module):
    hook_module.handle_user_prompt_submit({
        "hook_event_name": "UserPromptSubmit",
        "prompt": "Tenemos un bug en la autenticación JWT, decidimos cambiar a RS256.",
        "cwd": "/home/user/proyecto-x",
    })
    memories = hook_module.memory_mcp.recent_memories(limit=1)
    assert memories[0]["category"] == "prompt"
    assert "bug" in memories[0]["tags"]
    assert "jwt" in memories[0]["tags"]
    assert "prompt" in memories[0]["tags"]


def test_user_prompt_submit_ignored(hook_module):
    hook_module.handle_user_prompt_submit({
        "hook_event_name": "UserPromptSubmit",
        "prompt": "ok gracias",
        "cwd": "/home/user/proyecto-x",
    })
    memories = hook_module.memory_mcp.recent_memories(limit=1)
    assert not memories or memories[0]["category"] != "prompt"


def test_pre_compact(hook_module):
    hook_module.handle_pre_compact({
        "hook_event_name": "PreCompact",
        "trigger": "context_limit",
        "token_count": 250000,
        "cwd": "/home/user/proyecto-x",
        "session_id": "abc123",
    })
    memories = hook_module.memory_mcp.recent_memories(limit=1)
    assert memories[0]["category"] == "compaction_context"
    assert "compaction" in memories[0]["tags"]


def test_stop_failure(hook_module):
    hook_module.handle_stop_failure({
        "hook_event_name": "StopFailure",
        "error_type": "ToolExecutionError",
        "error_message": "El comando falló con exit code 1",
        "cwd": "/home/user/proyecto-x",
    })
    memories = hook_module.memory_mcp.recent_memories(limit=1)
    assert memories[0]["category"] == "bugfix"
    assert "bugfix" in memories[0]["tags"]
    assert "toolexecutionerror" in memories[0]["tags"]


def test_session_end_minimal(hook_module):
    hook_module.handle_session_end({
        "hook_event_name": "SessionEnd",
        "session_id": "abc123",
        "cwd": "/home/user/proyecto-x",
        "reason": "exit",
    })
    memories = hook_module.memory_mcp.recent_memories(limit=1)
    assert memories[0]["category"] == "session_summary"
    assert "session-summary" in memories[0]["tags"]
