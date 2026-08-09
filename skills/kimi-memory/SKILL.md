---
name: kimi-memory
description: Memoria persistente local para Kimi Code CLI usando SQLite + FTS5. Recupera contexto entre sesiones con un flujo progresivo para ahorrar tokens.
---

# Kimi Memory — Memoria persistente

Este skill conecta Kimi con una memoria local persistente (SQLite + FTS5) a través de un MCP server propio. La memoria sobrevive entre sesiones, proyectos y reinicios.

## Flujo de trabajo recomendado (progressive disclosure)

Para no quemar tokens, seguí este orden:

1. **Buscar índice ligero**:
   ```
   memory_search(query="autenticación JWT", project="mi-api", limit=10)
   ```
   Devuelve IDs, snippets cortos y score. NO leas el contenido completo todavía.

   Podés filtrar por fecha con `since`/`after` y `before`:
   ```
   memory_search(query="autenticación JWT", since="7d")
   memory_search(query="login", before="2026-08-01")
   ```
   Formatos soportados: ISO 8601 (`2026-08-09`) o relativos (`7d`, `1h`, `30m`, `2w`, `3mo`, `1y`).

2. **Obtener contexto cronológico** de los IDs interesantes:
   ```
   memory_timeline(id=42, window=3)
   ```
   Úsalo para entender qué pasaba antes/después de una observación clave.

3. **Leer detalle completo solo de lo relevante**:
   ```
   memory_get(ids=[42, 45, 51])
   ```
   Batchá siempre múltiples IDs en una sola llamada.

## Cuándo usar la memoria

- **Al inicio de cada sesión**: ejecutá `memory_search` con el tema actual antes de actuar.
- **Después de resolver algo importante**: guardá el aprendizaje con `memory_add`.
- **Antes de tomar decisiones de diseño**: buscá decisiones previas para mantener consistencia.
- **Cuando retomás un proyecto**: `memory_recent(limit=5)` para ver lo último.

## Reglas de oro

1. **Buscar antes de preguntar**: si el usuario menciona algo que pudiste haber hecho antes, usá `memory_search` primero.
2. **Progresivo**: nunca pidas el contenido completo de todos los resultados de una búsqueda. Filtrá por snippets, usá `memory_timeline`, y recién al final `memory_get`.
3. **Sé conciso pero completo** en `content`: incluí el "qué", el "porqué" y, si aplica, el "cómo".
4. **Usá `project`** cuando el recuerdo esté ligado a un proyecto concreto.
5. **Datos sensibles**: envolvelos en `<private>...</private>` para que no se guarden. Ejemplo:
   ```
   La API key es <private>sk-abc123</private> y vence en 30 días.
   ```
6. **Limpia cuando sea necesario**: usá `memory_delete` para eliminar recuerdos obsoletos o duplicados.

## Categorías

Podés usar cualquier categoría que tenga sentido para tu flujo. Estas son las sugeridas:

| Categoría | Uso |
|---|---|
| `decision` | Decisiones de diseño, arquitectura o estrategia. |
| `bugfix` | Bugs encontrados y cómo se solucionaron. |
| `architecture` | Estructura del proyecto, patrones, convenciones. |
| `todo` | Tareas pendientes o siguientes pasos importantes. |
| `snippet` | Fragmentos de código o configuraciones reutilizables. |
| `context` | Contexto general del proyecto o del usuario. |
| `note` | Cualquier otra observación útil. |

También podés crear categorías propias, por ejemplo: `security`, `refactor`, `deployment`, `meeting`, etc.

## Ubicación de los datos

La base de datos SQLite se guarda en `~/.kimi-code/memory.db`. Podés cambiarla con la variable de entorno `KIMI_MEMORY_DB`.
