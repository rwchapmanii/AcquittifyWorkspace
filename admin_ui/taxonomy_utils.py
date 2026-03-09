from __future__ import annotations

from typing import Any, Dict, Iterable, Set


def compute_coverage(code_set: Iterable[str], taxonomy_codes: Iterable[str], version: str | None, source: str) -> Dict[str, Any]:
    code_set_norm: Set[str] = {c for c in code_set if isinstance(c, str) and c.strip()}
    taxonomy_norm: Set[str] = {c for c in taxonomy_codes if isinstance(c, str) and c.strip()}
    covered = len(code_set_norm.intersection(taxonomy_norm))
    total_nodes = len(taxonomy_norm)
    ratio = covered / total_nodes if total_nodes else 0.0
    return {
        "version": version,
        "source": source,
        "total_nodes": total_nodes,
        "covered_nodes": covered,
        "coverage_ratio": ratio,
    }
