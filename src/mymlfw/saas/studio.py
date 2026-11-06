"""Studio home + plan HTTP helpers (goals / levers / progress / missions).

Routes call these with either ``CampaignBrainStore`` (no Mongo) or Mongo via
``project_data`` — no invented product fields.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from mymlfw.saas.ids import (
    new_dead_end_id,
    new_experiment_id,
    new_goal_id,
    new_progress_id,
    new_project_id,
    new_roadmap_strategy_id,
    new_source_id,
)
from mymlfw.saas.lever_verifier import verify_lever_mutation
from mymlfw.saas.schemas import (
    DeadEndCreate,
    DeadEndResponse,
    DeadEndStatus,
    ExperimentCreate,
    ExperimentResponse,
    ExperimentStatus,
    GoalDirection,
    GoalKind,
    GoalStatus,
    LeverCloseRequest,
    MissionListItem,
    MissionStatus,
    ProgressNoteCreate,
    ProgressNoteResponse,
    ProjectArchiveResponse,
    ProjectCreate,
    ProjectGoalCreate,
    ProjectGoalResponse,
    ProjectGoalUpdate,
    ProjectInviteCreate,
    ProjectKind,
    ProjectMemberResponse,
    ProjectSourceCreate,
    ProjectSourceResponse,
    ProjectSourceUpdate,
    ProjectSummary,
    RoadmapStrategyCreate,
    RoadmapStrategyResponse,
    RoadmapStrategyStatus,
    RoadmapStrategyUpdate,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return (slug or "project")[:48]


def goal_from_doc(doc: dict[str, Any]) -> ProjectGoalResponse:
    return ProjectGoalResponse(
        id=doc.get("id") or doc["_id"],
        project_id=doc["project_id"],
        title=doc["title"],
        kind=GoalKind(doc.get("kind") or GoalKind.notebook_score.value),
        metric_key=doc.get("metric_key") or "cv_mean",
        threshold=float(doc["threshold"]),
        direction=GoalDirection(doc.get("direction") or GoalDirection.maximize.value),
        constraints=list(doc.get("constraints") or []),
        status=GoalStatus(doc.get("status") or GoalStatus.active.value),
        priority=int(doc.get("priority") or 100),
        notes=str(doc.get("notes") or ""),
        best_value=doc.get("best_value"),
    )


def experiment_from_doc(doc: dict[str, Any]) -> ExperimentResponse:
    return ExperimentResponse(
        id=doc["_id"],
        project_id=doc["project_id"],
        goal_id=doc["goal_id"],
        parent_experiment_id=doc.get("parent_experiment_id"),
        epoch_id=doc.get("epoch_id"),
        variable=doc["variable"],
        band_low=float(doc["band_low"]),
        band_high=float(doc["band_high"]),
        fold_scores=list(doc.get("fold_scores") or []),
        cv_mean=doc.get("cv_mean"),
        cv_std=doc.get("cv_std"),
        cv_delta=doc.get("cv_delta"),
        verdict=doc.get("verdict"),
        status=ExperimentStatus(doc.get("status") or ExperimentStatus.open.value),
        teacher_oof_ids=list(doc.get("teacher_oof_ids") or []),
        strategy=doc.get("strategy"),
        parent_oof_ids=list(doc.get("parent_oof_ids") or []),
        ensemble_weights=list(doc.get("ensemble_weights") or []),
    )


def dead_end_from_doc(doc: dict[str, Any]) -> DeadEndResponse:
    return DeadEndResponse(
        id=doc["_id"],
        project_id=doc["project_id"],
        variable=doc["variable"],
        lesson=doc["lesson"],
        epoch_id=doc.get("epoch_id"),
        status=DeadEndStatus(doc.get("status") or DeadEndStatus.active_block.value),
        times_retrieved=int(doc.get("times_retrieved") or 0),
        times_cited=int(doc.get("times_cited") or 0),
        utility_weight=float(doc.get("utility_weight") or 1.0),
        snr_weight=float(doc.get("snr_weight") or 1.0),
    )


def progress_from_doc(doc: dict[str, Any]) -> ProgressNoteResponse:
    return ProgressNoteResponse(
        id=doc["_id"],
        project_id=doc["project_id"],
        note=doc["note"],
        created_at=doc["created_at"],
    )


def source_from_doc(doc: dict[str, Any]) -> ProjectSourceResponse:
    return ProjectSourceResponse(
        id=doc.get("id") or doc["_id"],
        project_id=doc["project_id"],
        title=str(doc.get("title") or ""),
        url=str(doc.get("url") or ""),
        description=str(doc.get("description") or ""),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


def build_source_doc(
    *,
    workspace_id: str,
    project_id: str,
    body: ProjectSourceCreate,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = now or _utcnow()
    source_id = new_source_id()
    return {
        "_id": source_id,
        "id": source_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "title": body.title.strip(),
        "url": body.url.strip(),
        "description": (body.description or "").strip(),
        "created_at": ts,
        "updated_at": ts,
        "deleted_at": None,
    }


def apply_source_update(doc: dict[str, Any], body: ProjectSourceUpdate) -> None:
    if body.title is not None:
        doc["title"] = body.title.strip()
    if body.url is not None:
        doc["url"] = body.url.strip()
    if body.description is not None:
        doc["description"] = body.description.strip()
    doc["updated_at"] = _utcnow()


def roadmap_strategy_from_doc(doc: dict[str, Any]) -> RoadmapStrategyResponse:
    raw = str(doc.get("status") or RoadmapStrategyStatus.planned.value)
    try:
        status = RoadmapStrategyStatus(raw)
    except ValueError:
        status = RoadmapStrategyStatus.planned
    return RoadmapStrategyResponse(
        id=doc.get("id") or doc["_id"],
        project_id=doc["project_id"],
        title=str(doc.get("title") or ""),
        plan=str(doc.get("plan") or ""),
        status=status,
        result=str(doc.get("result") or ""),
        result_metric=doc.get("result_metric"),
        priority=int(doc.get("priority") or 100),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
        executed_at=doc.get("executed_at"),
    )


def build_roadmap_strategy_doc(
    *,
    workspace_id: str,
    project_id: str,
    body: RoadmapStrategyCreate,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = now or _utcnow()
    strategy_id = new_roadmap_strategy_id()
    status = body.status or RoadmapStrategyStatus.planned
    return {
        "_id": strategy_id,
        "id": strategy_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "title": body.title.strip(),
        "plan": body.plan.strip(),
        "status": status.value,
        "result": "",
        "result_metric": None,
        "priority": int(body.priority),
        "created_at": ts,
        "updated_at": ts,
        "executed_at": ts if status == RoadmapStrategyStatus.executed else None,
        "deleted_at": None,
    }


def apply_roadmap_strategy_update(
    doc: dict[str, Any], body: RoadmapStrategyUpdate
) -> None:
    now = _utcnow()
    if body.title is not None:
        doc["title"] = body.title.strip()
    if body.plan is not None:
        doc["plan"] = body.plan.strip()
    if body.priority is not None:
        doc["priority"] = int(body.priority)
    if body.result is not None:
        doc["result"] = body.result.strip()
    if body.result_metric is not None:
        doc["result_metric"] = body.result_metric
    if body.status is not None:
        prev = str(doc.get("status") or "")
        doc["status"] = body.status.value
        if (
            body.status == RoadmapStrategyStatus.executed
            and prev != RoadmapStrategyStatus.executed.value
        ):
            doc["executed_at"] = now
        if body.status != RoadmapStrategyStatus.executed:
            # Keep executed_at history unless cancelled/reset to planned without result.
            if body.status in {
                RoadmapStrategyStatus.planned,
                RoadmapStrategyStatus.cancelled,
            } and not doc.get("result"):
                doc["executed_at"] = None
    doc["updated_at"] = now


def mission_from_doc(doc: dict[str, Any]) -> MissionListItem:
    raw = str(doc.get("status") or "queued")
    try:
        status = MissionStatus(raw)
    except ValueError:
        status = MissionStatus.queued
    return MissionListItem(
        id=doc["_id"],
        project_id=doc["project_id"],
        title=str(doc.get("title") or "mission"),
        status=status,
        mission_type=str(doc.get("mission_type") or "custom"),
        goal_id=doc.get("goal_id"),
    )


def build_goal_doc(
    *,
    workspace_id: str,
    project_id: str,
    body: ProjectGoalCreate,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = now or _utcnow()
    goal_id = new_goal_id()
    return {
        "_id": goal_id,
        "id": goal_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "title": body.title,
        "kind": body.kind.value,
        "metric_key": body.metric_key,
        "threshold": body.threshold,
        "direction": body.direction.value,
        "constraints": list(body.constraints),
        "status": GoalStatus.active.value,
        "priority": body.priority,
        "notes": body.notes,
        "best_value": None,
        "created_at": ts,
        "updated_at": ts,
        "deleted_at": None,
    }


def build_project_bundle(
    *,
    workspace_id: str,
    body: ProjectCreate,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return project doc + goal docs for wizard create."""
    if body.kind == ProjectKind.kaggle and not (body.kaggle_competition or "").strip():
        raise ValueError("kaggle_competition_required")
    project_id = new_project_id()
    now = _utcnow()
    project = {
        "_id": project_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "slug": _slugify(body.name),
        "name": body.name,
        "kind": body.kind.value,
        "is_demo": False,
        "epoch_id": "epoch_0",
        "folds_sha256": secrets.token_hex(32),
        "adv_auc": None,
        "n_folds": 5,
        "folds_artifact_key": f"projects/{project_id}/folds.parquet",
        "public_share_slug": None,
        "kaggle_competition": (body.kaggle_competition or "").strip() or None,
        "git_remote": (body.git_remote or "").strip() or None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    goals = [
        build_goal_doc(workspace_id=workspace_id, project_id=project_id, body=g, now=now)
        for g in body.goals
    ]
    return project, goals


def build_experiment_doc(
    *,
    workspace_id: str,
    project_id: str,
    body: ExperimentCreate,
    epoch_id: str | None = None,
) -> dict[str, Any]:
    gate = verify_lever_mutation(variable=body.variable)
    if not gate.allowed:
        raise ValueError(f"lever_rejected:{gate.reason}")
    now = _utcnow()
    exp_id = new_experiment_id()
    return {
        "_id": exp_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "goal_id": body.goal_id,
        "parent_experiment_id": body.parent_experiment_id,
        "epoch_id": body.epoch_id or epoch_id or "epoch_0",
        "variable": body.variable,
        "band_low": body.band_low,
        "band_high": body.band_high,
        "fold_scores": list(body.fold_scores),
        "cv_mean": None,
        "cv_std": None,
        "cv_delta": None,
        "verdict": None,
        "status": ExperimentStatus.open.value,
        "teacher_oof_ids": list(body.teacher_oof_ids),
        "strategy": body.strategy,
        "parent_oof_ids": list(body.parent_oof_ids),
        "ensemble_weights": list(body.ensemble_weights),
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }


def apply_goal_update(doc: dict[str, Any], body: ProjectGoalUpdate) -> dict[str, Any]:
    data = body.model_dump(exclude_none=True)
    for key, value in data.items():
        if hasattr(value, "value"):
            doc[key] = value.value
        else:
            doc[key] = value
    doc["updated_at"] = _utcnow()
    return doc


def apply_lever_close(doc: dict[str, Any], body: LeverCloseRequest) -> dict[str, Any]:
    if doc.get("status") != ExperimentStatus.open.value:
        raise ValueError("lever_not_open")
    now = _utcnow()
    scores = list(body.fold_scores)
    doc["status"] = ExperimentStatus.closed.value
    doc["verdict"] = body.verdict or doc.get("verdict")
    if scores:
        doc["fold_scores"] = scores
        doc["cv_mean"] = sum(scores) / len(scores)
    if body.notes:
        doc["completion_notes"] = body.notes
    doc["updated_at"] = now
    return doc


def build_dead_end_doc(
    *,
    workspace_id: str,
    project_id: str,
    body: DeadEndCreate,
    epoch_id: str | None = None,
) -> dict[str, Any]:
    now = _utcnow()
    ded_id = new_dead_end_id()
    return {
        "_id": ded_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "variable": body.variable,
        "lesson": body.lesson,
        "epoch_id": body.epoch_id or epoch_id or "epoch_0",
        "status": body.status.value,
        "times_retrieved": 0,
        "times_cited": 0,
        "utility_weight": 1.0,
        "snr_weight": 1.0,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }


def build_progress_doc(
    *,
    workspace_id: str,
    project_id: str,
    body: ProgressNoteCreate,
) -> dict[str, Any]:
    now = _utcnow()
    return {
        "_id": new_progress_id(),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "note": body.note,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }


def build_invite_doc(
    *,
    workspace_id: str,
    project_id: str,
    body: ProjectInviteCreate,
    user_id: str | None = None,
) -> dict[str, Any]:
    now = _utcnow()
    return {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "email": body.email,
        "role": body.role,
        "user_id": user_id,
        "status": "active" if user_id else "invited",
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }


def member_from_doc(doc: dict[str, Any]) -> ProjectMemberResponse:
    return ProjectMemberResponse(
        project_id=doc["project_id"],
        email=doc["email"],
        role=doc["role"],  # type: ignore[arg-type]
        user_id=doc.get("user_id"),
        status=doc.get("status") or "invited",  # type: ignore[arg-type]
    )


def lock_expires(hours: int = 24) -> datetime:
    return _utcnow() + timedelta(hours=hours)


# --- In-memory CampaignBrainStore operations ---------------------------------


def memory_create_project(store: Any, *, org_id: str, body: ProjectCreate) -> ProjectSummary:
    from mymlfw.saas.brain_store import CampaignBrainStore

    assert isinstance(store, CampaignBrainStore)
    project, goals = build_project_bundle(workspace_id=org_id, body=body)
    project_id = project["_id"]
    store.projects[project_id] = project
    store.by_org.setdefault(org_id, []).append(project_id)
    store.goals[project_id] = goals
    store.experiments.setdefault(project_id, [])
    store.missions.setdefault(project_id, [])
    store.dead_ends.setdefault(project_id, [])
    store.progress.setdefault(project_id, [])
    store.members.setdefault(project_id, [])
    return store._summary(project)


def memory_archive_project(
    store: Any, *, org_id: str, project_id: str
) -> ProjectArchiveResponse:
    proj = store.get_project(org_id, project_id)
    if proj is None:
        raise KeyError("project_not_found")
    now = _utcnow()
    proj["deleted_at"] = now
    proj["updated_at"] = now
    return ProjectArchiveResponse(id=project_id, deleted_at=now)


def memory_invite(
    store: Any,
    *,
    org_id: str,
    project_id: str,
    body: ProjectInviteCreate,
    user_id: str | None = None,
) -> ProjectMemberResponse:
    if store.get_project(org_id, project_id) is None:
        raise KeyError("project_not_found")
    doc = build_invite_doc(
        workspace_id=org_id,
        project_id=project_id,
        body=body,
        user_id=user_id,
    )
    store.members.setdefault(project_id, []).append(doc)
    return member_from_doc(doc)
