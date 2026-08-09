#!/usr/bin/env python3
"""Web Viewer UI local para Kimi Memory.

Servidor HTTP minimalista (solo stdlib) para ver, buscar, agregar, editar y
eliminar recuerdos desde el navegador.

Uso:
    python memory_web.py

Variables de entorno:
    KIMI_MEMORY_DB      Ruta a la base de datos SQLite.
    KIMI_MEMORY_WEB_PORT Puerto (default: 8080).
"""

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

PLUGIN_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(PLUGIN_DIR))
import memory_mcp  # noqa: E402

PORT = int(os.environ.get("KIMI_MEMORY_WEB_PORT", "8080"))


HTML_PAGE = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Kimi Memory — Web Viewer</title>
  <style>
    :root {
      --bg: #0f172a;
      --panel: #1e293b;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --danger: #f87171;
      --success: #4ade80;
      --border: #334155;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }
    .container { max-width: 960px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 8px; font-size: 1.6rem; }
    .subtitle { color: var(--muted); margin-bottom: 24px; }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
    }
    label { display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 4px; }
    input, textarea, select {
      width: 100%;
      background: var(--bg);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      margin-bottom: 12px;
      font: inherit;
    }
    textarea { min-height: 100px; resize: vertical; }
    .row { display: grid; gap: 12px; grid-template-columns: 1fr 1fr; }
    @media (max-width: 600px) { .row { grid-template-columns: 1fr; } }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    button {
      background: var(--accent);
      color: #0f172a;
      border: none;
      border-radius: 8px;
      padding: 10px 16px;
      font-weight: 600;
      cursor: pointer;
    }
    button.secondary { background: var(--border); color: var(--text); }
    button.danger { background: var(--danger); color: white; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
    .toolbar input { margin: 0; flex: 1; min-width: 180px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
    th { color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .snippet { color: var(--muted); font-size: 0.9rem; }
    .meta { font-size: 0.8rem; color: var(--muted); }
    .badge {
      display: inline-block;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 0.75rem;
      margin-right: 4px;
    }
    .empty { text-align: center; color: var(--muted); padding: 40px 0; }
    .toast {
      position: fixed; bottom: 16px; right: 16px;
      background: var(--success); color: #0f172a;
      padding: 10px 16px; border-radius: 8px; font-weight: 600;
      opacity: 0; transition: opacity 0.3s; pointer-events: none;
    }
    .toast.show { opacity: 1; }
    .toast.error { background: var(--danger); color: white; }
  </style>
</head>
<body>
  <div class="container">
    <h1>🧠 Kimi Memory</h1>
    <p class="subtitle">Visor web local de tu memoria persistente</p>

    <div class="card">
      <h3 id="form-title">Nuevo recuerdo</h3>
      <form id="memory-form">
        <input type="hidden" id="memory-id" />
        <label for="content">Contenido</label>
        <textarea id="content" required placeholder="Escribí el recuerdo..."></textarea>
        <div class="row">
          <div>
            <label for="category">Categoría</label>
            <input id="category" type="text" placeholder="decision, bugfix, note..." />
          </div>
          <div>
            <label for="project">Proyecto</label>
            <input id="project" type="text" placeholder="mi-api" />
          </div>
        </div>
        <div class="actions">
          <button type="submit" id="save-btn">Guardar</button>
          <button type="button" class="secondary" id="cancel-btn" style="display:none">Cancelar</button>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="toolbar">
        <input id="search" type="text" placeholder="Buscar..." />
        <input id="filter-project" type="text" placeholder="Proyecto" />
        <input id="filter-category" type="text" placeholder="Categoría" />
        <button id="btn-search">Buscar</button>
        <button class="secondary" id="btn-export">Exportar JSON</button>
      </div>
      <div id="results">
        <p class="empty">Cargando...</p>
      </div>
    </div>
  </div>

  <div id="toast" class="toast"></div>

  <script>
    const $ = (id) => document.getElementById(id);
    const fmtDate = (ts) => new Date(ts * 1000).toLocaleString();

    async function loadMemories() {
      const params = new URLSearchParams();
      const q = $('search').value.trim();
      const project = $('filter-project').value.trim();
      const category = $('filter-category').value.trim();
      if (q) params.set('q', q);
      if (project) params.set('project', project);
      if (category) params.set('category', category);
      params.set('limit', '100');

      const res = await fetch('/api/memories?' + params.toString());
      const data = await res.json();
      render(data.memories || data);
    }

    function render(memories) {
      const container = $('results');
      if (!memories.length) {
        container.innerHTML = '<p class="empty">No se encontraron recuerdos.</p>';
        return;
      }
      const rows = memories.map(m => `
        <tr>
          <td>
            <div>${escapeHtml(m.content)}</div>
            <div class="meta">${fmtDate(m.created_at)} · ID ${m.id}</div>
          </td>
          <td><span class="badge">${escapeHtml(m.category || 'note')}</span></td>
          <td>${escapeHtml(m.project || '—')}</td>
          <td>
            <button class="secondary" onclick="editMemory(${m.id})">Editar</button>
            <button class="danger" onclick="deleteMemory(${m.id})">Borrar</button>
          </td>
        </tr>
      `).join('');
      container.innerHTML = `<table><thead><tr><th>Contenido</th><th>Categoría</th><th>Proyecto</th><th>Acciones</th></tr></thead><tbody>${rows}</tbody></table>`;
    }

    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }

    $('memory-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = $('memory-id').value;
      const body = {
        content: $('content').value,
        category: $('category').value,
        project: $('project').value,
      };
      const url = id ? `/api/memories/${id}` : '/api/memories';
      const method = id ? 'PUT' : 'POST';
      const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (res.ok) {
        toast(id ? 'Actualizado' : 'Guardado');
        resetForm();
        loadMemories();
      } else {
        toast('Error al guardar', true);
      }
    });

    $('cancel-btn').addEventListener('click', resetForm);
    $('btn-search').addEventListener('click', loadMemories);
    $('btn-export').addEventListener('click', () => { window.location = '/api/export'; });
    $('search').addEventListener('keydown', (e) => { if (e.key === 'Enter') loadMemories(); });

    async function editMemory(id) {
      const res = await fetch('/api/memories?id=' + id);
      const data = await res.json();
      const m = (data.memories || data)[0];
      if (!m) return;
      $('memory-id').value = m.id;
      $('content').value = m.content;
      $('category').value = m.category || '';
      $('project').value = m.project || '';
      $('form-title').textContent = 'Editar recuerdo #' + m.id;
      $('save-btn').textContent = 'Actualizar';
      $('cancel-btn').style.display = '';
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    async function deleteMemory(id) {
      if (!confirm('¿Eliminar recuerdo #' + id + '?')) return;
      const res = await fetch('/api/memories/' + id, { method: 'DELETE' });
      if (res.ok) {
        toast('Eliminado');
        loadMemories();
      } else {
        toast('Error al eliminar', true);
      }
    }

    function resetForm() {
      $('memory-id').value = '';
      $('content').value = '';
      $('category').value = '';
      $('project').value = '';
      $('form-title').textContent = 'Nuevo recuerdo';
      $('save-btn').textContent = 'Guardar';
      $('cancel-btn').style.display = 'none';
    }

    function toast(msg, isError) {
      const t = $('toast');
      t.textContent = msg;
      t.className = 'toast' + (isError ? ' error' : '') + ' show';
      setTimeout(() => t.className = 'toast' + (isError ? ' error' : ''), 2000);
    }

    loadMemories();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silenciar logs de requests.
        pass

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text_response(self, text, status=200, content_type="text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._text_response(HTML_PAGE, content_type="text/html; charset=utf-8")
            return

        if path == "/api/memories":
            memory_id = qs.get("id", [None])[0]
            if memory_id:
                try:
                    result = memory_mcp.get_memories([int(memory_id)])
                except Exception as e:
                    self._json_response({"error": str(e)}, 400)
                    return
            else:
                q = qs.get("q", [""])[0]
                project = qs.get("project", [None])[0]
                category = qs.get("category", [None])[0]
                limit = int(qs.get("limit", ["100"])[0])
                try:
                    result = memory_mcp.search_memories(
                        query=q,
                        limit=limit,
                        project=project,
                    )
                    if category:
                        result = [m for m in result if (m.get("category") or "") == category]
                except Exception as e:
                    self._json_response({"error": str(e)}, 400)
                    return
            self._json_response(result)
            return

        if path == "/api/export":
            try:
                data = memory_mcp.export_memories()
            except Exception as e:
                self._json_response({"error": str(e)}, 400)
                return
            body = json.dumps(data.get("memories", []), ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="kimi-memory.json"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self._json_response({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/memories":
            self._json_response({"error": "Not found"}, 404)
            return
        body = self._read_body()
        try:
            result = memory_mcp.add_memory(
                content=body.get("content", ""),
                category=body.get("category"),
                project=body.get("project"),
            )
        except Exception as e:
            self._json_response({"error": str(e)}, 400)
            return
        self._json_response(result, 201)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "api" or parts[1] != "memories":
            self._json_response({"error": "Not found"}, 404)
            return
        try:
            memory_id = int(parts[2])
        except ValueError:
            self._json_response({"error": "Invalid id"}, 400)
            return
        body = self._read_body()
        now = int(__import__("time").time())
        try:
            memory_mcp.DB.execute(
                "UPDATE memories SET content = ?, category = ?, project = ?, updated_at = ? WHERE id = ?",
                (
                    body.get("content", "").strip(),
                    memory_mcp.normalize_category(body.get("category")),
                    str(body.get("project")).strip() if body.get("project") else None,
                    now,
                    memory_id,
                ),
            )
            memory_mcp.DB.commit()
        except Exception as e:
            self._json_response({"error": str(e)}, 400)
            return
        self._json_response({"updated": True, "id": memory_id})

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "api" or parts[1] != "memories":
            self._json_response({"error": "Not found"}, 404)
            return
        try:
            memory_id = int(parts[2])
        except ValueError:
            self._json_response({"error": "Invalid id"}, 400)
            return
        try:
            result = memory_mcp.delete_memory(memory_id)
        except Exception as e:
            self._json_response({"error": str(e)}, 400)
            return
        self._json_response(result)


def main() -> None:
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[kimi-memory-web] http://127.0.0.1:{PORT}")
    print(f"[kimi-memory-web] DB: {memory_mcp.DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[kimi-memory-web] Cerrando...")
        server.shutdown()


if __name__ == "__main__":
    main()
