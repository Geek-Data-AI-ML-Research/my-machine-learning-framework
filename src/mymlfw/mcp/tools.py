"""Thin MCP tool handlers — call saas services only (no driver / tenant IO)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from mymlfw.mcp.auth import (
    McpAuthContext,
    aresolve_auth_context,
    auth_error_payload,
    idempotency_key_from,
    require_scopes,
)
from mymlfw.saas.idempotency import IdempotencyConflict, IdempotencyStore, run_idempotent
from mymlfw.saas.missions import MissionNotFoundError, MissionService, StaleLeaseError
from mymlfw.saas.pats import PatStore
from mymlfw.saas.schemas import MissionOutcome

T = TypeVar("T")

_MCP_IDEMPOTENCY: IdempotencyStore | None = None

# Suggested fixes for common CloudProviderError codes.
_CLOUD_FIXES: dict[str, str] = {
    "feature_disabled": "PATCH /v1/orgs/current/feature-flags with cloud_runners=true",
    "not_connected": "Call connect_cloud_provider first",
    "quote_required": "Call quote_cloud_launch and pass cost_estimate_micros_hr",
    "quote_mismatch": "Re-quote; pass the exact cost_estimate_micros_hr",
    "cloud_budget_exceeded": "Raise max_cloud_micros_day entitlement",
    "invalid_api_key": "Pass a non-empty RunPod api_key",
    "invalid_role_arn": "Pass arn:aws:iam::… role_arn",
}


def _err(code: str, message: str, *, suggested_fix: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error_code": code, "message": message}
    if suggested_fix:
        body["suggested_fix"] = suggested_fix
    return body


def _cloud_err(code: str, message: str) -> dict[str, Any]:
    return _err(code, message, suggested_fix=_CLOUD_FIXES.get(code))


def _idempotency_store() -> IdempotencyStore:
    global _MCP_IDEMPOTENCY
    if _MCP_IDEMPOTENCY is None:
        _MCP_IDEMPOTENCY = IdempotencyStore()
    return _MCP_IDEMPOTENCY


def _require_idempotency(
    headers: dict[str, str] | None,
    explicit: str | None,
) -> str | dict[str, Any]:
    key = idempotency_key_from(headers, explicit)
    if not key:
        return _err(
            "idempotency_key_required",
            "Mutating MCP tools require idempotency_key (or Idempotency-Key header)",
            suggested_fix="Pass a unique UUID per logical operation",
        )
    return key


def _require_project(auth: McpAuthContext, project_id: str) -> str:
    """PAT may be workspace-wide or pinned to one project."""
    pinned = auth.principal.project_id
    if pinned and pinned != project_id:
        raise PermissionError("pat_project_mismatch")
    return auth.principal.workspace_id


async def _auth(
    *,
    pats: PatStore,
    headers: dict[str, str] | None,
    pat: str | None,
    scopes: tuple[str, ...],
) -> McpAuthContext | dict[str, Any]:
    try:
        auth = await aresolve_auth_context(
            headers=headers, explicit_token=pat, store=pats
        )
        require_scopes(auth, *scopes)
        return auth
    except PermissionError as exc:
        payload = auth_error_payload(exc)
        return payload or _err("permission_denied", str(exc))


async def tool_list_projects(
    *,
    missions: MissionService,
    pats: PatStore,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
) -> dict[str, Any]:
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
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
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    try:
        workspace_id = _require_project(auth, project_id)
    except PermissionError as exc:
        return auth_error_payload(exc) or _err("permission_denied", str(exc))
    _ = detail_level  # reserved for denser boards; service returns summary today
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
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    key = _require_idempotency(headers, idempotency_key)
    if isinstance(key, dict):
        return key
    try:
        workspace_id = _require_project(auth, project_id)
    except PermissionError as exc:
        return auth_error_payload(exc) or _err("permission_denied", str(exc))
    try:
        brief = await missions.get_next_mission(
            workspace_id=workspace_id,
            project_id=project_id,
            lease_owner=auth.lease_owner,
            idempotency_key=key,
            detail_level=detail_level,
        )
    except IdempotencyConflict:
        return _err(
            "idempotency_in_progress",
            "Idempotency-Key still in progress",
            suggested_fix="Retry the same Idempotency-Key after a short delay",
        )
    if brief is None:
        return {"mission": None, "message": "No queued missions available"}
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
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    key = _require_idempotency(headers, idempotency_key)
    if isinstance(key, dict):
        return key
    try:
        workspace_id = _require_project(auth, project_id)
    except PermissionError as exc:
        return auth_error_payload(exc) or _err("permission_denied", str(exc))
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
            idempotency_key=key,
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
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    key = _require_idempotency(headers, idempotency_key)
    if isinstance(key, dict):
        return key
    try:
        workspace_id = _require_project(auth, project_id)
    except PermissionError as exc:
        return auth_error_payload(exc) or _err("permission_denied", str(exc))
    try:
        result = await missions.report_mission_progress(
            workspace_id=workspace_id,
            project_id=project_id,
            mission_id=mission_id,
            lease_fencing_token=lease_fencing_token,
            note=note,
            percent=percent,
            idempotency_key=key,
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
    query: str = "",
) -> dict[str, Any]:
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    try:
        workspace_id = _require_project(auth, project_id)
    except PermissionError as exc:
        return auth_error_payload(exc) or _err("permission_denied", str(exc))
    result = await missions.query_project_brain(
        workspace_id=workspace_id,
        project_id=project_id,
        scope=scope,
        max_tokens=max_tokens,
        detail_level=detail_level,
        query=query,
    )
    return result.model_dump(mode="json")


async def tool_advise_project(
    *,
    project_id: str,
    pats: PatStore,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    task: str = "next experiment",
    max_missions: int = 3,
) -> dict[str, Any]:
    """Structured advise with citation_firewall (never returns unverified ULIDs)."""
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    try:
        workspace_id = _require_project(auth, project_id)
    except PermissionError as exc:
        return auth_error_payload(exc) or _err("permission_denied", str(exc))
    from mymlfw.saas.advise import advise_project
    from mymlfw.saas.brain_store import BRAIN_STORE

    try:
        result = advise_project(
            BRAIN_STORE,
            workspace_id=workspace_id,
            project_id=project_id,
            task=task,
            max_missions=max_missions,
        )
    except ValueError as exc:
        return _err("project_not_found", str(exc))
    return result.model_dump(mode="json")


async def tool_report_mcp_gap(
    *,
    title: str,
    needed_capability: str,
    pats: PatStore,
    mongo_client: Any | None = None,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    idempotency_key: str | None = None,
    context: str = "",
    workaround: str = "",
    severity: str = "annoying",
    project_id: str | None = None,
    suggested_tool_name: str = "",
    suggested_args_schema: str = "",
) -> dict[str, Any]:
    """Persist a missing-MCP-capability report for humans to triage in Studio."""
    key = _require_idempotency(headers, idempotency_key)
    if isinstance(key, dict):
        return key
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    if project_id:
        try:
            _require_project(auth, project_id)
        except PermissionError as exc:
            return auth_error_payload(exc) or _err("permission_denied", str(exc))

    from mymlfw.saas.mcp_gaps import list_gap_reports, report_gap
    from mymlfw.saas.schemas import McpGapReportCreate, McpGapSeverity

    try:
        sev = McpGapSeverity(severity)
    except ValueError:
        sev = McpGapSeverity.annoying

    body = McpGapReportCreate(
        title=title,
        needed_capability=needed_capability,
        context=context,
        workaround=workaround,
        severity=sev,
        project_id=project_id,
        suggested_tool_name=suggested_tool_name,
        suggested_args_schema=suggested_args_schema,
    )

    async def _write() -> dict[str, Any]:
        report = await report_gap(
            workspace_id=auth.principal.workspace_id,
            body=body,
            mongo_client=mongo_client,
        )
        return report.model_dump(mode="json")

    try:
        result, _replayed = await run_idempotent(
            _idempotency_store(),
            scope=f"mcp_gap:{auth.principal.workspace_id}",
            key=key,
            fn=_write,
        )
        return result
    except IdempotencyConflict:
        return _err(
            "idempotency_conflict",
            "idempotency_key already used for a different result",
            suggested_fix="Pass a fresh UUID for this gap report",
        )


async def tool_list_mcp_gaps(
    *,
    pats: PatStore,
    mongo_client: Any | None = None,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    if project_id:
        try:
            _require_project(auth, project_id)
        except PermissionError as exc:
            return auth_error_payload(exc) or _err("permission_denied", str(exc))
    from mymlfw.saas.mcp_gaps import list_gap_reports

    gaps = await list_gap_reports(
        workspace_id=auth.principal.workspace_id,
        project_id=project_id,
        limit=limit,
        mongo_client=mongo_client,
    )
    return {"gaps": [g.model_dump(mode="json") for g in gaps]}


async def tool_list_roadmap(
    *,
    project_id: str,
    pats: PatStore,
    mongo_client: Any | None = None,
    brain: Any | None = None,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
) -> dict[str, Any]:
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    try:
        workspace_id = _require_project(auth, project_id)
    except PermissionError as exc:
        return auth_error_payload(exc) or _err("permission_denied", str(exc))
    from mymlfw.saas.roadmap import list_strategies

    try:
        items = await list_strategies(
            workspace_id=workspace_id,
            project_id=project_id,
            mongo_client=mongo_client,
            brain=brain,
        )
    except KeyError:
        return _err(
            "project_not_found",
            "Project not found for this PAT workspace",
            suggested_fix="Call list_projects and pick a valid project_id",
        )
    return {"strategies": [s.model_dump(mode="json") for s in items]}


async def tool_add_roadmap_strategy(
    *,
    project_id: str,
    title: str,
    plan: str,
    pats: PatStore,
    mongo_client: Any | None = None,
    brain: Any | None = None,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    idempotency_key: str | None = None,
    priority: int = 100,
    status: str = "planned",
) -> dict[str, Any]:
    """Add one roadmap strategy (plan-first row on Studio Roadmap tab)."""
    key = _require_idempotency(headers, idempotency_key)
    if isinstance(key, dict):
        return key
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    try:
        workspace_id = _require_project(auth, project_id)
    except PermissionError as exc:
        return auth_error_payload(exc) or _err("permission_denied", str(exc))

    from mymlfw.saas.roadmap import add_strategy
    from mymlfw.saas.schemas import RoadmapStrategyCreate, RoadmapStrategyStatus

    try:
        st = RoadmapStrategyStatus(status)
    except ValueError:
        st = RoadmapStrategyStatus.planned
    body = RoadmapStrategyCreate(
        title=title, plan=plan, priority=int(priority), status=st
    )

    async def _write() -> dict[str, Any]:
        try:
            row = await add_strategy(
                workspace_id=workspace_id,
                project_id=project_id,
                body=body,
                mongo_client=mongo_client,
                brain=brain,
            )
        except KeyError:
            return _err(
                "project_not_found",
                "Project not found for this PAT workspace",
                suggested_fix="Call list_projects and pick a valid project_id",
            )
        return row.model_dump(mode="json")

    try:
        result, _replayed = await run_idempotent(
            _idempotency_store(),
            scope=f"add_roadmap:{workspace_id}:{project_id}",
            key=key,
            fn=_write,
        )
        return result
    except IdempotencyConflict:
        return _err(
            "idempotency_conflict",
            "idempotency_key already used for a different result",
            suggested_fix="Pass a fresh UUID for this strategy",
        )


async def tool_update_roadmap_strategy(
    *,
    project_id: str,
    strategy_id: str,
    pats: PatStore,
    mongo_client: Any | None = None,
    brain: Any | None = None,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    idempotency_key: str | None = None,
    title: str | None = None,
    plan: str | None = None,
    status: str | None = None,
    result: str | None = None,
    result_metric: float | None = None,
    priority: int | None = None,
) -> dict[str, Any]:
    """Patch a roadmap strategy (status / result / plan)."""
    key = _require_idempotency(headers, idempotency_key)
    if isinstance(key, dict):
        return key
    auth = await _auth(pats=pats, headers=headers, pat=pat, scopes=("mcp:worker",))
    if isinstance(auth, dict):
        return auth
    try:
        workspace_id = _require_project(auth, project_id)
    except PermissionError as exc:
        return auth_error_payload(exc) or _err("permission_denied", str(exc))

    from mymlfw.saas.roadmap import update_strategy
    from mymlfw.saas.schemas import RoadmapStrategyStatus, RoadmapStrategyUpdate

    st = None
    if status is not None:
        try:
            st = RoadmapStrategyStatus(status)
        except ValueError:
            return _err(
                "invalid_status",
                "status must be planned|in_progress|executed|cancelled",
            )
    body = RoadmapStrategyUpdate(
        title=title,
        plan=plan,
        status=st,
        result=result,
        result_metric=result_metric,
        priority=priority,
    )

    async def _write() -> dict[str, Any]:
        try:
            row = await update_strategy(
                workspace_id=workspace_id,
                project_id=project_id,
                strategy_id=strategy_id,
                body=body,
                mongo_client=mongo_client,
                brain=brain,
            )
        except KeyError as exc:
            code = str(exc) if str(exc) else "not_found"
            return _err(code, str(exc) or "roadmap strategy not found")
        return row.model_dump(mode="json")

    try:
        result_body, _replayed = await run_idempotent(
            _idempotency_store(),
            scope=f"update_roadmap:{workspace_id}:{project_id}:{strategy_id}",
            key=key,
            fn=_write,
        )
        return result_body
    except IdempotencyConflict:
        return _err(
            "idempotency_conflict",
            "idempotency_key already used for a different result",
            suggested_fix="Pass a fresh UUID for this update",
        )


def resource_org_runners(
    *,
    org_id: str,
    cloud_service: Any | None = None,
    cloud_runners_enabled: bool = False,
) -> dict[str, Any]:
    """Read-only runners listing — never includes provider secrets."""
    from mymlfw.saas.schemas import CloudRunnersResource

    runners: list[Any] = []
    if cloud_service is not None and cloud_runners_enabled:
        runners = list(cloud_service.list_runners())
    payload = CloudRunnersResource(
        org_id=org_id,
        runners=runners,
        cloud_runners_enabled=cloud_runners_enabled,
    )
    return payload.model_dump(mode="json")


def _cloud_svc(
    auth: McpAuthContext, cloud_store: Any
) -> tuple[Any, bool]:
    from mymlfw.saas.providers.mcp_facade import cloud_service_for_org

    return cloud_service_for_org(
        auth.principal.workspace_id, cloud_store=cloud_store
    )


async def _with_cloud_mutator(
    *,
    pats: PatStore,
    cloud_store: Any,
    headers: dict[str, str] | None,
    pat: str | None,
    idempotency_key: str | None,
    scope: str,
    fn: Callable[[Any], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    auth = await _auth(
        pats=pats,
        headers=headers,
        pat=pat,
        scopes=("mcp:cloud", "mcp:worker"),
    )
    if isinstance(auth, dict):
        return auth
    key = _require_idempotency(headers, idempotency_key)
    if isinstance(key, dict):
        return key
    svc, enabled = _cloud_svc(auth, cloud_store)
    if not enabled:
        return _cloud_err(
            "feature_disabled",
            "Enable org feature_flags.cloud_runners to use cloud providers",
        )

    async def _run() -> dict[str, Any]:
        return await fn(svc)

    try:
        result, _replayed = await run_idempotent(
            _idempotency_store(),
            scope=f"{scope}:{auth.principal.workspace_id}",
            key=key,
            fn=_run,
        )
        return result
    except IdempotencyConflict:
        return _err(
            "idempotency_in_progress",
            "Idempotency-Key still in progress",
            suggested_fix="Retry the same Idempotency-Key after a short delay",
        )


async def tool_list_org_runners(
    *,
    pats: PatStore,
    cloud_store: Any,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
) -> dict[str, Any]:
    """Read-only org runners payload (no secrets). Flag from org policy only."""
    from mymlfw.saas.providers.service import CloudProviderError
    from mymlfw.saas.schemas import CloudRunnersResource

    auth = await _auth(
        pats=pats,
        headers=headers,
        pat=pat,
        scopes=("mcp:cloud", "mcp:worker"),
    )
    if isinstance(auth, dict):
        return auth
    svc, enabled = _cloud_svc(auth, cloud_store)
    if not enabled:
        return CloudRunnersResource(
            org_id=auth.principal.workspace_id,
            runners=[],
            cloud_runners_enabled=False,
        ).model_dump(mode="json")
    try:
        runners = svc.list_runners()
    except CloudProviderError as exc:
        return _cloud_err(exc.code, exc.message)
    return CloudRunnersResource(
        org_id=auth.principal.workspace_id,
        runners=runners,
        cloud_runners_enabled=True,
    ).model_dump(mode="json")


async def tool_list_cloud_accounts(
    *,
    pats: PatStore,
    cloud_store: Any,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
) -> dict[str, Any]:
    from mymlfw.saas.providers.service import CloudProviderError

    auth = await _auth(
        pats=pats,
        headers=headers,
        pat=pat,
        scopes=("mcp:cloud", "mcp:worker"),
    )
    if isinstance(auth, dict):
        return auth
    svc, enabled = _cloud_svc(auth, cloud_store)
    if not enabled:
        return _cloud_err(
            "feature_disabled",
            "Enable org feature_flags.cloud_runners to list cloud accounts",
        )
    try:
        accounts = svc.list_accounts()
        return {"accounts": [a.model_dump(mode="json") for a in accounts]}
    except CloudProviderError as exc:
        return _cloud_err(exc.code, exc.message)


async def tool_connect_cloud_provider(
    *,
    provider: str,
    pats: PatStore,
    cloud_store: Any,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    api_key: str | None = None,
    role_arn: str | None = None,
    region: str = "us-east-1",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Seal RunPod API key or AWS role ARN; never echoes secrets."""
    from mymlfw.saas.providers.service import CloudProviderError

    async def _connect(svc: Any) -> dict[str, Any]:
        if provider == "runpod":
            if not api_key:
                return _cloud_err("invalid_api_key", "api_key required for runpod")
            return svc.connect_runpod(api_key=api_key).model_dump(mode="json")
        if provider == "aws":
            if not role_arn:
                return _cloud_err("invalid_role_arn", "role_arn required for aws")
            return svc.connect_aws(role_arn=role_arn, region=region).model_dump(
                mode="json"
            )
        return _err(
            "invalid_provider",
            "provider must be runpod|aws",
            suggested_fix="Pass provider=runpod or provider=aws",
        )

    try:
        return await _with_cloud_mutator(
            pats=pats,
            cloud_store=cloud_store,
            headers=headers,
            pat=pat,
            idempotency_key=idempotency_key,
            scope="mcp:cloud_connect",
            fn=_connect,
        )
    except CloudProviderError as exc:
        return _cloud_err(exc.code, exc.message)


