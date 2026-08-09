"""Fixtures compartidas para los tests de kimi-memory."""

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mcp_module(tmp_path, monkeypatch):
    """Devuelve el módulo memory_mcp con una base de datos temporal aislada."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("KIMI_MEMORY_DB", str(db_path))

    # Si el módulo ya fue cargado (por ejemplo por memory_web), lo recargamos
    # para que tome la nueva variable de entorno.
    if "memory_mcp" in sys.modules:
        importlib.reload(sys.modules["memory_mcp"])

    import memory_mcp

    memory_mcp.reset_db(db_path)
    return memory_mcp


@pytest.fixture
def db(mcp_module):
    return mcp_module.get_db()


@pytest.fixture
def add_memory(mcp_module):
    def _add(*args, **kwargs):
        return mcp_module.add_memory(*args, **kwargs)
    return _add
