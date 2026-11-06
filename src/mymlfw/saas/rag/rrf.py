"""App-side reciprocal rank fusion (fallback when ``$rankFusion`` unavailable)."""

from __future__ import annotations

from typing import Any


def rrf_fuse(
    *ranked_lists: list[dict[str, Any]],
    id_key: str = "doc_id",
    k: int = 60,
) -> list[dict[str, Any]]:
    """Fuse ranked lists with score ``1/(k+rank)``; preserve first-seen metadata."""
    scores: dict[str, float] = {}
    meta: dict[str, dict[str, Any]] = {}
    for ranked in ranked_lists:
        for rank, row in enumerate(ranked, start=1):
            doc_id = str(row.get(id_key) or "")
            if not doc_id:
                continue
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            if doc_id not in meta:
                meta[doc_id] = dict(row)
    fused = []
    for doc_id, score in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])):
        item = dict(meta[doc_id])
        item["rrf_score"] = score
        fused.append(item)
    return fused
