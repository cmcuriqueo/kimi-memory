# Roadmap / Mejoras pendientes

Backlog inspirado en la comparación con `claude-mem` y las necesidades propias de `kimi-memory`. Se van tachando a medida que se implementan.

## 🎯 Próximas 7 mejoras

1. [x] **Tags `<private>` para privacidad** — Eliminar del contenido todo lo que esté entre `<private>...</private>` antes de guardar, para que datos sensibles no persistan.
2. [x] **Progressive disclosure en SKILL.md** — Reescribir el skill para que el flujo recomendado sea: `memory_search` (índice ligero) → `memory_timeline` (contexto) → `memory_get` (detalle completo), ahorrando tokens.
3. [x] **Filtros por fecha en `memory_search`** — Soportar `since`, `before` y `after` en las búsquedas.
4. [ ] **Exportar / importar memoria a JSON** — Backup y restauración portable de la memoria.
5. [ ] **Categorías personalizables** — Permitir categorías definidas por el usuario, no solo las 7 fijas.
6. [ ] **Hooks de sesión para auto-guardar contexto** — Aprovechar los hooks de Kimi CLI para resumir y guardar automáticamente al finalizar una sesión.
7. [ ] **Web Viewer UI básico** — Servidor HTTP local opcional para ver y buscar recuerdos desde el navegador.

## ✅ Hecho

- [x] Servidor MCP stdio con SQLite + FTS5.
- [x] 6 herramientas MCP básicas.
- [x] Skill e instaladores para Kimi Code CLI.
- [x] Forzar UTF-8 en stdio para Windows.
- [x] Soporte para `ping` y manejo robusto de errores.

## 🧊 Heladera (ideas futuras)

- Búsqueda semántica con embeddings locales.
- Resumen automático con IA.
- Sincronización entre dispositivos.
- Publicación en PyPI / npm.
- Tests unitarios con pytest y CI/CD.
