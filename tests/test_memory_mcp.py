"""Tests unitarios para memory_mcp.py."""

import pytest


def test_add_memory_basic(mcp_module, db):
    result = mcp_module.add_memory("Contenido de prueba", category="note", project="test")
    assert result["added"] is True
    assert isinstance(result["id"], int)

    rows = db.execute("SELECT * FROM memories WHERE id = ?", (result["id"],)).fetchall()
    assert len(rows) == 1
    assert rows[0]["content"] == "Contenido de prueba"
    assert rows[0]["category"] == "note"
    assert rows[0]["project"] == "test"


def test_add_memory_with_tags_and_relations(mcp_module):
    a = mcp_module.add_memory("Decisión A", tags=["auth", "jwt"])
    b = mcp_module.add_memory("Tarea B", tags=["auth"], related_ids=[a["id"]])

    assert a["added"] is True
    assert b["added"] is True

    memories = mcp_module.get_memories([a["id"], b["id"]])
    by_id = {m["id"]: m for m in memories}

    assert by_id[a["id"]]["tags"] == ["auth", "jwt"]
    assert by_id[a["id"]]["related_ids"] == [b["id"]]
    assert by_id[b["id"]]["tags"] == ["auth"]
    assert by_id[b["id"]]["related_ids"] == [a["id"]]


def test_add_memory_private_tags(mcp_module):
    result = mcp_module.add_memory("Token: <private>secreto</private> fin")
    assert result["added"] is True

    m = mcp_module.get_memories([result["id"]])[0]
    assert "secreto" not in m["content"]
    assert "<private>" not in m["content"]


def test_add_memory_empty_after_private(mcp_module):
    result = mcp_module.add_memory("<private>secreto</private>")
    assert result["added"] is False
    assert "reason" in result


def test_search_memories_full_text(mcp_module):
    mcp_module.add_memory("SQLite con FTS5")
    mcp_module.add_memory("Otra cosa")

    results = mcp_module.search_memories("FTS5")
    assert len(results) == 1
    assert "FTS5" in results[0]["content"]


def test_search_memories_with_tags(mcp_module):
    mcp_module.add_memory("Auth con JWT", tags=["auth", "jwt"])
    mcp_module.add_memory("Auth con OAuth", tags=["auth", "oauth"])
    mcp_module.add_memory("Otro tema", tags=["other"])

    results = mcp_module.search_memories("Auth", tags=["auth", "jwt"])
    assert len(results) == 1
    assert "JWT" in results[0]["content"]


def test_search_empty_query_returns_recent(mcp_module):
    mcp_module.add_memory("A")
    mcp_module.add_memory("B")
    results = mcp_module.search_memories("")
    assert len(results) == 2


def test_get_memories(mcp_module):
    a = mcp_module.add_memory("A")
    b = mcp_module.add_memory("B")
    results = mcp_module.get_memories([a["id"], b["id"]])
    assert len(results) == 2
    assert {r["content"] for r in results} == {"A", "B"}


def test_recent_memories(mcp_module):
    mcp_module.add_memory(" viejo ")
    mcp_module.add_memory(" nuevo ")
    results = mcp_module.recent_memories(limit=2)
    assert len(results) == 2
    assert results[0]["content"] == "nuevo"


def test_recent_memories_with_tags(mcp_module):
    mcp_module.add_memory("A", tags=["tag-a"])
    mcp_module.add_memory("B", tags=["tag-b"])
    results = mcp_module.recent_memories(tags=["tag-a"])
    assert len(results) == 1
    assert results[0]["content"] == "A"


def test_timeline_memory(mcp_module):
    ids = [mcp_module.add_memory(f"M{i}")["id"] for i in range(5)]
    center = ids[2]
    results = mcp_module.timeline_memory(center, window=2)
    assert len(results) >= 3
    assert center in [r["id"] for r in results]


def test_update_memory(mcp_module):
    created = mcp_module.add_memory("Original", category="note", tags=["old"])
    updated = mcp_module.update_memory(
        created["id"],
        content="Actualizado",
        category="decision",
        tags=["new"],
    )
    assert updated["updated"] is True

    m = mcp_module.get_memories([created["id"]])[0]
    assert m["content"] == "Actualizado"
    assert m["category"] == "decision"
    assert m["tags"] == ["new"]


def test_update_memory_not_found(mcp_module):
    result = mcp_module.update_memory(99999, content="Nada")
    assert result["updated"] is False


def test_delete_memory_cascade(mcp_module):
    a = mcp_module.add_memory("A", tags=["x"])
    b = mcp_module.add_memory("B", related_ids=[a["id"]])

    mcp_module.delete_memory(a["id"])

    assert mcp_module.get_memories([a["id"]]) == []
    tags = mcp_module.get_memory_tags(a["id"])
    assert tags == []
    rels = mcp_module.get_memory_relations(b["id"])
    assert rels == []


