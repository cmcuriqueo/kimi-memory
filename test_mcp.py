#!/usr/bin/env python3
"""Cliente de prueba para el servidor MCP Kimi Memory."""

import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent.resolve()
SERVER = PLUGIN_DIR / "memory_mcp.py"


def send(stdin, stdout, method: str, params: dict | None = None, req_id: int = 1):
    req = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        req["params"] = params
    stdin.write(json.dumps(req) + "\n")
    stdin.flush()
    line = stdout.readline().strip()
    return json.loads(line)


def main():
    print(f"Iniciando servidor: {SERVER}")
    proc = subprocess.Popen(
        [sys.executable, "-u", str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "KIMI_MEMORY_DB": str(Path.home() / ".kimi-code" / "memory_test.db")},
    )
    assert proc.stdin and proc.stdout

    try:
        print("\n1) initialize")
        r = send(proc.stdin, proc.stdout, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }, req_id=1)
        print(json.dumps(r, ensure_ascii=False, indent=2))

        print("\n2) tools/list")
        r = send(proc.stdin, proc.stdout, "tools/list", {}, req_id=2)
        print(f"Herramientas: {[t['name'] for t in r['result']['tools']]}")

        print("\n3) memory_add")
        r = send(proc.stdin, proc.stdout, "tools/call", {
            "name": "memory_add",
            "arguments": {
                "content": "Decidimos usar SQLite con FTS5 para la memoria persistente.",
                "category": "decision",
                "project": "kimi-memory",
            },
        }, req_id=3)
        print(r["result"]["content"][0]["text"])

        print("\n4) memory_search")
        r = send(proc.stdin, proc.stdout, "tools/call", {
            "name": "memory_search",
            "arguments": {"query": "SQLite FTS5", "limit": 5},
        }, req_id=4)
        print(r["result"]["content"][0]["text"])

        print("\n5) memory_recent")
        r = send(proc.stdin, proc.stdout, "tools/call", {
            "name": "memory_recent",
            "arguments": {"limit": 5},
        }, req_id=5)
        print(r["result"]["content"][0]["text"])

        print("\n[OK] Todas las pruebas pasaron.")
    finally:
        proc.stdin.close()
        proc.wait(timeout=2)
        test_db = Path.home() / ".kimi-code" / "memory_test.db"
        if test_db.exists():
            test_db.unlink()
            wal = test_db.with_suffix(".db-wal")
            shm = test_db.with_suffix(".db-shm")
            if wal.exists():
                wal.unlink()
            if shm.exists():
                shm.unlink()


if __name__ == "__main__":
    main()
