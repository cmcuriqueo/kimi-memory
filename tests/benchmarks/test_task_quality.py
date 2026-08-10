"""Benchmark de calidad de respuesta basado en cobertura de hechos."""

from __future__ import annotations

import pytest

from .scenarios import build_scenarios, populate_db


def _fact_coverage(retrieved: list[dict], expected_facts: list[str]) -> float:
    """Devuelve el porcentaje de hechos esperados presentes en la memoria recuperada."""
    if not expected_facts:
        return 1.0
    combined = " ".join(r.get("content", "").lower() for r in retrieved)
    hits = sum(1 for fact in expected_facts if fact.lower() in combined)
    return hits / len(expected_facts)


@pytest.mark.parametrize("scenario", build_scenarios(), ids=lambda s: s.name)
def test_task_fact_coverage(benchmark_db, benchmark_reporter, scenario):
    """Mide si la memoria recuperada contiene los hechos necesarios para responder."""
    memory_mcp = benchmark_db
    populate_db(memory_mcp, scenario)

    search_results = memory_mcp.search_memories(scenario.query, project=scenario.project, limit=3)
    retrieved = memory_mcp.get_memories([r["id"] for r in search_results]) if search_results else []

    coverage = _fact_coverage(retrieved, scenario.expected_facts or [])

    benchmark_reporter.record(
        test=f"task_quality/{scenario.name}",
        fact_coverage=coverage * 100,
    )

    assert coverage >= 0.6, (
        f"Cobertura de hechos muy baja para '{scenario.name}': {coverage:.0%}"
    )


def test_average_fact_coverage(benchmark_db, benchmark_reporter):
    """Mide la cobertura promedio de hechos sobre todos los escenarios."""
    memory_mcp = benchmark_db
    coverages = []

    for scenario in build_scenarios():
        populate_db(memory_mcp, scenario)
        search_results = memory_mcp.search_memories(scenario.query, project=scenario.project, limit=3)
        retrieved = memory_mcp.get_memories([r["id"] for r in search_results]) if search_results else []
        coverage = _fact_coverage(retrieved, scenario.expected_facts or [])
        coverages.append(coverage)

    avg_coverage = sum(coverages) / len(coverages) if coverages else 0.0
    benchmark_reporter.record(
        test="task_quality/average",
        fact_coverage=avg_coverage * 100,
    )

    assert avg_coverage >= 0.7, f"Cobertura promedio de hechos muy baja: {avg_coverage:.0%}"