def test_export_import_roundtrip(mcp_module, tmp_path):
    a = mcp_module.add_memory("Recuerdo A", category="note", project="p", tags=["a"])
    b = mcp_module.add_memory("Recuerdo B", related_ids=[a["id"]])

    path = tmp_path / "backup.json"
    exported = mcp_module.export_memories(path=str(path))
    assert exported["count"] == 2

    # Borrar todo
    conn = mcp_module.get_db()
    conn.execute("DELETE FROM memories")
    conn.execute("DELETE FROM memories_fts")
    conn.execute("DELETE FROM memory_tags")
    conn.execute("DELETE FROM memory_relations")
    conn.commit()

    imported = mcp_module.import_memories(str(path))
    assert imported["imported"] == 2

    memories = mcp_module.recent_memories(limit=10)
    assert len(memories) == 2
    by_content = {m["content"]: m for m in memories}
    assert "a" in by_content["Recuerdo A"]["tags"]
    assert by_content["Recuerdo B"]["related_ids"]


def test_parse_timestamp(mcp_module):
    assert mcp_module.parse_timestamp("7d") is not None
    assert mcp_module.parse_timestamp("2026-08-01") is not None
    assert mcp_module.parse_timestamp(1234567890) == 1234567890

    with pytest.raises(ValueError):
        mcp_module.parse_timestamp("fecha-invalida")


def test_normalize_tags(mcp_module):
    assert mcp_module.normalize_tags([" Auth ", "JWT", "auth"]) == ["auth", "jwt"]
    assert mcp_module.normalize_tags(None) == []
    assert mcp_module.normalize_tags("solo") == ["solo"]


def test_normalize_related_ids(mcp_module):
    assert mcp_module.normalize_related_ids([1, 2, "3", 2], memory_id=2) == [1, 3]
    assert mcp_module.normalize_related_ids(None) == []


def test_search_sanitizes_fts5_special_chars(mcp_module):
    """Las consultas con caracteres especiales de FTS5 no deben fallar."""
    mcp_module.add_memory("Usamos Fly.io para desplegar.", category="decision", project="api")
    mcp_module.add_memory("El token es UTF-8 con guiones.", category="note", project="api")

    # Puntos
    results = mcp_module.search_memories("Fly.io", project="api")
    assert any("Fly.io" in r["content"] for r in results)

    # Guiones
    results = mcp_module.search_memories("UTF-8", project="api")
    assert any("UTF-8" in r["content"] for r in results)

    # Comillas
    results = mcp_module.search_memories('"token"', project="api")
    assert len(results) >= 0  # No lanza excepcion


def test_generate_gist(mcp_module):
    """El gist resume contenido largo y conserva contenido corto."""
    corto = "Decisión: usamos JWT."
    assert mcp_module.generate_gist(corto) == corto

    largo = (
        "Decisión de arquitectura: usamos JWT con algoritmo RS256 para autenticación. "
        "El secret se genera con openssl y se rota cada 90 dias. "
        "El frontend recibe un access token de 15 minutos y un refresh token de 7 dias. "
        "Además configuramos CORS para permitir solo los dominios de producción y "
        "agregamos rate limiting en el endpoint de login para prevenir ataques de fuerza bruta."
    )
    gist = mcp_module.generate_gist(largo)
    assert len(gist) < len(largo)
    assert "JWT" in gist or "RS256" in gist
    assert gist.endswith("...")


def test_memory_includes_gist(mcp_module):
    """Los recuerdos devueltos incluyen el campo gist."""
    result = mcp_module.add_memory(
        "Esta es una decision larga con mucho contexto. " * 10,
        category="decision",
    )
    memory = mcp_module.get_memories([result["id"]])[0]
    assert "gist" in memory
    assert memory["gist"]
    assert len(memory["gist"]) < len(memory["content"])


def test_add_memory_deduplicates_similar(mcp_module):
    """Si se guarda un recuerdo muy similar, se actualiza el existente."""
    a = mcp_module.add_memory(
        "Usamos JWT con RS256 para autenticación.",
        category="decision",
        project="api",
        tags=["auth"],
    )
    b = mcp_module.add_memory(
        "Usamos JWT con RS256 para autenticación en la API.",
        category="decision",
        project="api",
        tags=["auth", "jwt"],
    )
    assert a["id"] == b["id"]
    assert b["updated"] is True

    tags = mcp_module.get_memory_tags(b["id"])
    assert "auth" in tags
    assert "jwt" in tags


def test_add_memory_no_deduplicate_when_disabled(mcp_module):
    """Se puede desactivar la deduplicación."""
    a = mcp_module.add_memory("Decisión única.", category="decision")
    b = mcp_module.add_memory("Decisión única.", category="decision", deduplicate=False)
    assert a["id"] != b["id"]


def test_find_similar_memories(mcp_module):
    """find_similar_memories encuentra recuerdos relacionados."""
    a = mcp_module.add_memory("Usamos PostgreSQL con SQLAlchemy.", project="api")
    mcp_module.add_memory("Otra cosa no relacionada.", project="api")

    similar = mcp_module.find_similar_memories(
        "La base de datos es PostgreSQL y usamos SQLAlchemy.",
        project="api",
        threshold=0.3,
    )
    assert any(s["id"] == a["id"] for s in similar)


def test_index_project(mcp_module, tmp_path):
    """index_project guarda descripciones de archivos del proyecto."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text(
        '"""Modulo de autenticación con JWT."""\ndef login(): pass\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Proyecto demo\n", encoding="utf-8")

    result = mcp_module.index_project(tmp_path, project="demo")
    assert result["indexed"] == 2
    assert result["project"] == "demo"

    results = mcp_module.search_memories("autenticación", project="demo")
    assert any("auth.py" in r["content"] for r in results)
