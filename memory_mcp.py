#!/usr/bin/env python3
"""
Kimi Memory MCP Server — Minimalista, sin dependencias externas.
Memoria persistente para Kimi Code CLI usando SQLite + FTS5.
Comunicación MCP sobre stdio (JSON-RPC 2.0).
"""

import datetime
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# Forzar UTF-8 en stdio para evitar problemas de encoding en Windows con
# caracteres no-ASCII (acentos, eñes, etc.).
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
DEFAULT_DB = Path.home() / ".kimi-code" / "memory.db"

# Variables globales para la conexión lazy. Permiten reconfigurar la DB en tests.
_DB_PATH: Path | None = None
_DB: sqlite3.Connection | None = None


def get_db_path() -> Path:
    if _DB_PATH is not None:
        return _DB_PATH
    return Path(os.environ.get("KIMI_MEMORY_DB", DEFAULT_DB))


def set_db_path(path: Path | str) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)


def get_db() -> sqlite3.Connection:
    global _DB
    if _DB is None:
        path = get_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _DB = init_db(path)
    return _DB


def reset_db(path: Path | str) -> sqlite3.Connection:
    """Cierra la conexión actual y abre una nueva en el path indicado.

    Útil para tests que necesitan una base de datos aislada.
    """
    global _DB
    if _DB is not None:
        try:
            _get_db().close()
        except Exception:
            pass
        _DB = None
    set_db_path(path)
    return get_db()

CATEGORIES = {
    "decision",
    "bugfix",
    "architecture",
    "todo",
    "snippet",
    "note",
    "context",
}


