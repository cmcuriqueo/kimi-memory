"""Reporter simple para acumular y mostrar métricas de benchmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BenchmarkReporter:
    """Acumula métricas numéricas e imprime un resumen al final."""

    metrics: list[dict[str, Any]] = field(default_factory=list)

    def record(self, **kwargs: Any) -> None:
        """Registra un diccionario de métricas."""
        self.metrics.append(kwargs)

    def _average(self, key: str) -> float | None:
        values = [m[key] for m in self.metrics if key in m and isinstance(m[key], (int, float))]
        if not values:
            return None
        return sum(values) / len(values)

    def print_summary(self) -> None:
        """Imprime una tabla Markdown con promedios clave."""
        if not self.metrics:
            print("\n[kimi-memory-benchmark] No se registraron métricas.")
            return

        print("\n## Resumen de benchmarks kimi-memory\n")
        print("| Métrica | Valor |")
        print("|---|---|")

        keys = [
            "token_savings_percent",
            "precision_at_3",
            "recall_at_5",
            "mrr",
            "fact_coverage",
            "search_overhead_percent",
        ]
        labels = {
            "token_savings_percent": "Ahorro de tokens (%)",
            "precision_at_3": "Precision@3",
            "recall_at_5": "Recall@5",
            "mrr": "MRR",
            "fact_coverage": "Cobertura de hechos (%)",
            "search_overhead_percent": "Overhead de búsqueda (%)",
        }

        for key in keys:
            avg = self._average(key)
            if avg is not None:
                print(f"| {labels.get(key, key)} | {avg:.2f} |")

        print(f"\nTotal de observaciones: {len(self.metrics)}")
