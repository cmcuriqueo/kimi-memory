# Roadmap / Mejoras pendientes

Este archivo funciona como backlog público. Se van tachando a medida que se implementan y se publican en el changelog.

## 🚀 Quick wins

- [ ] **Categorías personalizables**: permitir que el usuario cree sus propias categorías además de las 7 fijas.
- [ ] **Filtros por fecha en búsquedas**: soportar `since`, `before`, `after` en `memory_search`.
- [ ] **`memory_summary`**: resumir recuerdos de un proyecto para retomar contexto rápido.
- [ ] **Exportar / importar memoria**: backup a JSON/CSV y restauración.
- [ ] **Validaciones y límites**: tamaño máximo de contenido, sanitización y prevención de duplicados exactos.

## ⚙️ Funcionalidad

- [ ] **Tags libres**: además de la categoría única, permitir múltiples tags por recuerdo.
- [ ] **Relaciones entre recuerdos**: `related_ids` para formar una red de conocimiento.
- [ ] **Prioridad / importancia**: score de importancia y ranking en búsquedas.
- [ ] **Memoria por workspace automática**: detectar el directorio de trabajo actual y asociar recuerdos automáticamente.
- [ ] **Auto-backup de la DB**: copias periódicas de `memory.db`.

## 🔥 Alto impacto

- [ ] **Búsqueda semántica con embeddings locales** (opcional, sin romper el modo sin dependencias).
- [ ] **Auto-detección de qué memorizar**: Kimi decide cuándo guardar sin que el usuario lo pida.
- [ ] **Recuperación proactiva de contexto**: al iniciar sesión, sugerir recuerdos relevantes según el tema actual.
- [ ] **Interfaz web local**: UI ligera para ver/editar/buscar recuerdos en el navegador.
- [ ] **Sincronización entre dispositivos**: opción de sincronizar la DB vía storage personal (S3/R2/Git).

## 🛠️ Técnicas

- [x] Forzar UTF-8 en stdio para evitar problemas de encoding en Windows.
- [x] Soporte para `ping` y manejo robusto de errores.
- [ ] Tests unitarios con pytest.
- [ ] Migraciones de schema.
- [ ] Logging configurable.
- [ ] Encriptación opcional de la base de datos.
- [ ] Empaquetado con `pyproject.toml` y publicación en PyPI (opcional).
- [ ] CI/CD básico (GitHub Actions) para tests.
