"""Escenarios sintéticos para evaluar ahorro de tokens y retrieval.

Cada escenario representa un proyecto con varios recuerdos guardados y una
consulta de seguimiento que debería beneficiarse de la memoria.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class ProjectScenario:
    """Un escenario de proyecto con memoria previa y una tarea de seguimiento."""

    name: str
    project: str
    memories: list[dict]
    query: str
    expected_memory_ids: list[int] | None = None
    expected_facts: list[str] | None = None


# Contextos de proyecto extensos que un usuario tendría que repetir sin memoria.
PROJECT_CONTEXTS: dict[str, list[dict]] = {
    "api-auth": [
        {
            "content": (
                "Decisión de arquitectura: usamos JWT con algoritmo RS256 para autenticación. "
                "El secret se genera con openssl y se rota cada 90 días. "
                "El frontend recibe un access token de 15 minutos y un refresh token de 7 días."
            ),
            "category": "decision",
            "tags": ["auth", "jwt", "security", "rs256"],
        },
        {
            "content": (
                "Convención: todos los endpoints de autenticación viven bajo el prefijo "
                "/api/v1/auth. Los controladores están en src/auth/controllers/."
            ),
            "category": "architecture",
            "tags": ["auth", "api", "convention"],
        },
        {
            "content": (
                "Bugfix: el middleware de auth fallaba con tokens que contenían caracteres UTF-8 "
                "en el payload. Se solucionó normalizando el header antes de decode."
            ),
            "category": "bugfix",
            "tags": ["auth", "jwt", "bugfix", "utf8"],
        },
    ],
    "db-migration": [
        {
            "content": (
                "Base de datos principal: PostgreSQL 16 desplegada en Render. "
                "Usamos SQLAlchemy 2.0 con asyncpg para operaciones asíncronas."
            ),
            "category": "architecture",
            "tags": ["db", "postgres", "sqlalchemy", "render"],
        },
        {
            "content": (
                "Decisión: las migraciones se manejan con Alembic. El comando para crear una "
                "nueva migración es `alembic revision --autogenerate -m 'nombre'`."
            ),
            "category": "decision",
            "tags": ["db", "migration", "alembic"],
        },
        {
            "content": (
                "Convención: todos los modelos heredan de Base declarative en src/models/base.py. "
                "Las tablas usan nombres en snake_case y plural."
            ),
            "category": "architecture",
            "tags": ["db", "model", "convention"],
        },
    ],
    "deploy-pipeline": [
        {
            "content": (
                "Despliegue: la aplicación corre en Fly.io con dos máquinas en regions ord y gru. "
                "El despliegue es automático desde la rama main vía GitHub Actions."
            ),
            "category": "context",
            "tags": ["deploy", "flyio", "ci"],
        },
        {
            "content": (
                "Decisión: usamos Docker multi-stage para reducir el tamaño de la imagen. "
                "La imagen final se basa en python:3.12-slim."
            ),
            "category": "decision",
            "tags": ["deploy", "docker", "python"],
        },
        {
            "content": (
                "Variables de entorno sensibles se inyectan como secrets de Fly.io, nunca en el Dockerfile."
            ),
            "category": "decision",
            "tags": ["deploy", "secrets", "security"],
        },
    ],
    "frontend-style": [
        {
            "content": (
                "Estilo de código frontend: usamos Tailwind CSS con componentes de shadcn/ui. "
                "No se agregan clases arbitrarias sin documentar la excepción."
            ),
            "category": "architecture",
            "tags": ["frontend", "tailwind", "shadcn"],
        },
        {
            "content": (
                "Decisión: el estado global se maneja con Zustand. No se usa Context API "
                "para estado que cambia frecuentemente."
            ),
            "category": "decision",
            "tags": ["frontend", "state", "zustand"],
        },
        {
            "content": (
                "Convención: los hooks personalizados se nombran con prefijo use y viven en src/hooks/. "
                "Deben devolver objetos, no arrays, para facilitar el destructuring."
            ),
            "category": "architecture",
            "tags": ["frontend", "hooks", "convention"],
        },
    ],
}


# Consultas de seguimiento y los hechos que deberían recuperarse.
# `query` es la pregunta del usuario; `search_query` son las palabras clave que
# se le pasan a FTS5. Se mantienen simples (1-2 términos) porque FTS5 une los
# términos con AND implícito.
TASKS: list[dict] = [
    {
        "scenario": "api-auth",
        "query": "cómo implementamos el login",
        "search_query": "JWT autenticación",
        "expected_facts": ["RS256", "/api/v1/auth", "refresh token"],
    },
    {
        "scenario": "api-auth",
        "query": "tenemos un bug con tokens UTF-8",
        "search_query": "UTF middleware",
        "expected_facts": ["UTF-8", "normalizando el header"],
    },
    {
        "scenario": "db-migration",
        "query": "cómo crear una migración",
        "search_query": "Alembic",
        "expected_facts": ["Alembic", "alembic revision --autogenerate"],
    },
    {
        "scenario": "db-migration",
        "query": "qué base de datos usamos",
        "search_query": "PostgreSQL",
        "expected_facts": ["PostgreSQL 16", "SQLAlchemy 2.0"],
    },
    {
        "scenario": "deploy-pipeline",
        "query": "cómo desplegamos a producción",
        "search_query": "GitHub Actions",
        "expected_facts": ["GitHub Actions", "rama main"],
    },
    {
        "scenario": "deploy-pipeline",
        "query": "dónde van los secrets",
        "search_query": "secrets",
        "expected_facts": ["secrets de Fly.io"],
    },
    {
        "scenario": "frontend-style",
        "query": "qué librería usamos para estilos",
        "search_query": "Tailwind",
        "expected_facts": ["Tailwind CSS", "shadcn/ui"],
    },
    {
        "scenario": "frontend-style",
        "query": "cómo manejamos el estado global",
        "search_query": "Zustand",
        "expected_facts": ["Zustand"],
    },
]


# Consultas aisladas para medir retrieval puro.
RETRIEVAL_QUERIES: list[dict] = [
    {"query": "autenticación JWT", "scenario": "api-auth", "expected_facts": ["RS256", "JWT"]},
    {"query": "middleware auth", "scenario": "api-auth", "expected_facts": ["UTF-8", "middleware"]},
    {"query": "base datos PostgreSQL", "scenario": "db-migration", "expected_facts": ["PostgreSQL", "SQLAlchemy"]},
    {"query": "migraciones Alembic", "scenario": "db-migration", "expected_facts": ["Alembic"]},
    {"query": "despliegue Fly", "scenario": "deploy-pipeline", "expected_facts": ["Fly.io"]},
    {"query": "Docker multi stage", "scenario": "deploy-pipeline", "expected_facts": ["Docker"]},
    {"query": "Tailwind CSS", "scenario": "frontend-style", "expected_facts": ["Tailwind"]},
    {"query": "Zustand estado global", "scenario": "frontend-style", "expected_facts": ["Zustand"]},
]


def build_scenarios() -> list[ProjectScenario]:
    """Construye escenarios completos a partir de PROJECT_CONTEXTS y TASKS."""
    scenarios = []
    for task in TASKS:
        scenario_name = task["scenario"]
        memories = [
            {"project": scenario_name, **m} for m in PROJECT_CONTEXTS[scenario_name]
        ]
        scenarios.append(
            ProjectScenario(
                name=task["query"],
                project=scenario_name,
                memories=memories,
                query=sanitize_fts_query(task.get("search_query", task["query"])),
                expected_facts=task["expected_facts"],
            )
        )
    return scenarios


def sanitize_fts_query(query: str) -> str:
    """Limpia una consulta para que sea segura para FTS5.

    FTS5 interpreta ciertos caracteres (., -, ", etc.) como operadores. Esta
    función conserva solo palabras alfanuméricas y las une con espacios.
    """
    import re

    tokens = re.findall(r"[a-zA-Z0-9\u00C0-\u024F\u1E00-\u1EFF]+", query)
    return " ".join(tokens)


def populate_db(memory_mcp, scenario: ProjectScenario) -> dict[int, dict]:
    """Puebla la base de datos con los recuerdos del escenario.

    Devuelve un diccionario {id: memory} para poder referenciar resultados esperados.
    """
    created = {}
    for mem in scenario.memories:
        result = memory_mcp.add_memory(
            content=mem["content"],
            category=mem.get("category"),
            project=mem.get("project", scenario.project),
            tags=mem.get("tags"),
        )
        created[result["id"]] = mem
    return created


def prompt_without_memory(scenario: ProjectScenario) -> str:
    """Simula el prompt que un usuario tendría que escribir si no hubiera memoria."""
    context = "\n\n".join(m["content"] for m in scenario.memories)
    return f"Contexto del proyecto:\n\n{context}\n\nTarea: {scenario.query}"


def prompt_with_memory(query: str, retrieved: list[dict]) -> str:
    """Simula el prompt con la memoria recuperada inyectada."""
    if not retrieved:
        return f"Tarea: {query}"
    context = "\n\n".join(r["content"] for r in retrieved)
    return f"Contexto recordado:\n\n{context}\n\nTarea: {query}"
