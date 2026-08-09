---
name: kimi-memory
description: Memoria persistente local para Kimi Code CLI usando SQLite + FTS5. Recupera contexto entre sesiones y guarda decisiones, bugfixes y aprendizajes.
---

# Kimi Memory — Memoria persistente minimalista

Este skill conecta Kimi con una memoria local persistente (SQLite + FTS5) a través de un MCP server propio. La memoria sobrevive entre sesiones, proyectos y reinicios.

## Cuándo usar la memoria

- **Al inicio de cada sesión**: busca contexto relevante con `memory_search` antes de empezar a trabajar.
- **Después de resolver algo importante**: guarda el aprendizaje con `memory_add`.
- **Antes de tomar decisiones de diseño**: busca decisiones previas para mantener consistencia.
- **Cuando retomas un proyecto**: recupera recuerdos recientes con `memory_recent`.
- **Cuando encuentras un bug y su solución**: guárdalo como `bugfix`.

## Flujo de trabajo recomendado

1. **Recuperar contexto**:
   ```
   memory_search(query="autenticación JWT")
   ```
   Revisa los snippets. Si alguno es relevante, obtén el detalle completo:
   ```
   memory_get(ids=[3, 7])
   ```

2. **Trabajar normalmente** en la tarea.

3. **Guardar lo importante**:
   ```
   memory_add(
     content="Decidimos usar PyJWT con RS256. La clave pública se lee de /secrets/jwt.pub.",
     category="decision",
     project="mi-api"
   )
   ```

## Categorías disponibles

| Categoría | Cuándo usarla |
|-----------|---------------|
| `decision` | Decisiones de diseño, arquitectura o estrategia. |
| `bugfix` | Bugs encontrados y cómo se solucionaron. |
| `architecture` | Estructura del proyecto, patrones, convenciones. |
| `todo` | Tareas pendientes o siguientes pasos importantes. |
| `snippet` | Fragmentos de código reutilizables o configuraciones. |
| `note` | Cualquier otra observación útil (categoría por defecto). |
| `context` | Contexto general del proyecto o del usuario. |

## Reglas importantes

- **Sé conciso pero completo** en `content`. Incluye el "qué", el "porqué" y, si aplica, el "cómo".
- **Usa `project`** cuando el recuerdo esté ligado a un proyecto concreto. Si no estás seguro, omítelo.
- **No guardes datos sensibles** (contraseñas, tokens, secretos). La base de datos vive en texto plano local.
- **Si el usuario menciona datos sensibles**, envuélvelos en `<private>...</private>` dentro del `content`. El servidor los eliminará antes de guardar. Ejemplo:
  ```
  Usamos la API key <private>sk-abc123</private> para el servicio de pagos.
  ```
- **Busca antes de preguntar**: si el usuario menciona algo que pudiste haber hecho antes, usa `memory_search` primero.
- **Limpia cuando sea necesario**: usa `memory_delete` para eliminar recuerdos obsoletos o duplicados.

## Comandos útiles para el usuario

- Ver todos los recuerdos recientes: pide al usuario que use `memory_recent`.
- Ver contexto alrededor de un recuerdo: `memory_timeline(id=42, window=5)`.
- Buscar en un proyecto: `memory_search(query="login", project="mi-app")`.

## Ubicación de los datos

La base de datos SQLite se guarda en `~/.kimi-code/memory.db`. Puedes cambiarla con la variable de entorno `KIMI_MEMORY_DB`.
