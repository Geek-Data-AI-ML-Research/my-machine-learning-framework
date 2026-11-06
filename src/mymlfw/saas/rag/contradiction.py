"""Contradiction unlock — mark legacy dead ends ``needs_reverification``."""

from __future__ import annotations

from typing import Any


def mark_needs_reverification(
    dead_ends: list[dict[str, Any]],
    *,
    variable_family: str | None,
    new_epoch_id: str | None,
    context_shifted: bool = False,
) -> list[str]:
    """When epoch/context shifts, unlock matching dead ends and suggest fold0_smoke.

    Returns ids that were flipped to ``needs_reverification``.
    """
    family = (variable_family or "").split("=", 1)[0].strip()
    if not family and not context_shifted:
        return []
    touched: list[str] = []
    for ded in dead_ends:
        if ded.get("deleted_at"):
            continue
        var = str(ded.get("variable") or "")
        if family and not var.startswith(family):
            continue
        same_epoch = new_epoch_id and ded.get("epoch_id") == new_epoch_id
        if same_epoch and not context_shifted:
            continue
        if ded.get("status") == "needs_reverification":
            continue
        ded["status"] = "needs_reverification"
        ded["suggested_run_mode"] = "fold0_smoke"
        touched.append(str(ded.get("_id") or ded.get("id") or ""))
    return [t for t in touched if t]
