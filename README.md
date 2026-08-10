# 🧠 Kimi Memory

Memoria persistente minimalista para **Kimi Code CLI**.

Guarda decisiones, bugfixes, snippets y contexto entre sesiones usando **SQLite + FTS5**. Sin dependencias externas: solo Python 3.10+.

## ✨ Características

- 🗄️ Almacenamiento local en SQLite.
- 🔍 Búsqueda full-text rápida (FTS5).
- 🚫 Sin dependencias externas.
- 🪟 Funciona en Windows, macOS y Linux.
- 🔌 Servidor MCP sobre stdio (JSON-RPC 2.0).
- 🧩 Skill + plugin opcional para Kimi Code CLI.

## 🚀 Instalación

### Con npx (recomendado)

```bash
npx kimi-memory install
```

Con el hook de auto-guardado de sesiones:

```bash
npx kimi-memory install --hook
```

### Desde el repo

```bash
git clone https://github.com/cmcuriqueo/kimi-memory.git
cd kimi-memory
./install.sh       # bash / Git Bash / WSL / macOS / Linux
# o
.\install.ps1      # PowerShell (Windows)
```

Los instaladores:
1. Verifican Python y FTS5.
2. Copian el plugin a `~/.kimi-code/plugins/kimi-memory/`.
3. Copian el skill a `~/.kimi/skills/kimi-memory/`.
4. Registran el servidor MCP en `~/.kimi/mcp.json`.
5. Opcionalmente configuran el hook `SessionEnd` en `~/.kimi/config.toml`.

> ⚠️ Reiniciá Kimi Code CLI después de instalar.

## 🧪 Tests

```bash
# Instalar dependencias de desarrollo
pip install -e ".[dev]"

# Correr tests
pytest
```

También podés probar el servidor MCP manualmente:

```bash
python -u memory_mcp.py
```

y enviá por stdin:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"kimi","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
```

## 🛠️ Herramientas MCP

| Herramienta | Descripción |
|---|---|
| `memory_add` | Guarda un recuerdo. |
| `memory_search` | Busca recuerdos por texto libre. |
| `memory_get` | Obtiene recuerdos por ID. |
| `memory_recent` | Devuelve los recuerdos más recientes. |
| `memory_timeline` | Muestra recuerdos cercanos a un ID. |
| `memory_delete` | Elimina un recuerdo por ID. |
| `memory_update` | Actualiza contenido, categoría, proyecto, tags y relaciones. |
| `memory_export` | Exporta recuerdos a JSON. |
| `memory_import` | Importa recuerdos desde JSON. |

## 📂 Estructura

```
kimi-memory/
├── memory_mcp.py          # Servidor MCP
├── memory_web.py          # Visor web local
├── test_mcp.py            # Tests manuales
├── skills/
│   └── kimi-memory/
│       └── SKILL.md       # Instrucciones para Kimi
├── kimi.plugin.json       # Manifest del plugin
├── install.sh             # Instalador bash
├── install.ps1            # Instalador PowerShell
├── example-mcp-config.json# Ejemplo de config MCP
├── CHANGELOG.md
├── TODO.md
└── README.md
```

## 🔄 Sincronización via Git

Podés sincronizar tu memoria entre dispositivos usando un repositorio Git. Cada recuerdo se exporta como un archivo Markdown con frontmatter YAML en el repo.

```bash
# Crear o clonar un repo Git
export KIMI_MEMORY_GIT_REPO=/ruta/a/tu/repo-de-memoria
```

Cuando `KIMI_MEMORY_GIT_REPO` está configurado:

- Al iniciar el servidor MCP se hace `pull → import → export → commit → push`.
- Cada `memory_add`/`memory_update`/`memory_delete` exporta y commitea automáticamente.
- La herramienta `memory_sync` permite sincronizar manualmente.

Requisitos:

- Git instalado y en PATH.
- `user.name` y `user.email` configurados.
- El repo debe tener un remote configurado para push/pull (SSH o HTTPS con credenciales).

## ⚙️ Configuración

Podés cambiar la ubicación de la base de datos con la variable de entorno `KIMI_MEMORY_DB`:

```bash
export KIMI_MEMORY_DB=/ruta/a/tu/memory.db
```

## 🌐 Visor web

Podés levantar una interfaz web local para ver, buscar, agregar, editar y eliminar recuerdos, con renderizado Markdown y una vista de grafo:

```bash
python ~/.kimi-code/plugins/kimi-memory/memory_web.py
```

Por defecto se abre en **http://127.0.0.1:8080**.

### Características

- 🔍 Búsqueda full-text con filtros por proyecto, categoría y tags.
- 📝 Renderizado Markdown en el contenido de los recuerdos.
- 🕸️ Vista de grafo interactiva para explorar relaciones entre recuerdos.
- 🖊️ Panel lateral de edición inline.
- 📤 Exportación a JSON.

### Variables de entorno

- `KIMI_MEMORY_WEB_PORT` — puerto (default 8080).
- `KIMI_MEMORY_DB` — ruta a la base de datos.

### Endpoints

- `GET /` — interfaz web.
- `GET /api/memories?q=...&project=...&category=...&tags=...` — buscar recuerdos.
- `GET /api/graph?...` — datos de nodos y edges para el grafo.
- `POST /api/memories` — crear recuerdo (con `tags` y `related_ids`).
- `PUT /api/memories/<id>` — editar recuerdo (con `tags` y `related_ids`).
- `DELETE /api/memories/<id>` — eliminar recuerdo.
- `GET /api/export` — descargar JSON.

## 🪝 Hooks (auto-guardar contexto)

Kimi Code CLI puede ejecutar hooks en eventos del ciclo de vida. Kimi Memory incluye un hook unificado (`memory_hook.py`) que guarda automáticamente contexto útil en varios momentos:

| Evento | Qué guarda | Categoría |
|---|---|---|
| `SessionEnd` | Resumen de la sesión (temas, herramientas, cwd). | `session_summary` |
| `PostToolUse` | Archivos modificados con `WriteFile` o `StrReplaceFile`. | `file_change` |
| `UserPromptSubmit` | Prompts del usuario que parecen relevantes (bugs, decisiones, arquitectura, etc.). | `prompt` |
| `PreCompact` | Compactaciones de contexto (trigger y tokens). | `compaction_context` |
| `StopFailure` | Errores al finalizar un turno. | `bugfix` |

### Activación automática

```bash
npx kimi-memory install --hook
```

### Activación manual

Agregá esto a `~/.kimi/config.toml`:

```toml
[[hooks]]
event = "SessionEnd"
command = "python ~/.kimi-code/plugins/kimi-memory/hooks/memory_hook.py"

