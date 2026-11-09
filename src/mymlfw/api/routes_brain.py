"""Phase B brain routes: projects, dashboard, share, demo seed + studio CRUD."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from mymlfw.api.auth import AUTH_STORE
from mymlfw.api.deps import get_current_principal, require_owner
from mymlfw.api.public_route import public_route
from mymlfw.saas.brain_store import BRAIN_STORE
from mymlfw.saas.schemas import (
    AdviseRequest,
    AdviseResponse,
    DashboardResponse,
    DeadEndCreate,
    DeadEndListResponse,
    DeadEndResponse,
    ExperimentCreate,
    ExperimentResponse,
    LeverCloseRequest,
    LeverListResponse,
    MissionListResponse,
    PlaybookCatalogResponse,
    ProgressNoteCreate,
    ProgressNoteListResponse,
    ProgressNoteResponse,
    ProjectArchiveResponse,
    ProjectCreate,
    ProjectGitLinkRequest,
    ProjectGitResponse,
    ProjectGoalCreate,
    ProjectGoalListResponse,
    ProjectGoalResponse,
    ProjectGoalUpdate,
    ProjectInviteCreate,
    ProjectListResponse,
    ProjectMemberListResponse,
    ProjectMemberResponse,
    ProjectSourceCreate,
    ProjectSourceListResponse,
    ProjectSourceResponse,
    ProjectSourceUpdate,
    ProjectSummary,
    RoadmapStrategyCreate,
    RoadmapStrategyListResponse,
    RoadmapStrategyResponse,
    RoadmapStrategyUpdate,
    PublicSnapshotCreate,
    PublicSnapshotResponse,
    QueryProjectBrainRequest,
    QueryProjectBrainResponse,
    SettingsResponse,
)

router = APIRouter(tags=["brain"])


def _mongo(request: Request) -> Any | None:
    return getattr(request.app.state, "mongo_db", None)


def _org(principal: dict[str, Any]) -> Any:
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    return org


async def _lookup_invitee_user_id(request: Request, email: str) -> str | None:
    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import auth_data

        user = await auth_data.get_user_by_email(mongo, email)
        return None if user is None else str(user["_id"])
    return AUTH_STORE.by_email.get(email.lower())


@router.get("/v1/playbook/catalog", response_model=PlaybookCatalogResponse)
async def get_playbook_catalog(
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
    modality: str = "tabular",
    kind: str = "standalone",
) -> PlaybookCatalogResponse:
    """DS strategy ladder + paradigm shifts (shared with ``mymlfw playbook`` CLI)."""
    del principal  # auth gate only — catalog is org-agnostic
    from mymlfw.playbook import playbook_catalog

    try:
        payload = playbook_catalog(modality=modality, kind=kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlaybookCatalogResponse.model_validate(payload)


@router.get("/v1/settings", response_model=SettingsResponse)
async def settings(
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> SettingsResponse:
    """Settings read — entitlements/flags already on me/org (no Stripe)."""
    return SettingsResponse(
        user=principal["user"],
        org=principal.get("org"),
        persona=principal.get("persona"),
    )


@router.post("/v1/studio/ensure-demo", response_model=ProjectSummary)
async def ensure_demo(
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectSummary:
    """Deprecated: no invented demo campaign. Returns 404."""
    _ = request, principal
    raise HTTPException(status_code=404, detail="demo_campaign_removed")


@router.get("/v1/projects", response_model=ProjectListResponse)
async def list_projects(
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectListResponse:
    org = _org(principal)
    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        return ProjectListResponse(
            projects=await project_data.list_projects(mongo, org.id)
        )
    return ProjectListResponse(projects=BRAIN_STORE.list_projects(org.id))


@router.post("/v1/projects", response_model=ProjectSummary)
async def create_project(
    body: ProjectCreate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectSummary:
    """New project wizard create (gated by entitlements.max_private_projects)."""
    org = _org(principal)
    entitlements = org.entitlements
    max_projects = int(getattr(entitlements, "max_private_projects", 5) or 5)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            existing = await project_data.list_projects(mongo, org.id)
            if len(existing) >= max_projects:
                raise HTTPException(status_code=403, detail="max_private_projects")
            return await project_data.create_project(
                mongo, workspace_id=org.id, body=body
            )
        existing = BRAIN_STORE.list_projects(org.id)
        if len(existing) >= max_projects:
            raise HTTPException(status_code=403, detail="max_private_projects")
        return BRAIN_STORE.create_project(org.id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/v1/projects/{project_id}", response_model=ProjectSummary)
async def get_project(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectSummary:
    org = _org(principal)
    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        proj = await project_data.get_project(mongo, org.id, project_id)
        if proj is None:
            raise HTTPException(status_code=404, detail="project_not_found")
        return project_data.project_summary_from_doc(proj)
    proj = BRAIN_STORE.get_project(org.id, project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    return BRAIN_STORE._summary(proj)


@router.post(
    "/v1/projects/{project_id}/archive",
    response_model=ProjectArchiveResponse,
)
async def archive_project(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectArchiveResponse:
    org = _org(principal)
    require_owner(principal, action="archive project")
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.archive_project(
                mongo, workspace_id=org.id, project_id=project_id
            )
        return BRAIN_STORE.archive_project(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc


@router.post(
    "/v1/projects/{project_id}/invite",
    response_model=ProjectMemberResponse,
)
async def invite_project_member(
    project_id: str,
    body: ProjectInviteCreate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectMemberResponse:
    org = _org(principal)
    require_owner(principal, action="invite member")
    user_id = await _lookup_invitee_user_id(request, body.email)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.invite_member(
                mongo,
                workspace_id=org.id,
                project_id=project_id,
                body=body,
                user_id=user_id,
            )
        return BRAIN_STORE.invite_member(
            org.id, project_id, body, user_id=user_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc


@router.get(
    "/v1/projects/{project_id}/members",
    response_model=ProjectMemberListResponse,
)
async def list_project_members(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectMemberListResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            members = await project_data.list_members(mongo, org.id, project_id)
        else:
            members = BRAIN_STORE.list_members(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    return ProjectMemberListResponse(members=members)


@router.get(
    "/v1/projects/{project_id}/goals",
    response_model=ProjectGoalListResponse,
)
async def list_goals(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectGoalListResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            goals = await project_data.list_goals(mongo, org.id, project_id)
        else:
            if BRAIN_STORE.get_project(org.id, project_id) is None:
                raise KeyError("project_not_found")
            goals = BRAIN_STORE.list_goals(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    return ProjectGoalListResponse(goals=goals)


@router.post(
    "/v1/projects/{project_id}/goals",
    response_model=ProjectGoalResponse,
)
async def create_goal(
    project_id: str,
    body: ProjectGoalCreate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectGoalResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.add_goal(
                mongo, workspace_id=org.id, project_id=project_id, body=body
            )
        return BRAIN_STORE.add_goal(org.id, project_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/v1/projects/{project_id}/goals/{goal_id}",
    response_model=ProjectGoalResponse,
)
async def patch_goal(
    project_id: str,
    goal_id: str,
    body: ProjectGoalUpdate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectGoalResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.update_goal(
                mongo,
                workspace_id=org.id,
                project_id=project_id,
                goal_id=goal_id,
                body=body,
            )
        return BRAIN_STORE.update_goal(org.id, project_id, goal_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/v1/projects/{project_id}/progress",
    response_model=ProgressNoteListResponse,
)
async def list_progress(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProgressNoteListResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            notes = await project_data.list_progress(mongo, org.id, project_id)
        else:
            if BRAIN_STORE.get_project(org.id, project_id) is None:
                raise KeyError("project_not_found")
            notes = BRAIN_STORE.list_progress(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    return ProgressNoteListResponse(notes=notes)


@router.post(
    "/v1/projects/{project_id}/progress",
    response_model=ProgressNoteResponse,
)
async def add_progress(
    project_id: str,
    body: ProgressNoteCreate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProgressNoteResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.add_progress(
                mongo, workspace_id=org.id, project_id=project_id, body=body
            )
        return BRAIN_STORE.add_progress(org.id, project_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc


@router.get(
    "/v1/projects/{project_id}/dead-ends",
    response_model=DeadEndListResponse,
)
async def list_dead_ends(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> DeadEndListResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            items = await project_data.list_dead_ends(mongo, org.id, project_id)
        else:
            if BRAIN_STORE.get_project(org.id, project_id) is None:
                raise KeyError("project_not_found")
            items = BRAIN_STORE.list_dead_ends(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    return DeadEndListResponse(dead_ends=items)


@router.post(
    "/v1/projects/{project_id}/dead-ends",
    response_model=DeadEndResponse,
)
async def add_dead_end(
    project_id: str,
    body: DeadEndCreate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> DeadEndResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.add_dead_end(
                mongo, workspace_id=org.id, project_id=project_id, body=body
            )
        return BRAIN_STORE.add_dead_end(org.id, project_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc


@router.get(
    "/v1/projects/{project_id}/sources",
    response_model=ProjectSourceListResponse,
)
async def list_sources(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectSourceListResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            items = await project_data.list_sources(mongo, org.id, project_id)
        else:
            if BRAIN_STORE.get_project(org.id, project_id) is None:
                raise KeyError("project_not_found")
            items = BRAIN_STORE.list_sources(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    return ProjectSourceListResponse(sources=items)


@router.post(
    "/v1/projects/{project_id}/sources",
    response_model=ProjectSourceResponse,
)
async def create_source(
    project_id: str,
    body: ProjectSourceCreate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectSourceResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.add_source(
                mongo, workspace_id=org.id, project_id=project_id, body=body
            )
        return BRAIN_STORE.add_source(org.id, project_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc


@router.patch(
    "/v1/projects/{project_id}/sources/{source_id}",
    response_model=ProjectSourceResponse,
)
async def patch_source(
    project_id: str,
    source_id: str,
    body: ProjectSourceUpdate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectSourceResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.update_source(
                mongo,
                workspace_id=org.id,
                project_id=project_id,
                source_id=source_id,
                body=body,
            )
        return BRAIN_STORE.update_source(org.id, project_id, source_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/v1/projects/{project_id}/sources/{source_id}")
async def remove_source(
    project_id: str,
    source_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> dict[str, Any]:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            await project_data.delete_source(
                mongo,
                workspace_id=org.id,
                project_id=project_id,
                source_id=source_id,
            )
        else:
            BRAIN_STORE.delete_source(org.id, project_id, source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "source_id": source_id}


@router.get(
    "/v1/projects/{project_id}/roadmap",
    response_model=RoadmapStrategyListResponse,
)
async def list_roadmap(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> RoadmapStrategyListResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            items = await project_data.list_roadmap_strategies(
                mongo, org.id, project_id
            )
        else:
            if BRAIN_STORE.get_project(org.id, project_id) is None:
                raise KeyError("project_not_found")
            items = BRAIN_STORE.list_roadmap_strategies(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    return RoadmapStrategyListResponse(strategies=items)


@router.post(
    "/v1/projects/{project_id}/roadmap",
    response_model=RoadmapStrategyResponse,
)
async def create_roadmap_strategy(
    project_id: str,
    body: RoadmapStrategyCreate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> RoadmapStrategyResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.add_roadmap_strategy(
                mongo, workspace_id=org.id, project_id=project_id, body=body
            )
        return BRAIN_STORE.add_roadmap_strategy(org.id, project_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc


@router.patch(
    "/v1/projects/{project_id}/roadmap/{strategy_id}",
    response_model=RoadmapStrategyResponse,
)
async def patch_roadmap_strategy(
    project_id: str,
    strategy_id: str,
    body: RoadmapStrategyUpdate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> RoadmapStrategyResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.update_roadmap_strategy(
                mongo,
                workspace_id=org.id,
                project_id=project_id,
                strategy_id=strategy_id,
                body=body,
            )
        return BRAIN_STORE.update_roadmap_strategy(
            org.id, project_id, strategy_id, body
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/v1/projects/{project_id}/roadmap/{strategy_id}")
async def remove_roadmap_strategy(
    project_id: str,
    strategy_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> dict[str, Any]:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            await project_data.delete_roadmap_strategy(
                mongo,
                workspace_id=org.id,
                project_id=project_id,
                strategy_id=strategy_id,
            )
        else:
            BRAIN_STORE.delete_roadmap_strategy(org.id, project_id, strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "strategy_id": strategy_id}


@router.get(
    "/v1/projects/{project_id}/git",
    response_model=ProjectGitResponse,
)
async def get_project_git(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectGitResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.get_project_git(mongo, org.id, project_id)
        return BRAIN_STORE.get_project_git(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc


@router.put(
    "/v1/projects/{project_id}/git",
    response_model=ProjectGitResponse,
)
async def put_project_git(
    project_id: str,
    body: ProjectGitLinkRequest,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectGitResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.set_project_git(
                mongo,
                workspace_id=org.id,
                project_id=project_id,
                remote=body.remote,
                refresh=body.refresh,
            )
        return BRAIN_STORE.set_project_git(
            org.id, project_id, body.remote, refresh=body.refresh
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/v1/projects/{project_id}/git/refresh",
    response_model=ProjectGitResponse,
)
async def refresh_project_git(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectGitResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.refresh_project_git(
                mongo, workspace_id=org.id, project_id=project_id
            )
        return BRAIN_STORE.refresh_project_git(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/v1/projects/{project_id}/git",
    response_model=ProjectGitResponse,
)
async def delete_project_git(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectGitResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.clear_project_git(
                mongo, workspace_id=org.id, project_id=project_id
            )
        return BRAIN_STORE.clear_project_git(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc


@router.get(
    "/v1/projects/{project_id}/levers",
    response_model=LeverListResponse,
)
async def list_levers(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> LeverListResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            levers = await project_data.list_levers(mongo, org.id, project_id)
        else:
            if BRAIN_STORE.get_project(org.id, project_id) is None:
                raise KeyError("project_not_found")
            levers = BRAIN_STORE.list_levers(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    return LeverListResponse(levers=levers)


@router.post(
    "/v1/projects/{project_id}/levers",
    response_model=ExperimentResponse,
)
async def open_lever(
    project_id: str,
    body: ExperimentCreate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ExperimentResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.open_lever(
                mongo, workspace_id=org.id, project_id=project_id, body=body
            )
        return BRAIN_STORE.open_lever(org.id, project_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        if str(exc) == "one_open_lever":
            raise HTTPException(status_code=409, detail="one_open_lever") from exc
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/v1/projects/{project_id}/levers/{experiment_id}/close",
    response_model=ExperimentResponse,
)
async def close_lever(
    project_id: str,
    experiment_id: str,
    body: LeverCloseRequest,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ExperimentResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.close_lever(
                mongo,
                workspace_id=org.id,
                project_id=project_id,
                experiment_id=experiment_id,
                body=body,
            )
        return BRAIN_STORE.close_lever(org.id, project_id, experiment_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/v1/projects/{project_id}/missions",
    response_model=MissionListResponse,
)
async def list_missions(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> MissionListResponse:
    org = _org(principal)
    mongo = _mongo(request)
    try:
        if mongo is not None:
            from mymlfw.saas.db import project_data

            missions = await project_data.list_missions(mongo, org.id, project_id)
        else:
            if BRAIN_STORE.get_project(org.id, project_id) is None:
                raise KeyError("project_not_found")
            missions = BRAIN_STORE.list_missions(org.id, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project_not_found") from exc
    return MissionListResponse(missions=missions)


@router.get("/v1/projects/{project_id}/dashboard", response_model=DashboardResponse)
async def project_dashboard(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> DashboardResponse:
    """Single JSON board for web Overview + CLI ``project dashboard``.

    When Mongo is available, goals/experiments/missions/dead_ends are read via
    ``ProjectScopedDB`` (slim ``$project`` before ``$facet`` warm-up).
    """
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")

    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        dash = await project_data.load_dashboard(mongo, org.id, project_id)
        if dash is None:
            raise HTTPException(status_code=404, detail="project_not_found")
        return dash

    dash = BRAIN_STORE.dashboard(org.id, project_id)
    if dash is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    return dash


@router.post(
    "/v1/projects/{project_id}/share",
    response_model=PublicSnapshotResponse,
)
async def publish_share(
    project_id: str,
    body: PublicSnapshotCreate,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> PublicSnapshotResponse:
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        snap = await project_data.publish_snapshot(
            mongo,
            workspace_id=org.id,
            org_slug=org.slug,
            project_id=project_id,
            include_goals=body.include_goals,
            include_lever_stats=body.include_lever_stats,
            include_dead_end_lessons=body.include_dead_end_lessons,
        )
        if snap is None:
            raise HTTPException(status_code=404, detail="project_not_found")
        return snap
    snap = BRAIN_STORE.publish_snapshot(
        org_id=org.id,
        org_slug=org.slug,
        project_id=project_id,
        include_goals=body.include_goals,
        include_lever_stats=body.include_lever_stats,
        include_dead_end_lessons=body.include_dead_end_lessons,
    )
    if snap is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    return snap


@router.post(
    "/v1/projects/{project_id}/advise",
    response_model=AdviseResponse,
)
async def advise_project(
    project_id: str,
    body: AdviseRequest,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> AdviseResponse:
    """Phase E structured advise — citation_firewall on every egress."""
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    if body.project_id != project_id:
        raise HTTPException(status_code=400, detail="project_id_mismatch")
    from mymlfw.saas.advise import advise_project as _advise

    store = BRAIN_STORE
    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        hydrated = await project_data.hydrate_brain_store(
            mongo, org.id, project_id
        )
        if hydrated is None:
            raise HTTPException(status_code=404, detail="project_not_found")
        store = hydrated
    try:
        return _advise(
            store,
            workspace_id=org.id,
            project_id=project_id,
            task=body.task,
            max_missions=body.max_missions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/v1/projects/{project_id}/brain/query",
    response_model=QueryProjectBrainResponse,
)
async def query_project_brain(
    project_id: str,
    body: QueryProjectBrainRequest,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> QueryProjectBrainResponse:
    """Mid-mission 3-bucket RAG query (Phase E)."""
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    from mymlfw.saas.advise import query_project_brain_from_store

    store = BRAIN_STORE
    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        hydrated = await project_data.hydrate_brain_store(
            mongo, org.id, project_id
        )
        if hydrated is None:
            return QueryProjectBrainResponse(
                status="empty",
                message="project_not_found",
                results=[],
            )
        store = hydrated
    return query_project_brain_from_store(
        store,
        workspace_id=org.id,
        project_id=project_id,
        scope=body.scope,
        max_tokens=body.max_tokens,
        query=body.query,
    )


@router.get("/v1/public/{org_slug}/{slug}")
@public_route
async def get_public_share(
    org_slug: str, slug: str, request: Request
) -> dict[str, Any]:
    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        doc = await project_data.get_public_snapshot(mongo, org_slug, slug)
    else:
        doc = BRAIN_STORE.get_public_snapshot(org_slug, slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="snapshot_not_found")
    return {
        "slug": doc["slug"],
        "org_slug": doc["org_slug"],
        "project_slug": doc["project_slug"],
        "share_path": f"/p/{doc['org_slug']}/{doc['slug']}",
        "redacted": doc["redacted"],
        "entropy": doc["entropy"],
    }
