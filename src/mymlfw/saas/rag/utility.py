"""Bandit utility updates for cited dead ends / episode memory."""

from __future__ import annotations

from typing import Any, Iterable


def bump_times_cited(docs: Iterable[dict[str, Any]], cited_ids: list[str]) -> list[str]:
    """Advise-path: increment ``times_cited`` only (no utility multiply)."""
    want = set(cited_ids)
    touched: list[str] = []
    for doc in docs:
        doc_id = str(doc.get("_id") or doc.get("id") or "")
        if doc_id not in want:
            continue
        doc["times_cited"] = int(doc.get("times_cited") or 0) + 1
        touched.append(doc_id)
    return touched


def update_cited_memory_utility(
    docs: Iterable[dict[str, Any]],
    *,
    cited_ids: list[str],
    outcome: str,
) -> list[str]:
    """Mutate docs in place. Promote → ×1.15 (dead ends ×1.10); kill → ×0.80 + falsified.

    Returns ids that were updated.
    """
    want = set(cited_ids)
    touched: list[str] = []
    promote = outcome in {"succeeded", "success", "promote"}
    kill = outcome in {"failed", "kill", "abandoned"}
    for doc in docs:
        doc_id = str(doc.get("_id") or doc.get("id") or "")
        if doc_id not in want:
            continue
        w = float(doc.get("utility_weight") or 1.0)
        if promote:
            if doc_id.startswith("ded_"):
                w *= 1.10
            else:
                w *= 1.15
            doc["times_cited"] = int(doc.get("times_cited") or 0) + 1
        elif kill:
            w *= 0.80
            doc["falsified_on_cv"] = True
            doc["times_cited"] = int(doc.get("times_cited") or 0) + 1
        doc["utility_weight"] = max(0.05, min(8.0, w))
        touched.append(doc_id)
    return touched
