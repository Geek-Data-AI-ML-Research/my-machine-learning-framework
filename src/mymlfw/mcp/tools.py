"""Thin MCP tool handlers — call saas services only (no driver / tenant IO)."""

from __future__ import annotations

from typing import Any

from mymlfw.mcp.auth import McpAuthContext, resolve_auth_context
from mymlfw.saas.idempotency import IdempotencyConflict
from mymlfw.saas.missions import MissionNotFoundError, MissionService, StaleLeaseError
from mymlfw.saas.pats import PatStore
from mymlfw.saas.schemas import MissionOutcome


def _err(code: str, message: str, *, suggested_fix: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error_code": code, "message": message}
    if suggested_fix:
        body["suggested_fix"] = suggested_fix
    return body


def _require_project(
    auth: McpAuthContext, project_id: str
) -> str:
    """PAT may be workspace-wide or pinned to one project."""
    pinned = auth.principal.project_id
    if pinned and pinned != project_id:
        raise PermissionError("pat_project_mismatch")
    return auth.principal.workspace_id


async def tool_list_projects(
    *,
    missions: MissionService,
    pats: PatStore,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
) -> dict[str, Any]:
    auth = resolve_auth_context(headers=headers, explicit_token=pat, store=pats)
    listing = await missions.list_projects(auth.principal.workspace_id)
    return listing.model_dump(mode="json")


async def tool_get_project_dashboard(
    *,
    project_id: str,
    missions: MissionService,
    pats: PatStore,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    detail_level: str = "summary",
) -> dict[str, Any]:
    _ = detail_level
    auth = resolve_auth_context(headers=headers, explicit_token=pat, store=pats)
    workspace_id = _require_project(auth, project_id)
    dash = await missions.get_project_dashboard(workspace_id, project_id)
    if dash is None:
        return _err(
            "project_not_found",
            "Project not found for this PAT workspace",
            suggested_fix="Call list_projects and pick a valid project_id",
        )
    return dash.model_dump(mode="json")


async def tool_get_next_mission(
    *,
    project_id: str,
    missions: MissionService,
    pats: PatStore,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    idempotency_key: str | None = None,
    detail_level: str = "summary",
) -> dict[str, Any]:
    auth = resolve_auth_context(headers=headers, explicit_token=pat, store=pats)
    workspace_id = _require_project(auth, project_id)
    try:
        brief = await missions.get_next_mission(
            workspace_id=workspace_id,
            project_id=project_id,
            lease_owner=auth.lease_owner,
            idempotency_key=idempotency_key,
            detail_level=detail_level,
        )
    except IdempotencyConflict:
        return _err(
            "idempotency_in_progress",
            "Idempotency-Key still in progress",
            suggested_fix="Retry the same Idempotency-Key after a short delay",
        )
    if brief is None:
        return {
            "mission": None,
            "message": "No queued missions available",
        }
    return {"mission": brief.model_dump(mode="json")}


async def tool_complete_mission(
    *,
    project_id: str,
    mission_id: str,
    lease_fencing_token: int,
    outcome: str,
    missions: MissionService,
    pats: PatStore,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    fold_scores: list[float] | None = None,
    notes: str = "",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    auth = resolve_auth_context(headers=headers, explicit_token=pat, store=pats)
    workspace_id = _require_project(auth, project_id)
    try:
        parsed = MissionOutcome(outcome)
    except ValueError:
        return _err(
            "invalid_outcome",
            "outcome must be succeeded|failed|abandoned",
            suggested_fix="Pass outcome=succeeded or outcome=failed",
        )
    try:
        result = await missions.complete_mission(
            workspace_id=workspace_id,
            project_id=project_id,
            mission_id=mission_id,
            lease_fencing_token=lease_fencing_token,
            outcome=parsed,
            fold_scores=fold_scores,
            notes=notes,
            idempotency_key=idempotency_key,
        )
    except StaleLeaseError as exc:
        return _err(
            "stale_lease",
            str(exc) or "Lease fencing token is stale",
            suggested_fix="Re-claim with get_next_mission; do not retry the old token",
        )
    except MissionNotFoundError as exc:
        return _err("mission_not_found", str(exc), suggested_fix="Check mission_id")
    except IdempotencyConflict:
        return _err(
            "idempotency_in_progress",
            "Idempotency-Key still in progress",
            suggested_fix="Retry the same Idempotency-Key after a short delay",
        )
    return result.model_dump(mode="json")


async def tool_report_mission_progress(
    *,
    project_id: str,
    mission_id: str,
    lease_fencing_token: int,
    missions: MissionService,
    pats: PatStore,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    note: str = "",
    percent: float | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    auth = resolve_auth_context(headers=headers, explicit_token=pat, store=pats)
    workspace_id = _require_project(auth, project_id)
    try:
        result = await missions.report_mission_progress(
            workspace_id=workspace_id,
            project_id=project_id,
            mission_id=mission_id,
            lease_fencing_token=lease_fencing_token,
            note=note,
            percent=percent,
            idempotency_key=idempotency_key,
        )
    except StaleLeaseError as exc:
        return _err(
            "stale_lease",
            str(exc) or "Lease fencing token is stale",
            suggested_fix="Re-claim with get_next_mission; do not retry the old token",
        )
    except MissionNotFoundError as exc:
        return _err("mission_not_found", str(exc), suggested_fix="Check mission_id")
    except IdempotencyConflict:
        return _err(
            "idempotency_in_progress",
            "Idempotency-Key still in progress",
            suggested_fix="Retry the same Idempotency-Key after a short delay",
        )
    return result.model_dump(mode="json")


async def tool_query_project_brain(
    *,
    project_id: str,
    missions: MissionService,
    pats: PatStore,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    scope: str = "all",
    max_tokens: int = 512,
    detail_level: str = "summary",
) -> dict[str, Any]:
    auth = resolve_auth_context(headers=headers, explicit_token=pat, store=pats)
    workspace_id = _require_project(auth, project_id)
    result = await missions.query_project_brain(
        workspace_id=workspace_id,
        project_id=project_id,
        scope=scope,
        max_tokens=max_tokens,
        detail_level=detail_level,
    )
    return result.model_dump(mode="json")


async def tool_optimize_ensemble(
    *,
    project_id: str,
    oof_ids: list[str],
    pats: PatStore,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    mode: str = "auto",
    missions: MissionService | None = None,
) -> dict[str, Any]:
    """Thin MCP wrapper: plan nested-CV blend for ready OOF artifact ids."""
    _ = missions
    auth = resolve_auth_context(headers=headers, explicit_token=pat, store=pats)
    _require_project(auth, project_id)
    from mymlfw.saas.ensemble import plan_ensemble

    return plan_ensemble(list(oof_ids), mode=mode)  # type: ignore[arg-type]


async def tool_promote_blend_to_experiment(
    *,
    project_id: str,
    parent_oof_ids: list[str],
    weights: list[float],
    pats: PatStore,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    mode: str = "linear",
    goal_id: str | None = None,
    parent_experiment_ids: list[str] | None = None,
    missions: MissionService | None = None,
) -> dict[str, Any]:
    """Thin MCP wrapper: stub promote with ensemble_blend lineage parents."""
    _ = missions
    auth = resolve_auth_context(headers=headers, explicit_token=pat, store=pats)
    _require_project(auth, project_id)
    from mymlfw.saas.ensemble import EnsembleError, promote_blend_to_experiment

    try:
        return promote_blend_to_experiment(
            parent_oof_ids=parent_oof_ids,
            weights=weights,
            mode=mode,  # type: ignore[arg-type]
            project_id=project_id,
            goal_id=goal_id,
            parent_experiment_ids=parent_experiment_ids,
        )
    except EnsembleError as exc:
        return _err(exc.code, exc.message, suggested_fix=exc.extra.get("suggested_fix"))