def log(msg: str) -> None:
    """Log a stderr (no contamina stdout del MCP)."""
    print(f"[kimi-memory] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
def init_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error as e:
        log(f"No se pudo activar WAL: {e}")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT,
            project TEXT,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
            uuid TEXT UNIQUE
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content,
            content='memories',
            content_rowid='id'
        )
        """
    )
    # Triggers para mantener FTS5 sincronizado
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content) VALUES ('delete', old.id, old.content);
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content) VALUES ('delete', old.id, old.content);
            INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
        END
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_uuid ON memories(uuid)"
    )
    # Migración: agregar columna uuid si no existe (tablas creadas en versiones anteriores).
    try:
        conn.execute("ALTER TABLE memories ADD COLUMN uuid TEXT UNIQUE")
    except sqlite3.OperationalError:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_tags (
            memory_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            PRIMARY KEY (memory_id, tag),
            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_tags_tag ON memory_tags(tag)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_relations (
            memory_id INTEGER NOT NULL,
            related_memory_id INTEGER NOT NULL,
            PRIMARY KEY (memory_id, related_memory_id),
            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE,
            FOREIGN KEY (related_memory_id) REFERENCES memories(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    return conn


def normalize_category(category: Any) -> str | None:
    if not category:
        return None
    cat = str(category).lower().strip()
    if not cat:
        return None
    # Se permiten categorías personalizadas; las predefinidas son sugerencias.
    return cat


def normalize_tags(tags: Any) -> list[str]:
    """Normaliza una lista de tags: minúsculas, trim, únicos, no vacíos."""
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, (list, tuple, set)):
        return []
    result: set[str] = set()
    for t in tags:
        if t is None:
            continue
        s = str(t).lower().strip()
        if s:
            result.add(s)
    return sorted(result)


def normalize_related_ids(related_ids: Any, memory_id: int | None = None) -> list[int]:
    """Normaliza una lista de IDs relacionados, descartando duplicados y el propio ID."""
    if related_ids is None:
        return []
    if isinstance(related_ids, (int, str)):
        related_ids = [related_ids]
    if not isinstance(related_ids, (list, tuple, set)):
        return []
    result: set[int] = set()
    for rid in related_ids:
        try:
            i = int(rid)
            if i <= 0:
                continue
            if memory_id is not None and i == memory_id:
                continue
            result.add(i)
        except (ValueError, TypeError):
            continue
    return sorted(result)


def generate_uuid() -> str:
    return str(uuid.uuid4())


def ensure_uuid(memory_id: int) -> str:
    """Devuelve el UUID de un recuerdo, generando uno si no existe."""
    memory_id = int(memory_id)
    row = get_db().execute("SELECT uuid FROM memories WHERE id = ?", (memory_id,)).fetchone()
    if not row:
        raise ValueError(f"Recuerdo no encontrado: {memory_id}")
    existing = row["uuid"]
    if existing:
        return existing
    new_uuid = generate_uuid()
    get_db().execute("UPDATE memories SET uuid = ? WHERE id = ?", (new_uuid, memory_id))
    get_db().commit()
    return new_uuid


def set_memory_tags(memory_id: int, tags: list[str]) -> None:
    get_db().execute("DELETE FROM memory_tags WHERE memory_id = ?", (memory_id,))
    for tag in tags:
        get_db().execute(
            "INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)",
            (memory_id, tag),
        )


def get_memory_tags(memory_id: int) -> list[str]:
    rows = get_db().execute(
        "SELECT tag FROM memory_tags WHERE memory_id = ? ORDER BY tag",
        (memory_id,),
    ).fetchall()
    return [r["tag"] for r in rows]


def set_memory_relations(memory_id: int, related_ids: list[int]) -> None:
    get_db().execute("DELETE FROM memory_relations WHERE memory_id = ? OR related_memory_id = ?", (memory_id, memory_id))
    for rid in related_ids:
        # Guardar relación en ambas direcciones para consultas simples.
        get_db().execute(
            "INSERT OR IGNORE INTO memory_relations (memory_id, related_memory_id) VALUES (?, ?)",
            (memory_id, rid),
        )
        get_db().execute(
            "INSERT OR IGNORE INTO memory_relations (memory_id, related_memory_id) VALUES (?, ?)",
            (rid, memory_id),
        )


def get_memory_relations(memory_id: int) -> list[int]:
    rows = get_db().execute(
        "SELECT related_memory_id FROM memory_relations WHERE memory_id = ? ORDER BY related_memory_id",
        (memory_id,),
    ).fetchall()
    return sorted({r["related_memory_id"] for r in rows})


_PRIVATE_TAG_RE = re.compile(r"<private>.*?</private>", re.DOTALL | re.IGNORECASE)


_RELATIVE_TIME_RE = re.compile(r"^(\d+)\s*(s|m|h|d|w|mo|y)$", re.IGNORECASE)


def parse_timestamp(value: Any) -> int | None:
    """Convierte una fecha a timestamp Unix.

    Soporta:
    - Timestamp Unix (int o string numérico).
    - ISO 8601: 2026-08-09 o 2026-08-09T10:00:00.
    - Relativas: 7d, 1h, 30m, 2w, 3mo, 1y.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return None

    # Timestamp puro
    if s.isdigit():
        return int(s)

    # Relativa, ej: 7d, 1h, 30m, 2w, 3mo, 1y
    match = _RELATIVE_TIME_RE.match(s)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        delta_kwargs: dict[str, int] = {}
        if unit == "s":
            delta_kwargs["seconds"] = amount
        elif unit == "m":
            delta_kwargs["minutes"] = amount
        elif unit == "h":
            delta_kwargs["hours"] = amount
        elif unit == "d":
            delta_kwargs["days"] = amount
        elif unit == "w":
            delta_kwargs["days"] = amount * 7
        elif unit == "mo":
            delta_kwargs["days"] = amount * 30
        elif unit == "y":
            delta_kwargs["days"] = amount * 365
        return int((datetime.datetime.now() - datetime.timedelta(**delta_kwargs)).timestamp())

    # ISO 8601
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except ValueError:
        raise ValueError(f"Formato de fecha no soportado: {s}")


def strip_private_sections(content: str) -> str:
    """Elimina secciones marcadas como <private>...</private> del contenido.

    Útil para evitar que datos sensibles (contraseñas, tokens, etc.) se
    guarden en la memoria persistente.
    """
    return _PRIVATE_TAG_RE.sub("", content)


