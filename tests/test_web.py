"""Tests de integración para memory_web.py."""

import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


@pytest.fixture
def web_server(mcp_module):
    import memory_web

    port = 18080
    memory_web.PORT = port
    server = memory_web.HTTPServer(("127.0.0.1", port), memory_web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def _request(url, method="GET", data=None):
    body = None
    headers = {}
    if data is not None:
        body = json_bytes(data)
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read().decode("utf-8")


def json_bytes(obj):
    import json
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def json_loads(text):
    import json
    return json.loads(text)


def test_create_memory(web_server, mcp_module):
    status, body = _request(
        f"{web_server}/api/memories",
        method="POST",
        data={"content": "Decisión de usar SQLite", "category": "decision", "tags": ["sqlite"]},
    )
    assert status == 201
    result = json_loads(body)
    assert result["added"] is True

    status, body = _request(f"{web_server}/api/memories?id={result['id']}")
    assert status == 200
    memories = json_loads(body)
    assert len(memories) == 1
    assert memories[0]["content"] == "Decisión de usar SQLite"
    assert memories[0]["tags"] == ["sqlite"]


def test_search_by_tag(web_server, mcp_module):
    _request(
        f"{web_server}/api/memories",
        method="POST",
        data={"content": "A", "tags": ["auth", "jwt"]},
    )
    _request(
        f"{web_server}/api/memories",
        method="POST",
        data={"content": "B", "tags": ["auth"]},
    )

    status, body = _request(f"{web_server}/api/memories?tags=auth,jwt")
    assert status == 200
    memories = json_loads(body)
    assert len(memories) == 1
    assert memories[0]["content"] == "A"


def test_update_memory(web_server, mcp_module):
    status, body = _request(
        f"{web_server}/api/memories",
        method="POST",
        data={"content": "Original", "tags": ["old"]},
    )
    memory_id = json_loads(body)["id"]

    status, body = _request(
        f"{web_server}/api/memories/{memory_id}",
        method="PUT",
        data={"content": "Actualizado", "tags": ["new"]},
    )
    assert status == 200
    result = json_loads(body)
    assert result["updated"] is True

    status, body = _request(f"{web_server}/api/memories?id={memory_id}")
    memories = json_loads(body)
    assert memories[0]["content"] == "Actualizado"
    assert memories[0]["tags"] == ["new"]


def test_delete_memory(web_server, mcp_module):
    status, body = _request(
        f"{web_server}/api/memories",
        method="POST",
        data={"content": "Para borrar"},
    )
    memory_id = json_loads(body)["id"]

    status, _ = _request(f"{web_server}/api/memories/{memory_id}", method="DELETE")
    assert status == 200

    status, body = _request(f"{web_server}/api/memories?id={memory_id}")
    memories = json_loads(body)
    assert memories == []


def test_index_page(web_server):
    status, body = _request(web_server)
    assert status == 200
    assert "Kimi Memory" in body


def test_export(web_server, mcp_module):
    _request(
        f"{web_server}/api/memories",
        method="POST",
        data={"content": "Exportable", "tags": ["x"]},
    )
    status, body = _request(f"{web_server}/api/export")
    assert status == 200
    data = json_loads(body)
    assert len(data) >= 1
    assert any(m["content"] == "Exportable" for m in data)
