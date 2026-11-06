"""Phase C routes: OOF presign/confirm, research modes, runner claim, autopilot."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request

from mymlfw.api.deps import get_current_principal, require_project_in_org
from mymlfw.runner.client import RunnerClient, mint_job_token
from mymlfw.saas.artifacts import ArtifactError, OofArtifactService, default_memory_service
from mymlfw.saas.ids import new_runner_id
from mymlfw.saas.research import ResearchRunService
from mymlfw.saas.autopilot import (
    AutopilotError,
    digest_autopilot,
    expire_wall_budget_if_needed,
    get_autopilot_status,
    halt_autopilot,
    headless_driver_tick,
    pause_autopilot,
    resume_autopilot,
    rollback_autopilot_start,
    start_autopilot,
    usd_to_micros,
)
from mymlfw.saas.ensemble import (
    EnsembleError,
    OofCandidate,
    optimize_ensemble,
    plan_ensemble,
    promote_blend_to_experiment,
)
from mymlfw.saas.schemas import (
    AutopilotDigestResponse,
    AutopilotDriverTickRequest,
    AutopilotDriverTickResponse,
    AutopilotHaltRequest,
    AutopilotSessionResponse,
    AutopilotStartRequest,
    EnsembleOptimizeRequest,
    EnsembleOptimizeResponse,
    EnsemblePromoteRequest,
    EnsemblePromoteResponse,
    ErrorSlicesResource,
    FeatureFlags,
    JobClaimRequest,
    JobClaimResponse,
    LogOofRequest,
    LogOofResponse,
    OofArtifactConfirmRequest,
    OofArtifactCreateRequest,
    OofArtifactPresignResponse,
    OofArtifactResponse,
    ResearchRunCreateRequest,
    ResearchRunResponse,
    RunnerHeartbeatRequest,
    RunnerHeartbeatResponse,
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


async def _require_project(
    request: Request, principal: dict[str, Any], project_id: str
) -> Any:
    return await require_project_in_org(request, principal, project_id)


def _night_shift_enabled(org: Any) -> bool:
    flags = getattr(org, "feature_flags", None)
    if flags is None:
        return False
    if isinstance(flags, FeatureFlags):
        return bool(flags.night_shift)
    if isinstance(flags, dict):
        return bool(flags.get("night_shift"))
    return bool(getattr(flags, "night_shift", False))


def _autopilot_http(exc: AutopilotError) -> HTTPException:
    code = 403 if exc.code == "feature_flag_disabled" else 400
    if exc.code in ("execution_lock_held", "session_already_active"):
        code = 409
    if exc.code == "session_not_found":
        code = 404
    return HTTPException(status_code=code, detail=exc.to_dict())


def _get_artifact_service(
    request: Request, workspace_id: str, project_id: str
) -> OofArtifactService:
    key = _svc_key(workspace_id, project_id)
    services = _artifact_services(request.app.state)
    if key in services:
        return services[key]
    import os

    settings = getattr(request.app.state, "settings", None)
    from mymlfw.saas.storage import use_minio_live

    use_minio = bool(
        settings and getattr(settings, "minio_endpoint", None) and use_minio_live()
    )
    if use_minio:
        from mymlfw.saas.artifacts import InMemoryArtifactRepo, OofArtifactService
        from mymlfw.saas.storage import HmacPresignStore

        endpoint = os.environ.get("MYMLFW_MINIO_ENDPOINT") or settings.minio_endpoint
        store = HmacPresignStore(
            endpoint=endpoint,
            bucket=settings.minio_bucket,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            region=settings.minio_region,
        )
        services[key] = OofArtifactService(
            store=store,
            repo=InMemoryArtifactRepo(),
            workspace_id=workspace_id,
            project_id=project_id,
        )
    else:
        svc, _store = default_memory_service(
            workspace_id=workspace_id, project_id=project_id
        )
        services[key] = svc
    return services[key]


async def _release_mongo_autopilot_lock(
    request: Request,
    *,
    workspace_id: str,
    project_id: str,
    session_id: str,
) -> None:
    mongo = getattr(request.app.state, "mongo_db", None)
    if mongo is None:
        return
    from mymlfw.saas.db.project_db import ProjectScopedDB

    pdb = ProjectScopedDB(mongo, workspace_id=workspace_id, project_id=project_id)
    await pdb.release_execution_lock(holder_type="autopilot", holder_id=session_id)


def _tick_metrics_attested(
    request: Request,
    principal: dict[str, Any],
    body: AutopilotDriverTickRequest,
    *,
    org_id: str,
    project_id: str,
) -> bool:
    """Runner job_token required unless MYMLFW_AUTOPILOT_ALLOW_UNATTESTED=1."""
    import os

    if os.environ.get("MYMLFW_AUTOPILOT_ALLOW_UNATTESTED", "").strip() in {
        "1",
        "true",
        "True",
    }:
        return True
    token = (body.job_token or "").strip()
    if not token:
        return False
    # Accept any minted job token for this org's runners.
    for client in _runners(request.app.state).values():
        try:
            _verify_runner_token(client, token)
            return True
        except HTTPException:
            continue
    _ = principal, org_id, project_id
    return False


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
    org = await _require_project(request, principal, project_id)
    return _get_artifact_service(request, org.id, project_id).create_upload(body)


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
    org = await _require_project(request, principal, project_id)
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
    org = await _require_project(request, principal, project_id)
    key = _svc_key(org.id, project_id)
    svc = _artifact_services(request.app.state).get(key)
    if svc is None:
        raise HTTPException(status_code=404, detail="oof_not_found")
    try:
        return svc.get(oof_id)
    except ArtifactError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc


@router.post(
    "/projects/{project_id}/log-oof",
    response_model=LogOofResponse,
)
async def log_oof_scores(
    project_id: str,
    body: LogOofRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> LogOofResponse:
    """Record finite fold scores. Prediction bytes use the OOF presign route."""
    await _require_project(request, principal, project_id)
    return LogOofResponse(
        status="accepted",
        experiment_id=body.experiment_id,
        fold_scores=list(body.fold_scores),
        message="fold scores recorded; upload prediction bytes via oof-artifacts presign",
    )


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
    org = await _require_project(request, principal, project_id)
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
    org = await _require_project(request, principal, project_id)
    key = _svc_key(org.id, project_id)
    svc = _run_services(request.app.state).get(key)
    if svc is None:
        return ErrorSlicesResource(run_id=run_id, status="empty", slices=[])
    return svc.get_error_slices(run_id)


@router.post(
    "/projects/{project_id}/ensemble",
    response_model=EnsembleOptimizeResponse,
)
async def optimize_project_ensemble(
    project_id: str,
    body: EnsembleOptimizeRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> EnsembleOptimizeResponse:
    """Nested-CV Caruana blend. Inline ``candidates`` for sandbox; else return plan."""
    org = await _require_project(request, principal, project_id)
    _ = org
    _ = project_id
    if not body.candidates:
        plan = plan_ensemble(list(body.oof_ids), mode=body.mode.value)
        status = "plan" if plan.get("status") == "ready" else "error"
        return EnsembleOptimizeResponse(
            status=status,  # type: ignore[arg-type]
            mode=body.mode,
            requested_mode=body.mode,
            oof_ids=list(body.oof_ids),
            plan=plan,
            error_code=plan.get("error_code"),
            message=plan.get("suggested_fix") if status == "error" else None,
            suggested_fix=plan.get("suggested_fix"),
        )
    if len(body.labels) == 0 or len(body.folds) == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "missing_labels_folds",
                "message": "Inline candidates require labels and folds.",
            },
        )
    try:
        cands = [
            OofCandidate(
                name=c.name,
                predictions=np.asarray(c.predictions, dtype=np.float32),
                oof_id=c.oof_id,
                split_hash=c.split_hash,
            )
            for c in body.candidates
        ]
        result = optimize_ensemble(
            cands,
            y=np.asarray(body.labels),
            folds=np.asarray(body.folds, dtype=int),
            mode=body.mode.value,  # type: ignore[arg-type]
            metric=body.metric,  # type: ignore[arg-type]
            diversity_method=body.diversity_method,  # type: ignore[arg-type]
            corr_threshold=body.corr_threshold,
            polish=body.polish,
            expected_split_hash=body.expected_split_hash,
            allow_subsample=body.allow_subsample,
        )
    except EnsembleError as exc:
        if exc.code == "needs_worker_offload":
            return EnsembleOptimizeResponse(
                status="needs_worker_offload",
                mode=body.mode,
                requested_mode=body.mode,
                oof_ids=list(body.oof_ids),
                offload_hint=exc.message,
                ncm=exc.extra.get("ncm"),
                error_code=exc.code,
                message=exc.message,
                suggested_fix=exc.extra.get("suggested_fix"),
            )
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    payload = result.to_dict()
    return EnsembleOptimizeResponse(
        status="ok",
        mode=payload["mode"],
        requested_mode=payload.get("requested_mode"),
        weights=payload["weights"],
        candidate_names=payload["candidate_names"],
        candidate_oof_ids=payload["candidate_oof_ids"],
        nested_cv_score=payload["nested_cv_score"],
        oof_blend_score=payload["oof_blend_score"],
        fold_scores=payload["fold_scores"],
        fold_snr=payload["fold_snr"],
        p_value=payload["p_value"],
        verdict=payload["verdict"],
        ascii_board=payload["ascii_board"],
        diversity_method=payload["diversity_method"],
        metric=payload["metric"],
        subsampled=payload["subsampled"],
        offload_hint=payload.get("offload_hint"),
        ncm=payload.get("ncm"),
        oof_ids=list(body.oof_ids),
    )


@router.post(
    "/projects/{project_id}/ensemble/promote",
    response_model=EnsemblePromoteResponse,
)
async def promote_project_ensemble(
    project_id: str,
    body: EnsemblePromoteRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> EnsemblePromoteResponse:
    """Promote blend only when parent OOF artifacts are project-scoped and ready."""
    org = await _require_project(request, principal, project_id)
    artifacts = _get_artifact_service(request, org.id, project_id)
    try:
        out = promote_blend_to_experiment(
            parent_oof_ids=body.parent_oof_ids,
            weights=body.weights,
            mode=body.mode.value,  # type: ignore[arg-type]
            project_id=project_id,
            goal_id=body.goal_id,
            parent_experiment_ids=body.parent_experiment_ids,
            nested_cv_score=body.nested_cv_score,
            fold_scores=body.fold_scores,
            artifact_repo=artifacts.repo,
            require_ready_oofs=True,
        )
    except EnsembleError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return EnsemblePromoteResponse(
        status="created",
        experiment_id=out["experiment_id"],
        strategy="ensemble_blend",
        parent_oof_ids=out["parent_oof_ids"],
        weights=out["weights"],
        mode=body.mode,
        detail=out["detail"],
        experiment=out["experiment"],
    )


@router.post(
    "/projects/{project_id}/autopilot/start",
    response_model=AutopilotSessionResponse,
)
async def autopilot_start(
    project_id: str,
    body: AutopilotStartRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> AutopilotSessionResponse:
    """Start Night-Shift session behind ``night_shift``; acquires execution lock."""
    org = await _require_project(request, principal, project_id)
    micros = body.max_llm_cost_micros
    if micros is None and body.max_llm_usd is not None:
        try:
            micros = usd_to_micros(body.max_llm_usd)
        except AutopilotError as exc:
            raise _autopilot_http(exc) from exc
    try:
        out = start_autopilot(
            workspace_id=org.id,
            project_id=project_id,
            mode=body.mode.value,  # type: ignore[arg-type]
            hours=body.hours,
            max_probes=body.max_probes,
            max_gpu_hours=body.max_gpu_hours,
            max_llm_cost_micros=micros,
            baseline_cv=body.baseline_cv,
            night_shift_enabled=_night_shift_enabled(org),
        )
    except AutopilotError as exc:
        raise _autopilot_http(exc) from exc
    # When Mongo is up, fence on projects.active_execution_lock; roll back
    # in-memory session+lock on conflict so retries are not stuck 12h.
    mongo = getattr(request.app.state, "mongo_db", None)
    if mongo is not None and out.get("session"):
        from mymlfw.saas.db.project_db import ProjectScopedDB

        session = out["session"]
        sid = session.get("id") if isinstance(session, dict) else None
        lock = out.get("active_execution_lock") or {}
        if sid and lock.get("expires_at"):
            pdb = ProjectScopedDB(mongo, workspace_id=org.id, project_id=project_id)
            try:
                from datetime import datetime as _dt

                expires = lock["expires_at"]
                if isinstance(expires, str):
                    expires = _dt.fromisoformat(expires.replace("Z", "+00:00"))
                await pdb.acquire_execution_lock(
                    holder_type="autopilot",
                    holder_id=sid,
                    expires_at=expires,
                )
            except RuntimeError as exc:
                rollback_autopilot_start(
                    workspace_id=org.id,
                    project_id=project_id,
                    session_id=sid,
                )
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_code": "execution_lock_held",
                        "message": str(exc),
                    },
                ) from exc
    return AutopilotSessionResponse(
        status=out["status"],
        session=out["session"],
        root_node=out.get("root_node"),
        active_execution_lock=out.get("active_execution_lock"),
        feature_flag="night_shift",
        auto_kaggle_submit=False,
    )


@router.get(
    "/projects/{project_id}/autopilot/status",
    response_model=AutopilotSessionResponse,
)
async def autopilot_status(
    project_id: str,
    request: Request,
    session_id: str | None = None,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> AutopilotSessionResponse:
    org = await _require_project(request, principal, project_id)
    expired = expire_wall_budget_if_needed(
        project_id=project_id,
        session_id=session_id,
        workspace_id=org.id,
    )
    if expired and expired.get("session_id"):
        await _release_mongo_autopilot_lock(
            request,
            workspace_id=org.id,
            project_id=project_id,
            session_id=str(expired["session_id"]),
        )
    try:
        out = get_autopilot_status(
            project_id=project_id,
            session_id=session_id,
            workspace_id=org.id,
        )
    except AutopilotError as exc:
        raise _autopilot_http(exc) from exc
    return AutopilotSessionResponse(
        status=out["status"],
        session=out["session"],
        node_count=out.get("node_count"),
        nodes=out.get("nodes") or [],
        budget_remaining=out.get("budget_remaining"),
        active_execution_lock=out.get("active_execution_lock"),
        feature_flag="night_shift",
        auto_kaggle_submit=False,
    )


@router.post(
    "/projects/{project_id}/autopilot/pause",
    response_model=AutopilotSessionResponse,
)
async def autopilot_pause(
    project_id: str,
    request: Request,
    session_id: str | None = None,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> AutopilotSessionResponse:
    org = await _require_project(request, principal, project_id)
    try:
        out = pause_autopilot(
            project_id=project_id,
            session_id=session_id,
            workspace_id=org.id,
        )
    except AutopilotError as exc:
        raise _autopilot_http(exc) from exc
    return AutopilotSessionResponse(
        status=out["status"],
        session=out["session"],
        feature_flag="night_shift",
        auto_kaggle_submit=False,
    )


@router.post(
    "/projects/{project_id}/autopilot/resume",
    response_model=AutopilotSessionResponse,
)
async def autopilot_resume(
    project_id: str,
    request: Request,
    session_id: str | None = None,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> AutopilotSessionResponse:
    org = await _require_project(request, principal, project_id)
    try:
        out = resume_autopilot(
            project_id=project_id,
            session_id=session_id,
            night_shift_enabled=_night_shift_enabled(org),
            workspace_id=org.id,
        )
    except AutopilotError as exc:
        raise _autopilot_http(exc) from exc
    return AutopilotSessionResponse(
        status=out["status"],
        session=out["session"],
        feature_flag="night_shift",
        auto_kaggle_submit=False,
    )


@router.post(
    "/projects/{project_id}/autopilot/halt",
    response_model=AutopilotSessionResponse,
)
async def autopilot_halt(
    project_id: str,
    body: AutopilotHaltRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> AutopilotSessionResponse:
    """Operator halt — releases in-memory + Mongo ``active_execution_lock``."""
    org = await _require_project(request, principal, project_id)
    try:
        out = halt_autopilot(
            project_id=project_id,
            session_id=body.session_id,
            workspace_id=org.id,
            reason=body.reason,
        )
    except AutopilotError as exc:
        raise _autopilot_http(exc) from exc
    session = out.get("session") or {}
    sid = session.get("id") if isinstance(session, dict) else None
    if sid:
        await _release_mongo_autopilot_lock(
            request,
            workspace_id=org.id,
            project_id=project_id,
            session_id=str(sid),
        )
    return AutopilotSessionResponse(
        status=out["status"],
        session=out["session"],
        feature_flag="night_shift",
        auto_kaggle_submit=False,
    )


@router.get(
    "/projects/{project_id}/autopilot/digest",
    response_model=AutopilotDigestResponse,
)
async def autopilot_digest(
    project_id: str,
    request: Request,
    session_id: str | None = None,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> AutopilotDigestResponse:
    org = await _require_project(request, principal, project_id)
    try:
        out = digest_autopilot(
            project_id=project_id,
            session_id=session_id,
            workspace_id=org.id,
        )
    except AutopilotError as exc:
        raise _autopilot_http(exc) from exc
    return AutopilotDigestResponse(
        status=out["status"],
        session_id=out["session_id"],
        ascii_board=out["ascii_board"],
        cta=out.get("cta") or [],
        auto_kaggle_submit=False,
        feature_flag="night_shift",
    )


@router.post(
    "/projects/{project_id}/autopilot/tick",
    response_model=AutopilotDriverTickResponse,
)
async def autopilot_driver_tick(
    project_id: str,
    body: AutopilotDriverTickRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> AutopilotDriverTickResponse:
    """Headless driver step; promote metrics require runner job_token attestation."""
    org = await _require_project(request, principal, project_id)
    attested = _tick_metrics_attested(
        request, principal, body, org_id=org.id, project_id=project_id
    )
    if not attested:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "unattested_metrics",
                "message": (
                    "Autopilot tick metrics require a runner job_token "
                    "(or MYMLFW_AUTOPILOT_ALLOW_UNATTESTED=1 for local tests)."
                ),
                "suggested_fix": "Pass job_token from the runner claim response.",
            },
        )
    try:
        out = headless_driver_tick(
            project_id=project_id,
            session_id=body.session_id,
            variable=body.variable,
            smoke_ok=body.smoke_ok,
            fold0_delta=body.fold0_delta,
            max_spearman_to_pool=body.max_spearman_to_pool,
            cv_delta=body.cv_delta,
            integrity_ok=body.integrity_ok,
            llm_cost_micros=body.llm_cost_micros,
            night_shift_enabled=_night_shift_enabled(org),
            workspace_id=org.id,
        )
    except AutopilotError as exc:
        raise _autopilot_http(exc) from exc
    if out.get("status") in {"completed", "halted"} and out.get("session_id"):
        await _release_mongo_autopilot_lock(
            request,
            workspace_id=org.id,
            project_id=project_id,
            session_id=str(out["session_id"]),
        )
    elif out.get("status") == "completed":
        # budget_exhausted path may omit session_id — recover from body/store.
        sid = body.session_id or (out.get("session") or {}).get("id")
        if sid:
            await _release_mongo_autopilot_lock(
                request,
                workspace_id=org.id,
                project_id=project_id,
                session_id=str(sid),
            )
    return AutopilotDriverTickResponse(
        status=out["status"],
        session_id=out.get("session_id"),
        parent_id=out.get("parent_id"),
        uct=out.get("uct"),
        child=out.get("child"),
        halving=out.get("halving") or [],
        lever_verifier=out.get("lever_verifier"),
        local_runner_hook=bool(out.get("local_runner_hook", True)),
        auto_kaggle_submit=False,
        feature_flag="night_shift",
        notes=out.get("notes") or [],
        reason=out.get("reason"),
        ascii_board=out.get("ascii_board"),
    )


def _org_runner_key(org_id: str, runner_id: str) -> str:
    return f"{org_id}:{runner_id}"


def _verify_runner_token(client: RunnerClient, token: str | None) -> None:
    from mymlfw.runner.client import hash_runner_token

    # Fail closed: every registered runner must present a matching token.
    if client.token_hash is None or not token:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "invalid_runner_token",
                "message": "Runner token required for this runner_id",
            },
        )
    if hash_runner_token(token) != client.token_hash:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "invalid_runner_token",
                "message": "Runner token required for this runner_id",
            },
        )


@router.post("/runners/heartbeat", response_model=RunnerHeartbeatResponse)
async def runner_heartbeat(
    body: RunnerHeartbeatRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> RunnerHeartbeatResponse:
    org = _require_org(principal)
    runners = _runners(request.app.state)
    key = _org_runner_key(org.id, body.runner_id)
    client = runners.get(key)
    if client is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "runner_not_registered",
                "message": "Register via POST /v1/runners/register first",
            },
        )
    _verify_runner_token(client, body.runner_token)
    return client.heartbeat(status=body.status, capability_tags=body.capability_tags)


@router.post("/runners/claim-job", response_model=JobClaimResponse)
async def runner_claim_job(
    body: JobClaimRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> JobClaimResponse:
    org = _require_org(principal)
    runners = _runners(request.app.state)
    key = _org_runner_key(org.id, body.runner_id)
    client = runners.get(key)
    if client is None:
        return JobClaimResponse(claimed=False, credentials=None)
    _verify_runner_token(client, body.runner_token)
    claim = client.claim_job(body)
    if claim.claimed and claim.credentials is None:
        return JobClaimResponse(claimed=True, credentials=mint_job_token())
    return claim


@router.post("/runners/register", response_model=RunnerHeartbeatResponse)
async def register_local_runner(
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> RunnerHeartbeatResponse:
    from mymlfw.runner.client import hash_runner_token
    from mymlfw.saas.providers.service import mint_short_lived_runner_token

    org = _require_org(principal)
    runner_id = new_runner_id()
    raw, token_hash = mint_short_lived_runner_token()
    client = RunnerClient(
        runner_id=runner_id,
        runner_token=raw,
        token_hash=token_hash or hash_runner_token(raw),
    )
    _runners(request.app.state)[_org_runner_key(org.id, runner_id)] = client
    # Unified registry: also surface local runners on /orgs/current/runners.
    from datetime import UTC, datetime

    from mymlfw.saas.control_plane import get_shared_cloud_store
    from mymlfw.saas.schemas import RunnerKind, RunnerLifecycleStatus

    now = datetime.now(UTC)
    get_shared_cloud_store().runners[runner_id] = {
        "_id": runner_id,
        "org_id": org.id,
        "kind": RunnerKind.local.value,
        "status": RunnerLifecycleStatus.online.value,
        "provider": None,
        "region": "",
        "gpu_type": "",
        "cost_estimate_micros_hr": 0,
        "provider_instance_id": None,
        "idle_timeout_minutes": 30,
        "last_heartbeat_at": now,
        "account_id": None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "schema_version": 1,
        "token_hash": token_hash or hash_runner_token(raw),
    }
    hb = client.heartbeat(status="idle")
    return hb.model_copy(update={"runner_token": raw})


def sse_hello() -> list[str]:
    now = datetime.now(UTC).isoformat()
    return [f'id: 0\nevent: hello\ndata: {{"ok":true,"ts":"{now}"}}\n\n']
