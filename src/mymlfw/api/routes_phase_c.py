"""Phase C starter routes: OOF presign/confirm, research modes, runner claim stubs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from mymlfw.api.deps import get_current_principal
from mymlfw.runner.client import RunnerClient, mint_job_token_stub
from mymlfw.saas.artifacts import ArtifactError, OofArtifactService, default_memory_service
from mymlfw.saas.ids import new_run_id, new_runner_id
from mymlfw.saas.research import ResearchRunService
from mymlfw.saas.schemas import (
    ErrorSlicesResource,
    JobClaimRequest,
    JobClaimResponse,
    OofArtifactConfirmRequest,
    OofArtifactCreateRequest,
    OofArtifactPresignResponse,
    OofArtifactResponse,
    ResearchRunCreateRequest,
    ResearchRunMode,
    ResearchRunResponse,
    RunnerHeartbeatRequest,
    RunnerHeartbeatResponse,
    TrainStripEvent,
)

router = APIRouter(prefix="/v1", tags=["phase-c"])


def _artifact_services(app_state: Any) -> dict[str, OofArtifactService]:
    store = getattr(app_state, "oof_services", None)
    if store is None:
        store = {}
        app_state.oof_services = store
    return store


def _run_services(app_state: Any) -> dict[str, ResearchRunService]:
    store = getattr(app_state, "research_services", None)
    if store is None:
        store = {}
        app_state.research_services = store
    return store


def _runners(app_state: Any) -> dict[str, RunnerClient]:
    store = getattr(app_state, "runner_clients", None)
    if store is None:
        store = {}
        app_state.runner_clients = store
    return store


def _svc_key(workspace_id: str, project_id: str) -> str:
    return f"{workspace_id}:{project_id}"


def _require_org(principal: dict[str, Any]) -> Any:
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    return org


@router.post(
    "/projects/{project_id}/oof-artifacts",
    response_model=OofArtifactPresignResponse,
)
async def create_oof_artifact(
    project_id: str,
    body: OofArtifactCreateRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> OofArtifactPresignResponse:
    org = _require_org(principal)
    key = _svc_key(org.id, project_id)
    services = _artifact_services(request.app.state)
    if key not in services:
        svc, _store = default_memory_service(workspace_id=org.id, project_id=project_id)
        services[key] = svc
    return services[key].create_upload(body)


@router.post(
    "/projects/{project_id}/oof-artifacts/{oof_id}/confirm",
    response_model=OofArtifactResponse,
)
async def confirm_oof_artifact(
    project_id: str,
    oof_id: str,
    request: Request,
    body: OofArtifactConfirmRequest | None = None,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> OofArtifactResponse:
    org = _require_org(principal)
    key = _svc_key(org.id, project_id)
    services = _artifact_services(request.app.state)
    svc = services.get(key)
    if svc is None:
        raise HTTPException(status_code=404, detail="oof_not_found")
    try:
        return svc.confirm(oof_id, body)
    except ArtifactError as exc:
        status = 404 if exc.code == "oof_not_found" else 409
        if exc.code == "oof_object_missing":
            status = 409
        raise HTTPException(
            status_code=status,
            detail={"error_code": exc.code, "message": exc.message},
        ) from exc


@router.get(
    "/projects/{project_id}/oof-artifacts/{oof_id}",
    response_model=OofArtifactResponse,
)
async def get_oof_artifact(
    project_id: str,
    oof_id: str,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> OofArtifactResponse:
    org = _require_org(principal)
    key = _svc_key(org.id, project_id)
    svc = _artifact_services(request.app.state).get(key)
    if svc is None:
        raise HTTPException(status_code=404, detail="oof_not_found")
    try:
        return svc.get(oof_id)
    except ArtifactError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc


@router.post(
    "/projects/{project_id}/research-runs",
    response_model=ResearchRunResponse,
)
async def create_research_run(
    project_id: str,
    body: ResearchRunCreateRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> ResearchRunResponse:
    org = _require_org(principal)
    key = _svc_key(org.id, project_id)
    services = _run_services(request.app.state)
    if key not in services:
        services[key] = ResearchRunService(workspace_id=org.id, project_id=project_id)
    return services[key].create_run(body)


@router.get(
    "/projects/{project_id}/runs/{run_id}/error_slices",
    response_model=ErrorSlicesResource,
)
async def get_error_slices(
    project_id: str,
    run_id: str,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> ErrorSlicesResource:
    org = _require_org(principal)
    key = _svc_key(org.id, project_id)
    svc = _run_services(request.app.state).get(key)
    if svc is None:
        return ErrorSlicesResource(run_id=run_id, status="not_ready", slices=[])
    return svc.get_error_slices(run_id)


@router.post("/runners/heartbeat", response_model=RunnerHeartbeatResponse)
async def runner_heartbeat(
    body: RunnerHeartbeatRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> RunnerHeartbeatResponse:
    _ = principal
    runners = _runners(request.app.state)
    client = runners.get(body.runner_id)
    if client is None:
        client = RunnerClient(runner_id=body.runner_id, kind=body.kind)
        runners[body.runner_id] = client
    return client.heartbeat(status=body.status, capability_tags=body.capability_tags)


@router.post("/runners/claim-job", response_model=JobClaimResponse)
async def runner_claim_job(
    body: JobClaimRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> JobClaimResponse:
    _ = principal
    runners = _runners(request.app.state)
    client = runners.get(body.runner_id)
    if client is None:
        # Empty claim when runner never heartbeated — still return job-token pattern shape.
        return JobClaimResponse(claimed=False, credentials=None)
    claim = client.claim_job(body)
    if claim.claimed and claim.credentials is None:
        # Should not happen; keep shape stable.
        return JobClaimResponse(claimed=True, credentials=mint_job_token_stub())
    return claim


@router.post("/runners/register", response_model=RunnerHeartbeatResponse)
async def register_local_runner(
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> RunnerHeartbeatResponse:
    _ = principal
    runner_id = new_runner_id()
    client = RunnerClient(runner_id=runner_id)
    _runners(request.app.state)[runner_id] = client
    return client.heartbeat(status="idle")


def train_strip_event_stub(run_id: str | None = None) -> TrainStripEvent:
    return TrainStripEvent(
        run_id=run_id or new_run_id(),
        mode=ResearchRunMode.fold0_smoke,
        progress_pct=0.0,
        message="kit train strip idle",
    )


def format_sse_train_strip(event: TrainStripEvent, event_id: int = 1) -> str:
    payload = event.model_dump_json()
    return f"id: {event_id}\nevent: train_strip\ndata: {payload}\n\n"


def sse_hello_and_train_strip() -> list[str]:
    now = datetime.now(UTC).isoformat()
    return [
        f'id: 0\nevent: hello\ndata: {{"ok":true,"ts":"{now}"}}\n\n',
        format_sse_train_strip(train_strip_event_stub(), event_id=1),
    ]
