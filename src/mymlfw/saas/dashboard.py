"""Project dashboard aggregates: progress formula + slim $project before $facet."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from mymlfw.saas.fold_badges import adv_auc_label, fold_snr_badge
from mymlfw.saas.schemas import (
    DashboardDeadEndsPanel,
    DashboardGoalsPanel,
    DashboardHeader,
    DashboardLeversPanel,
    DashboardMissionsPanel,
    DashboardResponse,
    FoldSnrBadge,
    GoalStatus,
)

# Slim fields only — keep $facet under the 100MB covered-query budget.
EXPERIMENT_FACET_PROJECT: dict[str, int] = {
    "status": 1,
    "verdict": 1,
    "cv_mean": 1,
    "cv_std": 1,
    "cv_delta": 1,
    "variable": 1,
    "created_at": 1,
    "fold_scores": 1,
    "goal_id": 1,
    "parent_experiment_id": 1,
}


def progress_pct(
    *,
    goals_met_ratio: float,
    lever_close_rate: float,
    mission_success_rate: float,
) -> float:
    """Canonical Overview progress: ``0.5*G + 0.3*L + 0.2*M``."""
    return round(
        0.5 * goals_met_ratio + 0.3 * lever_close_rate + 0.2 * mission_success_rate,
        6,
    )


def _ratio(numer: int, denom: int) -> float:
    if denom <= 0:
        return 0.0
    return numer / denom


def experiments_facet_pipeline() -> list[dict[str, Any]]:
    """Pipeline stages after ScopedCollection prepends tenant ``$match``.

    Order is binding: ``$sort`` + slim ``$project`` **before** ``$facet``.
    """
    return [
        {"$sort": {"created_at": -1}},
        {"$project": dict(EXPERIMENT_FACET_PROJECT)},
        {
            "$facet": {
                "lever_stats": [
                    {
                        "$group": {
                            "_id": None,
                            "open": {
                                "$sum": {"$cond": [{"$eq": ["$status", "open"]}, 1, 0]}
                            },
                            "closed": {
                                "$sum": {
                                    "$cond": [{"$eq": ["$status", "closed"]}, 1, 0]
                                }
                            },
                            "kills": {
                                "$sum": {
                                    "$cond": [{"$eq": ["$verdict", "kill"]}, 1, 0]
                                }
                            },
                            "promotes": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$in": [
                                                "$verdict",
                                                [
                                                    "promote-candidate",
                                                    "confirmed-large-gap",
                                                ],
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    }
                ],
                "sparkline": [
                    {"$limit": 14},
                    {
                        "$project": {
                            "cv_mean": 1,
                            "cv_delta": 1,
                            "created_at": 1,
                            "variable": 1,
                        }
                    },
                ],
            }
        },
    ]


def compute_dashboard(
    *,
    project_id: str,
    goals: Sequence[Mapping[str, Any]],
    experiments: Sequence[Mapping[str, Any]],
    missions: Sequence[Mapping[str, Any]],
    dead_ends: Sequence[Mapping[str, Any]],
    folds_sha256: str | None = None,
    adv_auc: float | None = None,
) -> DashboardResponse:
    """Pure aggregate used by API, CLI, and in-memory Demo Campaign."""
    active = sum(1 for g in goals if g.get("status") == GoalStatus.active.value)
    met = sum(1 for g in goals if g.get("status") == GoalStatus.met.value)
    abandoned = sum(1 for g in goals if g.get("status") == GoalStatus.abandoned.value)
    goal_total = active + met + abandoned
    goals_met_ratio = _ratio(met, goal_total if goal_total else 0)

    open_n = sum(1 for e in experiments if e.get("status") == "open")
    closed_n = sum(1 for e in experiments if e.get("status") == "closed")
    kills = sum(1 for e in experiments if e.get("verdict") == "kill")
    promotes = sum(
        1
        for e in experiments
        if e.get("verdict") in ("promote-candidate", "confirmed-large-gap")
    )
    lever_close_rate = _ratio(closed_n, open_n + closed_n)

    queued = sum(1 for m in missions if m.get("status") == "queued")
    # ``leased`` is the B2 lease state; ``running`` kept for older seeds.
    running = sum(
        1 for m in missions if m.get("status") in ("running", "leased")
    )
    succeeded = sum(1 for m in missions if m.get("status") == "succeeded")
    failed = sum(
        1
        for m in missions
        if m.get("status") in ("failed", "abandoned_by_agent")
    )
    mission_success_rate = _ratio(succeeded, succeeded + failed)

    pct = progress_pct(
        goals_met_ratio=goals_met_ratio,
        lever_close_rate=lever_close_rate,
        mission_success_rate=mission_success_rate,
    )

    primary = next(
        (g for g in goals if g.get("status") == GoalStatus.active.value),
        goals[0] if goals else None,
    )
    primary_status = "OPEN"
    if primary is not None:
        st = primary.get("status")
        if st == GoalStatus.met.value:
            primary_status = "MET"
        elif st == GoalStatus.abandoned.value:
            primary_status = "MISSED"

    badges: list[FoldSnrBadge] = []
    for exp in experiments:
        scores = exp.get("fold_scores") or []
        if scores:
            badges.append(fold_snr_badge(scores))

    spark = [
        {
            "variable": e.get("variable"),
            "cv_mean": e.get("cv_mean"),
            "cv_delta": e.get("cv_delta"),
            "created_at": e.get("created_at"),
        }
        for e in list(experiments)[:14]
    ]

    return DashboardResponse(
        project_id=project_id,
        header=DashboardHeader(
            primary_goal_id=primary.get("_id") or primary.get("id") if primary else None,
            primary_goal_title=primary.get("title") if primary else None,
            primary_threshold=primary.get("threshold") if primary else None,
            primary_status=primary_status,
            progress_pct=pct,
            goals_met_ratio=goals_met_ratio,
            lever_close_rate=lever_close_rate,
            mission_success_rate=mission_success_rate,
            folds_sha256=folds_sha256,
            adv_auc=adv_auc,
            adv_auc_label=adv_auc_label(adv_auc),
        ),
        goals=DashboardGoalsPanel(
            active=active, met=met, abandoned=abandoned, count=goal_total
        ),
        levers=DashboardLeversPanel(
            open=open_n,
            closed=closed_n,
            kills=kills,
            promotes=promotes,
            fold_badges=badges[:8],
            sparkline=spark,
        ),
        missions=DashboardMissionsPanel(
            queued=queued,
            running=running,
            succeeded=succeeded,
            failed=failed,
        ),
        dead_ends=DashboardDeadEndsPanel(
            count=len(dead_ends),
            top_variables=[
                str(d.get("variable") or "?") for d in list(dead_ends)[:5]
            ],
        ),
    )
