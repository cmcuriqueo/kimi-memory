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

### Clonar el repo

```bash
git clone https://github.com/TU_USUARIO/kimi-memory.git
cd kimi-memory
```

### Bash / Git Bash / WSL / macOS / Linux

```bash
./install.sh
```

### PowerShell (Windows)

```powershell
.\install.ps1
```

Los instaladores:
1. Verifican Python y FTS5.
2. Copian el plugin a `~/.kimi-code/plugins/kimi-memory/`.
3. Copian el skill a `~/.kimi/skills/kimi-memory/`.
4. Registran el servidor MCP en `~/.kimi/mcp.json`.

> ⚠️ Reiniciá Kimi Code CLI después de instalar.

## 🧪 Probar

```bash
python test_mcp.py
```

O manualmente:

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
| `memory_export` | Exporta recuerdos a JSON. |
| `memory_import` | Importa recuerdos desde JSON. |

## 📂 Estructura

```
kimi-memory/
├── memory_mcp.py          # Servidor MCP
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

## ⚙️ Configuración

Podés cambiar la ubicación de la base de datos con la variable de entorno `KIMI_MEMORY_DB`:

```bash
export KIMI_MEMORY_DB=/ruta/a/tu/memory.db
```

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
