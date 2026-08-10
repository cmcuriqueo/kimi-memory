"""Fixtures compartidas para los benchmarks de kimi-memory."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def benchmark_db(tmp_path, monkeypatch):
    """Devuelve memory_mcp con una base de datos temporal aislada."""
    db_path = tmp_path / "benchmark.db"
    monkeypatch.setenv("KIMI_MEMORY_DB", str(db_path))

    if "memory_mcp" in sys.modules:
        importlib.reload(sys.modules["memory_mcp"])

    import memory_mcp

    memory_mcp.reset_db(db_path)
    return memory_mcp


@pytest.fixture
def tokenizer():
    """Devuelve una función para contar tokens.

    Usa tiktoken si está disponible; si no, aplica una estimación conservadora
    basada en palabras para que los benchmarks sigan funcionando.
    """
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model("gpt-4o")

        def _count(text: str) -> int:
            return len(enc.encode(text or ""))

        _count.uses_real_tokenizer = True  # type: ignore[attr-defined]
        return _count
    except Exception:

        def _estimate(text: str) -> int:
            # Estimación conservadora: ~1.3 tokens por palabra para inglés/español.
            return int(len((text or "").split()) * 1.3)

        _estimate.uses_real_tokenizer = False  # type: ignore[attr-defined]
        return _estimate


@pytest.fixture(scope="session")
def benchmark_reporter():
    """Reporter compartido para acumular métricas entre tests."""
    from .reporter import BenchmarkReporter

    reporter = BenchmarkReporter()
    yield reporter
    reporter.print_summary()
