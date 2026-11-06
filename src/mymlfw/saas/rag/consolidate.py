"""Sleep-cycle consolidate → pinned project axioms."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from mymlfw.saas.ids import new_axiom_id


def consolidate_project_brain(
    *,
    project_id: str,
    workspace_id: str,
    dead_ends: list[dict[str, Any]],
    episode_cards: list[dict[str, Any]],
    epoch_id: str | None = None,
    max_axioms: int = 5,
) -> list[dict[str, Any]]:
    """Derive short axioms from repeated dead-end families + high-SNR cards."""
    now = datetime.now(UTC)
    families = Counter(
        str(d.get("variable") or "").split("=", 1)[0]
        for d in dead_ends
        if d.get("variable") and not d.get("deleted_at")
    )
    axioms: list[dict[str, Any]] = []
    for family, count in families.most_common(max_axioms):
        if not family or count < 1:
            continue
        ax_id = new_axiom_id()
        lesson = next(
            (
                str(d.get("lesson") or "")
                for d in dead_ends
                if str(d.get("variable") or "").startswith(family)
            ),
            "",
        )
        statement = (
            f"Avoid repeating {family} without fold0_smoke "
            f"({count} dead end(s)). {lesson}".strip()
        )
        axioms.append(
            {
                "_id": ax_id,
                "id": ax_id,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "schema_version": 1,
                "statement": statement[:500],
                "evidence_count": count,
                "pinned": True,
                "epoch_id": epoch_id,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        )
    # High-SNR episode hint
    strong = [
        c
        for c in episode_cards
        if float(c.get("snr_weight") or 0) >= 1.4 and not c.get("falsified_on_cv")
    ]
    if strong and len(axioms) < max_axioms:
        ax_id = new_axiom_id()
        axioms.append(
            {
                "_id": ax_id,
                "id": ax_id,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "schema_version": 1,
                "statement": f"Prefer patterns from high-SNR episodes ({len(strong)} cards).",
                "evidence_count": len(strong),
                "pinned": True,
                "epoch_id": epoch_id,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        )
    return axioms
