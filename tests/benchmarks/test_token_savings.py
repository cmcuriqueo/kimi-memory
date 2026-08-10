"""Benchmark de ahorro de tokens con/sin memoria."""

from __future__ import annotations

import pytest

from .scenarios import (
    build_scenarios,
    populate_db,
    prompt_with_memory,
    prompt_without_memory,
    sanitize_fts_query,
)


# Tokens aproximados que cuesta la llamada de busqueda + recuperacion.
# Se usa como estimacion del overhead del sistema de memoria.
SEARCH_QUERY_OVERHEAD_TOKENS = 15
MEMORY_GET_OVERHEAD_TOKENS = 10


@pytest.mark.parametrize("scenario", build_scenarios(), ids=lambda s: s.name)
def test_token_savings(benchmark_db, tokenizer, benchmark_reporter, scenario):
    """Compara el costo en tokens de resolver una tarea con y sin memoria."""
    memory_mcp = benchmark_db
    populate_db(memory_mcp, scenario)

    # --- Sin memoria: el usuario repite todo el contexto ---
    prompt_no_mem = prompt_without_memory(scenario)
    tokens_no_mem = tokenizer(prompt_no_mem)

    # --- Con memoria: busqueda + recuperar top resultados ---
    search_results = memory_mcp.search_memories(scenario.query, project=scenario.project, limit=3)

    # Simulamos leer el detalle completo de los resultados (memory_get).
    retrieved = memory_mcp.get_memories([r["id"] for r in search_results]) if search_results else []

    prompt_mem = prompt_with_memory(scenario.query, retrieved)
    tokens_prompt_mem = tokenizer(prompt_mem)

    # Overhead del sistema de memoria.
    search_overhead = tokenizer(scenario.query) + SEARCH_QUERY_OVERHEAD_TOKENS
    get_overhead = tokenizer(
        " ".join(str(rid) for rid in [r["id"] for r in search_results])
    ) + MEMORY_GET_OVERHEAD_TOKENS
    total_overhead = search_overhead + get_overhead

    tokens_con_mem = tokens_prompt_mem + total_overhead

    savings = tokens_no_mem - tokens_con_mem
    savings_percent = (savings / tokens_no_mem * 100) if tokens_no_mem else 0.0
    overhead_percent = (total_overhead / tokens_no_mem * 100) if tokens_no_mem else 0.0

    benchmark_reporter.record(
        test=f"token_savings/{scenario.name}",
        tokens_without_memory=tokens_no_mem,
        tokens_with_memory=tokens_con_mem,
        token_savings_percent=savings_percent,
        search_overhead_percent=overhead_percent,
    )

    assert savings_percent >= 15.0, (
        f"No se ahorraron suficientes tokens en '{scenario.name}': {savings_percent:.1f}%"
    )


def test_no_harm_when_no_relevant_memory(benchmark_db, tokenizer, benchmark_reporter):
    """Cuando no hay memoria relevante, el overhead de buscar memoria debe ser bajo."""
    memory_mcp = benchmark_db

    # Guardamos memoria de un proyecto distinto.
    memory_mcp.add_memory(
        content="Este proyecto usa Ruby on Rails y Sidekiq.",
        category="architecture",
        project="otro-proyecto",
        tags=["ruby", "rails"],
    )

    user_query = (
        "Necesito configurar un cluster de Kubernetes en AWS con autoescalado "
        "y un ingress controller para exponer varios servicios de microservicios."
    )

    # Simulamos un prompt moderado con algo de contexto del proyecto actual.
    project_baseline = (
        "Estamos trabajando en una aplicacion de e-commerce con arquitectura de microservicios. "
        "Usamos AWS, Docker y CI/CD con GitHub Actions. El frontend esta en Next.js y el backend "
        "en Node.js. Tenemos varios repositorios separados para catalogo, pagos y envios."
    )
    prompt_baseline = f"Contexto del proyecto:\n\n{project_baseline}\n\nTarea: {user_query}"
    tokens_baseline = tokenizer(prompt_baseline)

    # Con memoria: hacemos una busqueda que no va a devolver nada relevante.
    search_results = memory_mcp.search_memories(sanitize_fts_query(user_query), limit=3)
    retrieved = memory_mcp.get_memories([r["id"] for r in search_results]) if search_results else []
    prompt_with = prompt_with_memory(user_query, retrieved)
    tokens_with = tokenizer(prompt_with)

    # El usuario escribiria el query de todas formas; el overhead real es la busqueda + recuperacion.
    search_overhead = SEARCH_QUERY_OVERHEAD_TOKENS
    get_overhead = MEMORY_GET_OVERHEAD_TOKENS if search_results else 0
    total_overhead = search_overhead + get_overhead
    overhead_percent = (total_overhead / tokens_baseline * 100) if tokens_baseline else 0.0
    extra_tokens = (tokens_with + total_overhead) - tokens_baseline

    benchmark_reporter.record(
        test="token_savings/no_relevant_memory",
        tokens_without_memory=tokens_baseline,
        tokens_with_memory=tokens_with + total_overhead,
        token_savings_percent=-overhead_percent,
        search_overhead_percent=overhead_percent,
    )

    assert overhead_percent < 20.0, (
        f"El overhead de busqueda sin memoria relevante es muy alto: {overhead_percent:.1f}%"
    )
    assert extra_tokens < 50, (
        f"Se gastaron demasiados tokens extra sin memoria relevante: {extra_tokens}"
    )