[[hooks]]
event = "PostToolUse"
matcher = "WriteFile|StrReplaceFile"
command = "python ~/.kimi-code/plugins/kimi-memory/hooks/memory_hook.py"

[[hooks]]
event = "UserPromptSubmit"
command = "python ~/.kimi-code/plugins/kimi-memory/hooks/memory_hook.py"

[[hooks]]
event = "PreCompact"
command = "python ~/.kimi-code/plugins/kimi-memory/hooks/memory_hook.py"

[[hooks]]
event = "StopFailure"
command = "python ~/.kimi-code/plugins/kimi-memory/hooks/memory_hook.py"
```

En Windows reemplazá `~/.kimi-code` por `%USERPROFILE%\\.kimi-code`.

> ⚠️ Los hooks requieren que el plugin esté instalado (ver `install.sh` / `install.ps1`).

## 📊 Benchmarks

El proyecto incluye benchmarks cuantitativos en `tests/benchmarks/` para medir si la memoria realmente ahorra tokens y mejora la calidad de las respuestas.

### Instalar dependencias

```bash
pip install -e ".[dev,benchmark]"
```

### Correr benchmarks

```bash
pytest tests/benchmarks -v
```

### Métricas que se reportan

| Métrica | Qué mide |
|---|---|
| **Ahorro de tokens (%)** | Cuánto se reduce el prompt al recuperar memoria en lugar de repetir contexto. |
| **Precision@3** | De los top-3 resultados de búsqueda, cuántos son realmente relevantes. |
| **Recall@5** | De todos los recuerdos relevantes, cuántos aparecen en top-5. |
| **MRR** | Rank medio del primer resultado relevante. |
| **Cobertura de hechos (%)** | Cuántos hechos clave de la tarea aparecen en la memoria recuperada. |
| **Overhead de búsqueda (%)** | Costo de buscar memoria cuando no hay nada relevante. |

Los benchmarks usan escenarios sintéticos de proyectos reales (autenticación, base de datos, deploy, frontend). No requieren llamadas a APIs externas.

## 🗺️ Roadmap

Ver [`TODO.md`](./TODO.md) para la lista completa de mejoras planificadas.

Algunas ideas destacadas:

- Categorías y tags personalizables.
- Filtros por fecha.
- Búsqueda semántica opcional.
- Interfaz web local.
- Sincronización entre dispositivos.

## 🤝 Contribuir

1. Hacé un fork.
2. Creá una rama: `git checkout -b feature/nueva-mejora`.
3. Commiteá tus cambios.
4. Abrí un PR.

Consultá [`TODO.md`](./TODO.md) para ver qué mejoras están pendientes.

## 🛡️ Seguridad

- La base de datos es texto plano local. **No guardes contraseñas, tokens ni secretos**.
- Si compartís la máquina, protegé `~/.kimi-code/memory.db` con los permisos del sistema operativo.

## 📄 Licencia

MIT. Ver [`LICENSE`](./LICENSE).
