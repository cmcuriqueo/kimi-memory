# Changelog

Todos los cambios notables se documentan en este archivo.

## [Unreleased]

### Added
- Soporte para tags `<private>...</private>` en `memory_add`: el contenido marcado como privado se elimina antes de guardar, evitando que datos sensibles persistan.
- Progressive disclosure en `SKILL.md`: flujo recomendado `memory_search` → `memory_timeline` → `memory_get` para ahorrar tokens.
- Filtros por fecha en `memory_search`: soporta `since`/`after` y `before` en formato ISO 8601 o relativo (`7d`, `1h`, `30m`, `2w`, `3mo`, `1y`).

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
