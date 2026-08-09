# Changelog

Todos los cambios notables se documentan en este archivo.

## [Unreleased]

### Added
- Tags múltiples y relaciones entre recuerdos:
  - Nuevas tablas `memory_tags` y `memory_relations`.
  - `memory_add` acepta `tags` y `related_ids`.
  - Nueva herramienta `memory_update` para editar recuerdos.
  - `memory_search` soporta filtrar por tags (AND).
  - `memory_get`, `memory_recent` y `memory_timeline` devuelven `tags` y `related_ids`.
  - `memory_import` preserva tags y relaciones.
  - Web Viewer permite ver, filtrar, agregar y editar tags y recuerdos relacionados.
  - Hooks automáticos ahora taggean recuerdos según su tipo y contenido.
- Soporte para tags `<private>...</private>` en `memory_add`: el contenido marcado como privado se elimina antes de guardar, evitando que datos sensibles persistan.
- Progressive disclosure en `SKILL.md`: flujo recomendado `memory_search` → `memory_timeline` → `memory_get` para ahorrar tokens.
- Filtros por fecha en `memory_search`: soporta `since`/`after` y `before` en formato ISO 8601 o relativo (`7d`, `1h`, `30m`, `2w`, `3mo`, `1y`).
- `memory_export` e `memory_import`: backup y restauración de la memoria a/desde JSON.
- Categorías personalizables: el usuario puede usar cualquier categoría, no solo las 7 predefinidas.
- Tests unitarios con pytest (`tests/`) y workflow de CI/CD con GitHub Actions.
- `pyproject.toml` con dependencias de desarrollo.
- Refactorización de `memory_mcp.py` para soportar base de datos aislada en tests (`reset_db`).
- Hook unificado `memory_hook.py` para múltiples eventos:
  - `SessionEnd`: guarda resumen de sesión como `session_summary`.
  - `PostToolUse`: guarda archivos modificados como `file_change`.
  - `UserPromptSubmit`: guarda prompts relevantes como `prompt`.
  - `PreCompact`: guarda contexto de compactación como `compaction_context`.
  - `StopFailure`: guarda errores como `bugfix`.
- Web Viewer UI (`memory_web.py`): servidor HTTP local para ver, buscar, agregar, editar, eliminar y exportar recuerdos desde el navegador.
- Instalador npm (`npx kimi-memory install`): instala todo con un solo comando, con opción `--hook` para activar el hook SessionEnd.

### Fixed
- `memory_search` incluye `updated_at` en el SELECT para evitar error al construir el snippet.

## [0.1.0] - 2026-08-09

### Added
- Servidor MCP `kimi-memory` con SQLite + FTS5.
- Herramientas MCP:
  - `memory_add`
  - `memory_search`
  - `memory_get`
  - `memory_recent`
  - `memory_timeline`
  - `memory_delete`
- Skill para Kimi Code CLI (`skills/kimi-memory/SKILL.md`).
- Instaladores para bash (`install.sh`) y PowerShell (`install.ps1`).
- Tests manuales del servidor MCP (`test_mcp.py`).

### Fixed
- Forzado UTF-8 en `stdout`/`stderr` para evitar fallos de encoding en Windows.
- Agregado soporte para `ping` y manejo robusto de errores en el loop principal.
