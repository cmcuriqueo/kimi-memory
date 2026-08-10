"""Benchmark de relevancia de búsqueda (retrieval)."""

from __future__ import annotations

import pytest

from .scenarios import PROJECT_CONTEXTS, RETRIEVAL_QUERIES, populate_db, sanitize_fts_query


def _fact_hits(memory: dict, expected_facts: list[str]) -> int:
    """Cuenta cuántos hechos esperados aparecen en el contenido de un recuerdo."""
    content = memory.get("content", "").lower()
    return sum(1 for fact in expected_facts if fact.lower() in content)


def _rank_of_first_relevant(results: list[dict], expected_facts: list[str]) -> int | None:
    """Devuelve la posición (1-based) del primer resultado relevante, o None."""
    for idx, mem in enumerate(results, start=1):
        if _fact_hits(mem, expected_facts) > 0:
            return idx
    return None


@pytest.mark.parametrize("item", RETRIEVAL_QUERIES, ids=lambda x: x["query"])
def test_retrieval_relevance(benchmark_db, benchmark_reporter, item):
    """Mide precision@k y recall@k para consultas típicas."""
    memory_mcp = benchmark_db
    scenario_name = item["scenario"]
    query = item["query"]
    expected_facts = item["expected_facts"]

    # Poblar DB con el contexto del escenario.
    from .scenarios import ProjectScenario

    scenario = ProjectScenario(
        name=query,
        project=scenario_name,
        memories=[{"project": scenario_name, **m} for m in PROJECT_CONTEXTS[scenario_name]],
        query=query,
    )
    populate_db(memory_mcp, scenario)

    results = memory_mcp.search_memories(sanitize_fts_query(query), limit=5)

    relevant_at_k = [
        1 if _fact_hits(r, expected_facts) > 0 else 0 for r in results
    ]

    def _precision_at_k(k: int) -> float:
        if k == 0 or not results:
            return 0.0
        top = relevant_at_k[:k]
        return sum(top) / k

    def _recall_at_k(k: int) -> float:
        # Asumimos que hay al menos un recuerdo relevante por escenario.
        total_relevant_in_pool = min(1, len([m for m in scenario.memories if _fact_hits(m, expected_facts) > 0]))
        if total_relevant_in_pool == 0:
            return 0.0
        return sum(relevant_at_k[:k]) / total_relevant_in_pool

    precision_3 = _precision_at_k(3)
    recall_5 = _recall_at_k(5)
    rank = _rank_of_first_relevant(results, expected_facts)
    rr = 1.0 / rank if rank else 0.0

    benchmark_reporter.record(
        test=f"retrieval/{query}",
        precision_at_3=precision_3,
        recall_at_5=recall_5,
        mrr=rr,
    )

    # Thresholds suaves: la búsqueda debe ser razonablemente útil.
    assert precision_3 >= 0.3, f"precision@3 muy baja para '{query}': {precision_3}"
    assert recall_5 >= 0.5, f"recall@5 muy bajo para '{query}': {recall_5}"


def test_retrieval_mean_reciprocal_rank(benchmark_db):
    """Mide el MRR promedio sobre todas las consultas de retrieval."""
    memory_mcp = benchmark_db
    rr_values = []

    for item in RETRIEVAL_QUERIES:
        from .scenarios import ProjectScenario

        scenario = ProjectScenario(
            name=item["query"],
            project=item["scenario"],
            memories=[{"project": item["scenario"], **m} for m in PROJECT_CONTEXTS[item["scenario"]]],
            query=item["query"],
        )
        populate_db(memory_mcp, scenario)
        results = memory_mcp.search_memories(sanitize_fts_query(item["query"]), limit=5)
        rank = _rank_of_first_relevant(results, item["expected_facts"])
        rr_values.append(1.0 / rank if rank else 0.0)

    mrr = sum(rr_values) / len(rr_values) if rr_values else 0.0
    assert mrr >= 0.5, f"MRR global muy bajo: {mrr}"
