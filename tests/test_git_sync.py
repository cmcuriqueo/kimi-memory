"""Tests para sincronización via Git."""

import shutil
import subprocess
from pathlib import Path

import pytest


def _git(repo, args):
    return subprocess.run(
        ["git", "-C", str(repo)] + args,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def git_repo(tmp_path, mcp_module):
    repo = tmp_path / "git-memory"
    repo.mkdir()
    _git(repo, ["init"])
    _git(repo, ["config", "user.email", "test@example.com"])
    _git(repo, ["config", "user.name", "Test User"])
    yield repo


def test_export_to_git_creates_markdown(git_repo, mcp_module):
    a = mcp_module.add_memory("Decisión de usar JWT", category="decision", project="api", tags=["auth"])
    b = mcp_module.add_memory("Implementar middleware", category="todo", related_ids=[a["id"]])

    result = mcp_module.export_to_git(git_repo)
    assert result["exported"] == 2

    files = list((git_repo / "memories").glob("*.md"))
    assert len(files) == 2

    contents = {f.name: f.read_text(encoding="utf-8") for f in files}
    # Verificar que uno de los archivos contiene la decisión.
    assert any("Decisión de usar JWT" in text for text in contents.values())
    # Verificar frontmatter.
    for text in contents.values():
        assert text.startswith("---")
        assert "uuid:" in text


def test_import_from_git(git_repo, mcp_module):
    md = """---
uuid: "11111111-1111-1111-1111-111111111111"
category: "note"
project: "imported"
tags: ["imported", "tag-a"]
related_uuids: []
created_at: 1700000000
updated_at: 1700000001
---

Recuerdo importado desde Git.
"""
    memories_dir = git_repo / "memories"
    memories_dir.mkdir(exist_ok=True)
    (memories_dir / "11111111-1111-1111-1111-111111111111.md").write_text(md, encoding="utf-8")

    result = mcp_module.import_from_git(git_repo)
    assert result["imported"] == 1

    memories = mcp_module.search_memories("importado")
    assert len(memories) == 1
    assert memories[0]["category"] == "note"
    assert memories[0]["project"] == "imported"
    assert "imported" in memories[0]["tags"]
    assert memories[0]["uuid"] == "11111111-1111-1111-1111-111111111111"


def test_sync_git_commit(git_repo, mcp_module):
    mcp_module.add_memory("Recuerdo para sync")

    result = mcp_module.sync_git(git_repo, full=False)
    assert result["synced"] is True
    assert result["commit"]["ok"] is True

    log = _git(git_repo, ["log", "--oneline"])
    assert "kimi-memory sync" in log.stdout


def test_sync_git_roundtrip(git_repo, mcp_module):
    mcp_module.add_memory("Local A", tags=["local"])
    mcp_module.sync_git(git_repo, full=False)

    # Simular cambio remoto: borrar la DB local y recrear desde el repo.
    conn = mcp_module.get_db()
    conn.execute("DELETE FROM memories")
    conn.execute("DELETE FROM memories_fts")
    conn.execute("DELETE FROM memory_tags")
    conn.execute("DELETE FROM memory_relations")
    conn.commit()

    # Importar directamente (sin pull, porque el repo de test no tiene remote).
    imported = mcp_module.import_from_git(git_repo)
    assert imported["imported"] == 1

    memories = mcp_module.recent_memories(limit=10)
    assert any(m["content"] == "Local A" for m in memories)


def test_get_git_repo_from_env(tmp_path, monkeypatch):
    repo = tmp_path / "env-repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    monkeypatch.setenv("KIMI_MEMORY_GIT_REPO", str(repo))

    import memory_mcp
    assert memory_mcp.get_git_repo() == repo


def test_get_git_repo_from_config(tmp_path, monkeypatch, mcp_module):
    """El repo puede configurarse en el archivo de config persistente."""
    repo = tmp_path / "config-repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    config_path = tmp_path / "memory-config.json"
    monkeypatch.setenv("KIMI_MEMORY_CONFIG", str(config_path))
    monkeypatch.delenv("KIMI_MEMORY_GIT_REPO", raising=False)

    result = mcp_module.set_git_repo(repo)
    assert result["ok"] is True
    assert mcp_module.get_git_repo() == repo


def test_env_takes_precedence_over_config(tmp_path, monkeypatch, mcp_module):
    """La variable de entorno tiene prioridad sobre el archivo de config."""
    env_repo = tmp_path / "env-repo"
    env_repo.mkdir()
    subprocess.run(["git", "-C", str(env_repo), "init"], check=True, capture_output=True)

    config_repo = tmp_path / "config-repo"
    config_repo.mkdir()
    subprocess.run(["git", "-C", str(config_repo), "init"], check=True, capture_output=True)

    config_path = tmp_path / "memory-config.json"
    monkeypatch.setenv("KIMI_MEMORY_CONFIG", str(config_path))
    monkeypatch.setenv("KIMI_MEMORY_GIT_REPO", str(env_repo))

    mcp_module.set_git_repo(config_repo)
    assert mcp_module.get_git_repo() == env_repo


def test_memory_config_tool(tmp_path, monkeypatch, mcp_module):
    """La herramienta memory_config guarda y lee la configuración."""
    repo = tmp_path / "tool-repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)

    config_path = tmp_path / "memory-config.json"
    monkeypatch.setenv("KIMI_MEMORY_CONFIG", str(config_path))
    monkeypatch.delenv("KIMI_MEMORY_GIT_REPO", raising=False)

    result = mcp_module.dispatch_tool("memory_config", {"git_repo": str(repo)})
    assert result["ok"] is True
    assert result["git_repo"] == str(repo)
    assert mcp_module.get_git_repo() == repo


def test_memory_sync_with_explicit_repo(git_repo, mcp_module):
    """memory_sync acepta un repo explícito como parámetro."""
    mcp_module.add_memory("Recuerdo con repo explícito")
    result = mcp_module.dispatch_tool("memory_sync", {"repo": str(git_repo)})
    assert result["synced"] is True
    log = _git(git_repo, ["log", "--oneline"])
    assert "kimi-memory sync" in log.stdout
