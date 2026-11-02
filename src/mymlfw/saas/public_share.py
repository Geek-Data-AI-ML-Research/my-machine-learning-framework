"""Redacted ``public_snapshots`` for PLG share — never a live doc dump."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from mymlfw.saas.schemas import DashboardResponse


def make_share_slug(project_slug: str, entropy: str) -> str:
    """``{slug}-{entropy}`` high-entropy public path segment."""
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in project_slug.lower())
    return f"{safe}-{entropy}"


# Allowlist of goal fields safe to show publicly (no internal notes / constraints).
_GOAL_ALLOW = ("title", "kind", "metric_key", "threshold", "direction", "status")


def build_redacted_snapshot(
    *,
    project: Mapping[str, Any],
    dashboard: DashboardResponse,
    goals: Sequence[Mapping[str, Any]],
    dead_ends: Sequence[Mapping[str, Any]],
    include_goals: bool = True,
    include_lever_stats: bool = True,
    include_dead_end_lessons: bool = False,
) -> dict[str, Any]:
    """Build a redacted allowlist payload for ``public_snapshots``.

    Explicitly omits workspace/project ids, notes, teacher_oof_ids, and any
    live Mongo document dump.
    """
    out: dict[str, Any] = {
        "name": project.get("name"),
        "kind": project.get("kind"),
        "progress_pct": dashboard.header.progress_pct,
        "adv_auc_label": dashboard.header.adv_auc_label,
        # Never expose raw folds_sha256 or internal ids on public pages.
    }
    if include_goals:
        out["goals"] = [
            {k: g.get(k) for k in _GOAL_ALLOW if k in g} for g in goals
        ]
        out["goals_panel"] = dashboard.goals.model_dump()
    if include_lever_stats:
        levers = dashboard.levers.model_dump()
        # Drop sparkline timestamps / raw fold lists from public view.
        levers.pop("sparkline", None)
        levers["fold_badges"] = [
            {"display": b.get("display"), "label": b.get("label")}
            for b in levers.get("fold_badges") or []
        ]
        out["levers"] = levers
    if include_dead_end_lessons:
        out["dead_ends"] = [
            {"variable": d.get("variable"), "lesson": d.get("lesson")}
            for d in dead_ends
        ]
    else:
        out["dead_ends_count"] = dashboard.dead_ends.count
    return out
