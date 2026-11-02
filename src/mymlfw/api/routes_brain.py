"""Phase B brain routes: projects, dashboard, share, demo seed."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from mymlfw.api.deps import get_current_principal
from mymlfw.api.public_route import public_route
from mymlfw.saas.brain_store import BRAIN_STORE
from mymlfw.saas.schemas import (
    DashboardResponse,
    ProjectListResponse,
    ProjectSummary,
    PublicSnapshotCreate,
    PublicSnapshotResponse,
)

router = APIRouter(tags=["brain"])


@router.post("/v1/studio/ensure-demo", response_model=ProjectSummary)
async def ensure_demo(
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectSummary:
    """Seed Demo Campaign on first studio land (idempotent)."""
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    return BRAIN_STORE.ensure_demo_campaign(org_id=org.id, org_slug=org.slug)


@router.get("/v1/projects", response_model=ProjectListResponse)
async def list_projects(
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectListResponse:
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    # Ensure demo exists so studio is never empty after login.
    BRAIN_STORE.ensure_demo_campaign(org_id=org.id, org_slug=org.slug)
    return ProjectListResponse(projects=BRAIN_STORE.list_projects(org.id))


@router.get("/v1/projects/{project_id}", response_model=ProjectSummary)
async def get_project(
    project_id: str,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectSummary:
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    proj = BRAIN_STORE.get_project(org.id, project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    return BRAIN_STORE._summary(proj)


@router.get("/v1/projects/{project_id}/dashboard", response_model=DashboardResponse)
async def project_dashboard(
    project_id: str,
    request: Request,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> DashboardResponse:
    """Single JSON board for web Overview + CLI ``project dashboard``.

    When Mongo is available, experiments use slim ``$project`` before ``$facet``;
    the response shape is always ``DashboardResponse``.
    """
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")

    mongo = getattr(request.app.state, "mongo_db", None)
    if mongo is not None:
        from mymlfw.saas.dashboard import experiments_facet_pipeline
        from mymlfw.saas.db.project_db import ProjectScopedDB

        pdb = ProjectScopedDB(mongo, workspace_id=org.id, project_id=project_id)
        # Best-effort facet warm-up (result merged via brain store for Phase B).
        try:
            cursor = await pdb.experiments.aggregate(experiments_facet_pipeline())
            _ = [doc async for doc in cursor]
        except Exception:
            pass

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
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> PublicSnapshotResponse:
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
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


@router.get("/v1/public/{org_slug}/{slug}")
@public_route
async def get_public_share(org_slug: str, slug: str) -> dict[str, Any]:
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