def row_to_dict(row: sqlite3.Row, include_extras: bool = True) -> dict[str, Any]:
    d = {
        "id": row["id"],
        "uuid": row["uuid"],
        "content": row["content"],
        "category": row["category"],
        "project": row["project"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_extras:
        d["tags"] = get_memory_tags(row["id"])
        d["related_ids"] = get_memory_relations(row["id"])
    return d


def add_memory(
    content: str,
    category: str | None = None,
    project: str | None = None,
    tags: Any = None,
    related_ids: Any = None,
) -> dict[str, Any]:
    if not content or not str(content).strip():
        raise ValueError("content no puede estar vacío")
    cleaned = strip_private_sections(content).strip()
    if not cleaned:
        return {"id": None, "added": False, "reason": "El contenido quedó vacío tras eliminar secciones <private>."}
    cat = normalize_category(category)
    proj = str(project).strip() if project else None
    normalized_tags = normalize_tags(tags)
    normalized_related = normalize_related_ids(related_ids)
    new_uuid = generate_uuid()
    now = int(time.time())
    cur = get_db().execute(
        "INSERT INTO memories (content, category, project, created_at, updated_at, uuid) VALUES (?, ?, ?, ?, ?, ?)",
        (cleaned, cat, proj, now, now, new_uuid),
    )
    memory_id = cur.lastrowid
    set_memory_tags(memory_id, normalized_tags)
    set_memory_relations(memory_id, normalized_related)
    get_db().commit()
    _maybe_sync()
    return {"id": memory_id, "added": True}


def search_memories(
    query: str,
    limit: int = 10,
    project: str | None = None,
    since: Any = None,
    before: Any = None,
    after: Any = None,
    tags: Any = None,
) -> list[dict[str, Any]]:
    normalized_tags = normalize_tags(tags)
    if not query or not str(query).strip():
        return recent_memories(limit=limit, tags=normalized_tags)
    q = str(query).strip()
    limit = max(1, min(int(limit), 100))

    # Filtros de fecha
    since_ts = parse_timestamp(since)
    before_ts = parse_timestamp(before)
    after_ts = parse_timestamp(after)
    # 'since' es alias de 'after' (inclusive)
    start_ts = after_ts if after_ts is not None else since_ts

    sql = """
        SELECT m.id, m.uuid, m.content, m.category, m.project, m.created_at,
               m.updated_at, rank AS score
        FROM memories_fts f
        JOIN memories m ON m.id = f.rowid
        WHERE memories_fts MATCH ?
    """
    params: list[Any] = [q]
    if project:
        sql += " AND m.project = ?"
        params.append(project)
    if start_ts is not None:
        sql += " AND m.created_at >= ?"
        params.append(start_ts)
    if before_ts is not None:
        sql += " AND m.created_at <= ?"
        params.append(before_ts)
    if normalized_tags:
        placeholders = ",".join("?" * len(normalized_tags))
        sql += f""" AND m.id IN (
            SELECT memory_id FROM memory_tags
            WHERE tag IN ({placeholders})
            GROUP BY memory_id
            HAVING COUNT(DISTINCT tag) = ?
        )"""
        params.extend(normalized_tags)
        params.append(len(normalized_tags))
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    rows = get_db().execute(sql, params).fetchall()
    return [_result_with_snippet(row) for row in rows]


def get_memories(ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    rows = get_db().execute(
        f"SELECT * FROM memories WHERE id IN ({placeholders}) ORDER BY id",
        [int(i) for i in ids],
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def recent_memories(limit: int = 10, tags: list[str] | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    normalized_tags = normalize_tags(tags)
    if normalized_tags:
        placeholders = ",".join("?" * len(normalized_tags))
        sql = f"""
            SELECT m.* FROM memories m
            WHERE m.id IN (
                SELECT memory_id FROM memory_tags
                WHERE tag IN ({placeholders})
                GROUP BY memory_id
                HAVING COUNT(DISTINCT tag) = ?
            )
            ORDER BY m.created_at DESC LIMIT ?
        """
        params = [*normalized_tags, len(normalized_tags), limit]
    else:
        sql = "SELECT * FROM memories ORDER BY created_at DESC, id DESC LIMIT ?"
        params = (limit,)
    rows = get_db().execute(sql, params).fetchall()
    return [row_to_dict(row) for row in rows]


def timeline_memory(memory_id: int, window: int = 3) -> list[dict[str, Any]]:
    mid = int(memory_id)
    window = max(1, min(int(window), 50))
    rows = get_db().execute(
        "SELECT * FROM memories WHERE id BETWEEN ? AND ? ORDER BY id",
        (mid - window, mid + window),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def update_memory(
    memory_id: int,
    content: str | None = None,
    category: str | None = None,
    project: str | None = None,
    tags: Any = None,
    related_ids: Any = None,
) -> dict[str, Any]:
    memory_id = int(memory_id)
    row = get_db().execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    if not row:
        return {"updated": False, "id": memory_id, "reason": "Recuerdo no encontrado."}

    new_content = content if content is not None else row["content"]
    cleaned = strip_private_sections(new_content).strip()
    if not cleaned:
        return {"updated": False, "id": memory_id, "reason": "El contenido quedó vacío tras eliminar secciones <private>."}

    new_category = normalize_category(category) if category is not None else row["category"]
    new_project = str(project).strip() if project is not None else row["project"]
    now = int(time.time())

    get_db().execute(
        "UPDATE memories SET content = ?, category = ?, project = ?, updated_at = ? WHERE id = ?",
        (cleaned, new_category, new_project, now, memory_id),
    )

    normalized_tags = normalize_tags(tags)
    normalized_related = normalize_related_ids(related_ids, memory_id=memory_id)
    set_memory_tags(memory_id, normalized_tags)
    set_memory_relations(memory_id, normalized_related)
    get_db().commit()
    _maybe_sync()
    return {"updated": True, "id": memory_id}


def delete_memory(memory_id: int) -> dict[str, Any]:
    cur = get_db().execute("DELETE FROM memories WHERE id = ?", (int(memory_id),))
    get_db().commit()
    _maybe_sync()
    return {"deleted": cur.rowcount > 0, "id": int(memory_id)}


# ---------------------------------------------------------------------------
# Sincronización via Git
# ---------------------------------------------------------------------------
def get_git_repo() -> Path | None:
    """Devuelve el path al repo Git configurado, o None si no hay."""
    raw = os.environ.get("KIMI_MEMORY_GIT_REPO", "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_dir():
        return None
    return path


def git_run(repo: Path, args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = ["git", "-C", str(repo)] + args
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            timeout=60,
        )
    except Exception as e:
        log(f"Git command failed: {' '.join(cmd)} — {e}")
        # Devolver un CompletedProcess falso para simplificar el manejo posterior.
        result = subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(e))
        return result


def _parse_frontmatter_list(value: str) -> list[str]:
    """Parsea una lista en formato YAML simple: [a, b] o ['a', 'b']."""
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        if not inner:
            return []
        items = []
        for part in inner.split(","):
            part = part.strip()
            if (part.startswith("'") and part.endswith("'")) or (part.startswith('"') and part.endswith('"')):
                part = part[1:-1]
            if part:
                items.append(part)
        return items
    return []


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extrae frontmatter YAML simple y el cuerpo de un archivo Markdown."""
    meta: dict[str, Any] = {}
    if not text.startswith("---"):
        return meta, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return meta, text
    fm_text = parts[1].strip()
    body = parts[2].strip()
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value.startswith("["):
            meta[key] = _parse_frontmatter_list(value)
        elif value.startswith("'") and value.endswith("'"):
            meta[key] = value[1:-1]
        elif value.startswith('"') and value.endswith('"'):
            meta[key] = value[1:-1]
        elif value.isdigit():
            meta[key] = int(value)
        elif value.lower() in ("true", "false"):
            meta[key] = value.lower() == "true"
        else:
            meta[key] = value
    return meta, body


def _format_frontmatter_list(items: list[Any]) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(f'"{str(item)}"' for item in items) + "]"


def export_to_git(repo: Path) -> dict[str, Any]:
    """Exporta todos los recuerdos como archivos Markdown en el repo Git."""
    memories_dir = repo / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    rows = get_db().execute("SELECT * FROM memories").fetchall()
    exported_uuids: set[str] = set()

    for row in rows:
        memory_id = row["id"]
        muuid = row["uuid"] or ensure_uuid(memory_id)
        exported_uuids.add(muuid)
        tags = get_memory_tags(memory_id)
        related_ids = get_memory_relations(memory_id)
        related_uuids = []
        for rid in related_ids:
            rrow = get_db().execute("SELECT uuid FROM memories WHERE id = ?", (rid,)).fetchone()
            if rrow and rrow["uuid"]:
                related_uuids.append(rrow["uuid"])

        frontmatter = {
            "uuid": muuid,
            "category": row["category"] or "",
            "project": row["project"] or "",
            "tags": tags,
            "related_uuids": related_uuids,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        fm_lines = ["---"]
        for key, value in frontmatter.items():
            if isinstance(value, list):
                fm_lines.append(f"{key}: {_format_frontmatter_list(value)}")
            elif isinstance(value, str):
                fm_lines.append(f'{key}: "{value}"')
            else:
                fm_lines.append(f"{key}: {value}")
        fm_lines.append("---")

        content = "\n".join(fm_lines) + "\n\n" + (row["content"] or "")
        (memories_dir / f"{muuid}.md").write_text(content, encoding="utf-8")

    # Borrar archivos de recuerdos que ya no existen localmente.
    for f in memories_dir.glob("*.md"):
        if f.stem not in exported_uuids:
            f.unlink()

    return {"exported": len(rows)}


def import_from_git(repo: Path) -> dict[str, Any]:
    """Importa recuerdos desde archivos Markdown en el repo Git."""
    memories_dir = repo / "memories"
    if not memories_dir.exists():
        return {"imported": 0}

    files = sorted(memories_dir.glob("*.md"))
    imported = 0
    uuid_to_id: dict[str, int] = {}

    # Primera pasada: importar/actualizar recuerdos.
    for f in files:
        text = f.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        muuid = meta.get("uuid")
        if not muuid:
            continue
        content = body.strip()
        if not content:
            continue
        cleaned = strip_private_sections(content).strip()
        if not cleaned:
            continue

        cat = normalize_category(meta.get("category"))
        proj = str(meta.get("project")).strip() if meta.get("project") else None
        tags = [t.lower().strip() for t in meta.get("tags", []) if t]
        created = int(meta.get("created_at", 0)) or int(time.time())
        updated = int(meta.get("updated_at", 0)) or created

        existing = get_db().execute("SELECT id, updated_at FROM memories WHERE uuid = ?", (muuid,)).fetchone()
        if existing:
            if updated > existing["updated_at"]:
                get_db().execute(
                    "UPDATE memories SET content = ?, category = ?, project = ?, created_at = ?, updated_at = ? WHERE uuid = ?",
                    (cleaned, cat, proj, created, updated, muuid),
                )
                memory_id = existing["id"]
            else:
                memory_id = existing["id"]
        else:
            cur = get_db().execute(
                "INSERT INTO memories (content, category, project, created_at, updated_at, uuid) VALUES (?, ?, ?, ?, ?, ?)",
                (cleaned, cat, proj, created, updated, muuid),
            )
            memory_id = cur.lastrowid

        uuid_to_id[muuid] = memory_id
        set_memory_tags(memory_id, tags)
        imported += 1

    # Segunda pasada: establecer relaciones por UUID.
    for f in files:
        text = f.read_text(encoding="utf-8")
        meta, _ = _parse_frontmatter(text)
        muuid = meta.get("uuid")
        if not muuid or muuid not in uuid_to_id:
            continue
        memory_id = uuid_to_id[muuid]
        related_uuids = [u for u in meta.get("related_uuids", []) if u in uuid_to_id]
        related_ids = [uuid_to_id[u] for u in related_uuids]
        set_memory_relations(memory_id, related_ids)

    get_db().commit()
    return {"imported": imported}


def _maybe_sync() -> None:
    """Sincroniza cambios locales con Git si está configurado. No bloquea."""
    repo = get_git_repo()
    if repo:
        try:
            sync_git(repo, full=False)
        except Exception as e:
            log(f"Sync automático falló: {e}")


def sync_git(repo: Path | None = None, full: bool = False) -> dict[str, Any]:
    """Sincroniza la memoria con un repo Git.

    full=True hace pull, import, export, commit y push.
    full=False solo exporta y commitea los cambios locales.
    """
    repo = repo or get_git_repo()
    if not repo:
        return {"synced": False, "reason": "KIMI_MEMORY_GIT_REPO no configurado."}

    if not (repo / ".git").is_dir():
        return {"synced": False, "reason": f"{repo} no es un repo Git."}

    result: dict[str, Any] = {"repo": str(repo), "full": full}

    if full:
        pull = git_run(repo, ["pull", "--rebase", "--autostash"])
        result["pull"] = {"ok": pull.returncode == 0, "stderr": pull.stderr.strip()}
        if pull.returncode == 0:
            imported = import_from_git(repo)
            result["import"] = imported

    exported = export_to_git(repo)
    result["export"] = exported

    status = git_run(repo, ["status", "--porcelain"])
    if status.stdout.strip():
        git_run(repo, ["add", "."])
        timestamp = datetime.datetime.now().isoformat()
        commit = git_run(repo, ["commit", "-m", f"kimi-memory sync {timestamp}"])
        result["commit"] = {"ok": commit.returncode == 0, "stderr": commit.stderr.strip()}

        if full:
            push = git_run(repo, ["push"])
            result["push"] = {"ok": push.returncode == 0, "stderr": push.stderr.strip()}
    else:
        result["commit"] = {"ok": True, "stderr": "Sin cambios para commitear."}

    result["synced"] = True
    return result


def export_memories(project: str | None = None, path: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM memories"
    params: list[Any] = []
    if project:
        sql += " WHERE project = ?"
        params.append(project)
    sql += " ORDER BY created_at DESC"
    rows = get_db().execute(sql, params).fetchall()
    data = [row_to_dict(row) for row in rows]
    result: dict[str, Any] = {"count": len(data), "memories": data}
    if path:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        result["path"] = str(target)
    return result


def import_memories(data: Any, mode: str = "merge") -> dict[str, Any]:
    """Importa recuerdos desde una lista o desde un path a un archivo JSON.

    mode:
    - "merge" (default): agrega los recuerdos sin borrar los existentes.
    - "replace": borra todos los recuerdos existentes antes de importar.
    """
    items: list[dict[str, Any]] = []
    if isinstance(data, str):
        source = Path(data).expanduser()
        if not source.exists():
            raise FileNotFoundError(f"No se encontró el archivo: {source}")
        items = json.loads(source.read_text(encoding="utf-8"))
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("data debe ser una lista de recuerdos o una ruta a un archivo JSON")

    if not isinstance(items, list):
        raise ValueError("El JSON debe contener una lista de recuerdos")

    if str(mode).lower() == "replace":
        get_db().execute("DELETE FROM memories")
        get_db().execute("DELETE FROM memories_fts")
        get_db().commit()

    now = int(time.time())
    imported = 0
    id_map: dict[int, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        cleaned = strip_private_sections(content).strip()
        if not cleaned:
            continue
        cat = normalize_category(item.get("category"))
        proj = str(item.get("project")).strip() if item.get("project") else None
        created = int(item.get("created_at", now))
        updated = int(item.get("updated_at", created))
        original_id = item.get("id")

        if isinstance(original_id, int):
            existing = get_db().execute("SELECT 1 FROM memories WHERE id = ?", (original_id,)).fetchone()
            if existing:
                original_id = None

        if isinstance(original_id, int):
            get_db().execute(
                "INSERT INTO memories (id, content, category, project, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (original_id, cleaned, cat, proj, created, updated),
            )
            memory_id = original_id
        else:
            cur = get_db().execute(
                "INSERT INTO memories (content, category, project, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (cleaned, cat, proj, created, updated),
            )
            memory_id = cur.lastrowid

        id_map[int(item.get("id", memory_id))] = memory_id
        set_memory_tags(memory_id, normalize_tags(item.get("tags")))
        imported += 1

    # Segunda pasada: establecer relaciones usando el mapeo de IDs.
    for item in items:
        if not isinstance(item, dict):
            continue
        original_id = item.get("id")
        if not isinstance(original_id, int):
            continue
        memory_id = id_map.get(original_id)
        if memory_id is None:
            continue
        related = normalize_related_ids(item.get("related_ids"), memory_id=memory_id)
        mapped_related = [id_map.get(rid, rid) for rid in related if rid in id_map]
        set_memory_relations(memory_id, mapped_related)

    get_db().commit()
    return {"imported": imported}


def _result_with_snippet(row: sqlite3.Row) -> dict[str, Any]:
    d = row_to_dict(row)
    content = d["content"]
    d["snippet"] = content if len(content) <= 200 else content[:200].rstrip() + "…"
    d["score"] = row["score"]
    return d


# ---------------------------------------------------------------------------
# Definición de herramientas MCP
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "memory_add",
        "description": (
            "Guarda una observación, decisión o contexto en la memoria persistente. "
            "Úsalo después de resolver un bug, tomar una decisión de diseño, o encontrar "
            "información importante que quieras recordar en sesiones futuras. "
            "Envuelve datos sensibles en <private>...</private> para que no se guarden."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Texto completo del recuerdo a guardar.",
                },
                "category": {
                    "type": "string",
                    "description": "Tipo de recuerdo. Puede ser una de las sugeridas (decision, bugfix, architecture, todo, snippet, note, context) o cualquier categoría personalizada.",
                },
                "project": {
                    "type": "string",
                    "description": "Nombre del proyecto al que pertenece (opcional).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de tags para clasificar el recuerdo (opcional).",
                },
                "related_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "IDs de recuerdos relacionados (opcional).",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "memory_update",
        "description": (
            "Actualiza un recuerdo existente, incluyendo su contenido, categoría, "
            "proyecto, tags y relaciones."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "ID del recuerdo a actualizar.",
                },
                "content": {
                    "type": "string",
                    "description": "Nuevo contenido del recuerdo.",
                },
                "category": {
                    "type": "string",
                    "description": "Nueva categoría.",
                },
                "project": {
                    "type": "string",
                    "description": "Nuevo proyecto.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista completa de tags (reemplaza los existentes).",
                },
                "related_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Lista completa de IDs relacionados (reemplaza los existentes).",
                },
            },
            "required": ["id"],
        },
    },
    {
        "name": "memory_search",
        "description": (
            "Busca recuerdos relevantes por texto libre usando búsqueda full-text. "
            "Empieza siempre por esta herramienta cuando necesites recuperar contexto."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Consulta en lenguaje natural o palabras clave.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Máximo de resultados (1-100).",
                },
                "project": {
                    "type": "string",
                    "description": "Filtrar por proyecto (opcional).",
                },
                "since": {
                    "type": "string",
                    "description": "Fecha mínima: ISO 8601 (2026-08-09) o relativa (7d, 1h, 30m, 2w, 3mo, 1y). Alias de 'after'.",
                },
                "before": {
                    "type": "string",
                    "description": "Fecha máxima: ISO 8601 o relativa.",
                },
                "after": {
                    "type": "string",
                    "description": "Fecha mínima: ISO 8601 o relativa. Igual que 'since'.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filtrar por tags (todos deben estar presentes).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_get",
        "description": (
            "Obtiene el contenido completo de uno o varios recuerdos por sus IDs. "
            "Úsalo después de memory_search para leer en detalle los resultados relevantes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Lista de IDs de recuerdos.",
                },
            },
            "required": ["ids"],
        },
    },
    {
        "name": "memory_recent",
        "description": (
            "Devuelve los recuerdos más recientes. Útil para repasar lo último que pasó "
            "cuando retomas una sesión."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Máximo de resultados.",
                },
            },
        },
    },
    {
        "name": "memory_timeline",
        "description": (
            "Muestra recuerdos cercanos a un ID dado (contexto cronológico). "
            "Útil para entender qué pasaba antes/después de una observación concreta."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "ID del recuerdo central.",
                },
                "window": {
                    "type": "integer",
                    "default": 3,
                    "description": "Cuántos recuerdos antes y después mostrar.",
                },
            },
            "required": ["id"],
        },
    },
    {
        "name": "memory_delete",
        "description": "Elimina un recuerdo por ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "ID del recuerdo a eliminar.",
                },
            },
            "required": ["id"],
        },
    },
    {
        "name": "memory_export",
        "description": (
            "Exporta todos los recuerdos (o los de un proyecto) a JSON. "
            "Úsalo para hacer backup o migrar la memoria a otra máquina."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "Filtrar por proyecto (opcional).",
                },
                "path": {
                    "type": "string",
                    "description": "Ruta donde guardar el JSON (opcional). Si no se indica, devuelve el JSON en la respuesta.",
                },
            },
        },
    },
    {
        "name": "memory_sync",
        "description": (
            "Sincroniza la memoria con el repositorio Git configurado en "
            "KIMI_MEMORY_GIT_REPO. Hace pull, importa cambios remotos, exporta "
            "los recuerdos locales como archivos Markdown, commitea y hace push."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "memory_import",
        "description": (
            "Importa recuerdos desde una lista JSON o desde un archivo JSON. "
            "Modo 'merge' agrega sin borrar; modo 'replace' borra todo antes de importar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "data": {
                    "description": "Lista de recuerdos o ruta a un archivo JSON.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["merge", "replace"],
                    "default": "merge",
                    "description": "'merge' agrega; 'replace' borra todo antes de importar.",
                },
            },
            "required": ["data"],
        },
    },
]


# ---------------------------------------------------------------------------
# JSON-RPC / MCP
# ---------------------------------------------------------------------------
def send_message(msg: dict[str, Any]) -> None:
    data = json.dumps(msg, ensure_ascii=False)
    sys.stdout.write(data + "\n")
    sys.stdout.flush()


def make_result(id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def make_error(id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def handle_request(req: dict[str, Any]) -> None:
    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params", {}) or {}

    try:
        if method == "initialize":
            send_message(
                make_result(
                    req_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "kimi-memory",
                            "version": "1.0.0",
                        },
                    },
                )
            )
            return

        if method == "notifications/initialized":
            # Notificación, no requiere respuesta
            return

        if method == "ping":
            send_message(make_result(req_id, {}))
            return

        if method == "tools/list":
            send_message(make_result(req_id, {"tools": TOOLS}))
            return

        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments", {}) or {}
            result = dispatch_tool(name, args)
            send_message(
                make_result(
                    req_id,
                    {
                        "content": [
                            {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                        ],
                        "isError": False,
                    },
                )
            )
            return

        send_message(make_error(req_id, -32601, f"Método desconocido: {method}"))
    except Exception as e:
        log(f"Error en {method}: {e}")
        send_message(make_error(req_id, -32603, f"Error interno: {e}"))


def dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "memory_add":
        return add_memory(
            content=args["content"],
            category=args.get("category"),
            project=args.get("project"),
            tags=args.get("tags"),
            related_ids=args.get("related_ids"),
        )
    if name == "memory_search":
        return search_memories(
            query=args["query"],
            limit=args.get("limit", 10),
            project=args.get("project"),
            since=args.get("since"),
            before=args.get("before"),
            after=args.get("after"),
            tags=args.get("tags"),
        )
    if name == "memory_get":
        return get_memories(args["ids"])
    if name == "memory_recent":
        return recent_memories(limit=args.get("limit", 10))
    if name == "memory_timeline":
        return timeline_memory(memory_id=args["id"], window=args.get("window", 3))
    if name == "memory_update":
        return update_memory(
            memory_id=args["id"],
            content=args.get("content"),
            category=args.get("category"),
            project=args.get("project"),
            tags=args.get("tags"),
            related_ids=args.get("related_ids"),
        )
    if name == "memory_delete":
        return delete_memory(args["id"])
    if name == "memory_export":
        return export_memories(
            project=args.get("project"),
            path=args.get("path"),
        )
    if name == "memory_import":
        return import_memories(
            data=args["data"],
            mode=args.get("mode", "merge"),
        )
    if name == "memory_sync":
        return sync_git(full=True)
    raise ValueError(f"Herramienta desconocida: {name}")


def main() -> None:
    try:
        log(f"Iniciando. DB: {get_db_path()}")
        repo = get_git_repo()
        if repo:
            log(f"Sincronizando con Git: {repo}")
            try:
                sync_git(repo, full=True)
            except Exception as e:
                log(f"Sync inicial falló: {e}")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as e:
                log(f"JSON inválido: {e}")
                send_message(make_error(None, -32700, "Parse error"))
                continue
            try:
                handle_request(req)
            except Exception as e:
                log(f"Error no manejado en {req.get('method', '?')}: {e}")
                send_message(
                    make_error(req.get("id"), -32603, f"Error interno: {e}")
                )
    except Exception as e:
        log(f"Error fatal en el loop principal: {e}")
        raise


if __name__ == "__main__":
    main()
