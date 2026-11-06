"""Contrastive episode cards — primary memory on mission/lever close."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mymlfw.saas.ids import new_episode_card_id


def build_episode_card(
    *,
    project_id: str,
    workspace_id: str,
    outcome: str,
    notes: str = "",
    fold_scores: list[float] | None = None,
    variable: str | None = None,
    epoch_id: str | None = None,
    mission_title: str | None = None,
) -> dict[str, Any]:
    """Dense semantic summary for embed + hard metadata (no raw log dump)."""
    scores = list(fold_scores or [])
    mean = sum(scores) / len(scores) if scores else None
    snr = 1.0
    if scores and len(scores) > 1:
        mu = mean or 0.0
        var = sum((s - mu) ** 2 for s in scores) / len(scores)
        snr = 1.5 if var < 0.0004 else 0.8
    summary = (
        f"Mission={mission_title or 'unknown'}; outcome={outcome}; "
        f"variable={variable or 'n/a'}; "
        f"fold_mean={mean if mean is not None else 'n/a'}; "
        f"notes={notes[:280]}"
    )
    now = datetime.now(UTC)
    card_id = new_episode_card_id()
    return {
        "_id": card_id,
        "id": card_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "semantic_summary": summary,
        "epoch_id": epoch_id,
        "family": variable,
        "verdict": outcome,
        "snr_weight": snr,
        "utility_weight": 1.0,
        "times_retrieved": 0,
        "times_cited": 0,
        "falsified_on_cv": outcome in {"failed", "kill"},
        "attributed_cv_gains": 0.0,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
