#!/usr/bin/env python3
"""
Kimi Memory MCP Server — Minimalista, sin dependencias externas.
Memoria persistente para Kimi Code CLI usando SQLite + FTS5.
Comunicación MCP sobre stdio (JSON-RPC 2.0).
"""

import json
import os
import re
import sqlite3
import sys
import time
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
DB_PATH = Path(os.environ.get("KIMI_MEMORY_DB", DEFAULT_DB))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

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
def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
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
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
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
    conn.commit()
    return conn


DB = init_db()


def normalize_category(category: Any) -> str | None:
    if not category:
        return None
    cat = str(category).lower().strip()
    return cat if cat in CATEGORIES else "note"


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "content": row["content"],
        "category": row["category"],
        "project": row["project"],
        "created_at": row["created_at"],
    }


def add_memory(content: str, category: str | None = None, project: str | None = None) -> dict[str, Any]:
    if not content or not str(content).strip():
        raise ValueError("content no puede estar vacío")
    cat = normalize_category(category)
    proj = str(project).strip() if project else None
    now = int(time.time())
    cur = DB.execute(
        "INSERT INTO memories (content, category, project, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (content.strip(), cat, proj, now, now),
    )
    DB.commit()
    return {"id": cur.lastrowid, "added": True}


def search_memories(query: str, limit: int = 10, project: str | None = None) -> list[dict[str, Any]]:
    if not query or not str(query).strip():
        return recent_memories(limit=limit)
    q = str(query).strip()
    limit = max(1, min(int(limit), 100))
    sql = """
        SELECT m.id, m.content, m.category, m.project, m.created_at,
               rank AS score
        FROM memories_fts f
        JOIN memories m ON m.id = f.rowid
        WHERE memories_fts MATCH ?
    """
    params: list[Any] = [q]
    if project:
        sql += " AND m.project = ?"
        params.append(project)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    rows = DB.execute(sql, params).fetchall()
    return [_result_with_snippet(row) for row in rows]


def get_memories(ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    rows = DB.execute(
        f"SELECT * FROM memories WHERE id IN ({placeholders}) ORDER BY id",
        [int(i) for i in ids],
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def recent_memories(limit: int = 10) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    rows = DB.execute(
        "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def timeline_memory(memory_id: int, window: int = 3) -> list[dict[str, Any]]:
    mid = int(memory_id)
    window = max(1, min(int(window), 50))
    rows = DB.execute(
        "SELECT * FROM memories WHERE id BETWEEN ? AND ? ORDER BY id",
        (mid - window, mid + window),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def delete_memory(memory_id: int) -> dict[str, Any]:
    cur = DB.execute("DELETE FROM memories WHERE id = ?", (int(memory_id),))
    DB.commit()
    return {"deleted": cur.rowcount > 0, "id": int(memory_id)}


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
            "información importante que quieras recordar en sesiones futuras."
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
                    "enum": sorted(CATEGORIES),
                    "description": "Tipo de recuerdo (decisión, bugfix, arquitectura, etc.)",
                },
                "project": {
                    "type": "string",
                    "description": "Nombre del proyecto al que pertenece (opcional).",
                },
            },
            "required": ["content"],
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
        )
    if name == "memory_search":
        return search_memories(
            query=args["query"],
            limit=args.get("limit", 10),
            project=args.get("project"),
        )
    if name == "memory_get":
        return get_memories(args["ids"])
    if name == "memory_recent":
        return recent_memories(limit=args.get("limit", 10))
    if name == "memory_timeline":
        return timeline_memory(memory_id=args["id"], window=args.get("window", 3))
    if name == "memory_delete":
        return delete_memory(args["id"])
    raise ValueError(f"Herramienta desconocida: {name}")


def main() -> None:
    try:
        log(f"Iniciando. DB: {DB_PATH}")
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
