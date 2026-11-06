"""RRF × epoch decay × evidence SNR × utility bandit rescoring."""

from __future__ import annotations

from typing import Any


def epoch_weight(*, doc_epoch: str | None, current_epoch: str | None) -> float:
    if not current_epoch or not doc_epoch:
        return 1.0
    if doc_epoch == current_epoch:
        return 1.0
    # Simple Δepoch: treat non-matching as one step away (0.35^1).
    return 0.35


def evidence_weight(row: dict[str, Any]) -> float:
    snr = float(row.get("snr_weight") or 1.0)
    doc_type = str(row.get("doc_type") or "")
    if snr >= 1.4 or doc_type == "promoted":
        return 1.5
    if doc_type == "dead_end":
        return 1.2
    if doc_type in {"kaggle_intel", "note"}:
        return 0.8
    return 1.0


def final_score(
    row: dict[str, Any],
    *,
    current_epoch: str | None,
) -> float:
    rrf = float(row.get("rrf_score") or row.get("score") or 0.0)
    w_epoch = epoch_weight(
        doc_epoch=row.get("epoch_id"),
        current_epoch=current_epoch,
    )
    w_ev = evidence_weight(row)
    utility = float(row.get("utility_weight") or 1.0)
    return rrf * w_epoch * w_ev * utility


def rescore_hits(
    hits: list[dict[str, Any]],
    *,
    current_epoch: str | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in hits:
        item = dict(row)
        item["score"] = final_score(item, current_epoch=current_epoch)
        out.append(item)
    out.sort(key=lambda r: (-float(r.get("score") or 0.0), str(r.get("doc_id"))))
    return out