async def tool_disconnect_cloud_provider(
    *,
    provider: str,
    pats: PatStore,
    cloud_store: Any,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    from mymlfw.saas.providers.service import CloudProviderError

    async def _disconnect(svc: Any) -> dict[str, Any]:
        return svc.disconnect(provider).model_dump(mode="json")  # type: ignore[arg-type]

    try:
        return await _with_cloud_mutator(
            pats=pats,
            cloud_store=cloud_store,
            headers=headers,
            pat=pat,
            idempotency_key=idempotency_key,
            scope=f"mcp:cloud_disconnect:{provider}",
            fn=_disconnect,
        )
    except CloudProviderError as exc:
        return _cloud_err(exc.code, exc.message)


async def tool_list_cloud_gpus(
    *,
    provider: str,
    pats: PatStore,
    cloud_store: Any,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
) -> dict[str, Any]:
    from mymlfw.saas.providers.service import CloudProviderError

    auth = await _auth(
        pats=pats,
        headers=headers,
        pat=pat,
        scopes=("mcp:cloud", "mcp:worker"),
    )
    if isinstance(auth, dict):
        return auth
    svc, enabled = _cloud_svc(auth, cloud_store)
    if not enabled:
        return _cloud_err("feature_disabled", "cloud_runners feature flag is off")
    try:
        offers = svc.list_gpus(provider)  # type: ignore[arg-type]
        return {"gpus": [o.model_dump(mode="json") for o in offers]}
    except CloudProviderError as exc:
        return _cloud_err(exc.code, exc.message)


async def tool_quote_cloud_launch(
    *,
    provider: str,
    gpu_type: str,
    pats: PatStore,
    cloud_store: Any,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
) -> dict[str, Any]:
    from mymlfw.saas.providers.service import CloudProviderError

    auth = await _auth(
        pats=pats,
        headers=headers,
        pat=pat,
        scopes=("mcp:cloud", "mcp:worker"),
    )
    if isinstance(auth, dict):
        return auth
    svc, enabled = _cloud_svc(auth, cloud_store)
    if not enabled:
        return _cloud_err("feature_disabled", "cloud_runners feature flag is off")
    try:
        return svc.quote_launch(
            provider=provider,  # type: ignore[arg-type]
            gpu_type=gpu_type,
        ).model_dump(mode="json")
    except CloudProviderError as exc:
        return _cloud_err(exc.code, exc.message)


async def tool_launch_cloud_runner(
    *,
    provider: str,
    gpu_type: str,
    cost_estimate_micros_hr: int,
    pats: PatStore,
    cloud_store: Any,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    spot: bool = True,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    from mymlfw.saas.providers.service import CloudProviderError

    async def _launch(svc: Any) -> dict[str, Any]:
        return svc.launch(
            provider=provider,  # type: ignore[arg-type]
            gpu_type=gpu_type,
            quote_accepted_micros_hr=cost_estimate_micros_hr,
            spot=spot,
        ).model_dump(mode="json")

    try:
        return await _with_cloud_mutator(
            pats=pats,
            cloud_store=cloud_store,
            headers=headers,
            pat=pat,
            idempotency_key=idempotency_key,
            scope="mcp:cloud_launch",
            fn=_launch,
        )
    except CloudProviderError as exc:
        return _cloud_err(exc.code, exc.message)


async def tool_stop_cloud_runner(
    *,
    runner_id: str,
    pats: PatStore,
    cloud_store: Any,
    headers: dict[str, str] | None = None,
    pat: str | None = None,
    terminate: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    from mymlfw.saas.providers.service import CloudProviderError

    async def _stop(svc: Any) -> dict[str, Any]:
        if terminate:
            return svc.terminate(runner_id).model_dump(mode="json")
        return svc.stop(runner_id).model_dump(mode="json")

    try:
        return await _with_cloud_mutator(
            pats=pats,
            cloud_store=cloud_store,
            headers=headers,
            pat=pat,
            idempotency_key=idempotency_key,
            scope=f"mcp:cloud_stop:{runner_id}",
            fn=_stop,
        )
    except CloudProviderError as exc:
        return _cloud_err(exc.code, exc.message)
