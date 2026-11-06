"""Settings / API routes for cloud providers (feature flag ``cloud_runners``)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from mymlfw.api.deps import get_current_principal, require_cloud_operator, require_owner
from mymlfw.saas.providers import (
    CloudProviderError,
    CloudProviderService,
    InMemoryCloudStore,
)
from mymlfw.saas.schemas import (
    CloudConnectAwsRequest,
    CloudConnectRunPodRequest,
    CloudGpuOffer,
    CloudLaunchQuote,
    CloudLaunchRequest,
    CloudProviderAccountResponse,
    CloudProviderName,
    FeatureFlags,
    OrgEntitlements,
    OrgResponse,
    RunnerResponse,
)

router = APIRouter(prefix="/v1", tags=["cloud"])


def _require_org(principal: dict[str, Any]) -> OrgResponse:
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    return org


def _cloud_store(app_state: Any) -> InMemoryCloudStore:
    from mymlfw.saas.control_plane import get_shared_cloud_store

    store = get_shared_cloud_store()
    app_state.cloud_store = store
    return store


def _svc(request: Request, org: OrgResponse) -> CloudProviderService:
    from mymlfw.saas.control_plane import set_org_policy

    flags = org.feature_flags if isinstance(org.feature_flags, FeatureFlags) else FeatureFlags(
        **(org.feature_flags if isinstance(org.feature_flags, dict) else {})
    )
    ents = (
        org.entitlements
        if isinstance(org.entitlements, OrgEntitlements)
        else OrgEntitlements(**(org.entitlements if isinstance(org.entitlements, dict) else {}))
    )
    set_org_policy(org.id, feature_flags=flags, entitlements=ents)
    cache = getattr(request.app.state, "cloud_services", None)
    if cache is None:
        cache = {}
        request.app.state.cloud_services = cache
    svc = cache.get(org.id)
    if svc is None:
        # Tests may inject mocks via app.state; production leaves transports None
        # so CloudProviderService uses Live* once the user seals credentials.
        rp = getattr(request.app.state, "cloud_runpod_transport", None)
        aws = getattr(request.app.state, "cloud_aws_transport", None)
        svc = CloudProviderService(
            org_id=org.id,
            store=_cloud_store(request.app.state),
            feature_flags=flags,
            entitlements=ents,
            runpod_transport=rp,
            aws_transport=aws,
        )
        cache[org.id] = svc
    else:
        svc.feature_flags = flags
        svc.entitlements = ents
        svc.store = _cloud_store(request.app.state)
    return svc


def _http_err(exc: CloudProviderError) -> HTTPException:
    status = 403 if exc.code in {"feature_disabled", "cloud_budget_exceeded"} else 400
    if exc.code in {"runner_not_found", "not_connected"}:
        status = 404
    return HTTPException(
        status_code=status,
        detail={"error_code": exc.code, "message": exc.message},
    )


@router.get(
    "/orgs/current/cloud/accounts",
    response_model=list[CloudProviderAccountResponse],
)
async def list_cloud_accounts(
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> list[CloudProviderAccountResponse]:
    org = _require_org(principal)
    try:
        return _svc(request, org).list_accounts()
    except CloudProviderError as exc:
        raise _http_err(exc) from exc


@router.post(
    "/orgs/current/cloud/connect/runpod",
    response_model=CloudProviderAccountResponse,
)
async def connect_runpod(
    body: CloudConnectRunPodRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> CloudProviderAccountResponse:
    org = _require_org(principal)
    require_owner(principal, action="cloud connect runpod")
    try:
        return _svc(request, org).connect_runpod(api_key=body.api_key)
    except CloudProviderError as exc:
        raise _http_err(exc) from exc


@router.post(
    "/orgs/current/cloud/connect/aws",
    response_model=CloudProviderAccountResponse,
)
async def connect_aws(
    body: CloudConnectAwsRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> CloudProviderAccountResponse:
    org = _require_org(principal)
    require_owner(principal, action="cloud connect aws")
    try:
        return _svc(request, org).connect_aws(role_arn=body.role_arn, region=body.region)
    except CloudProviderError as exc:
        raise _http_err(exc) from exc


@router.post(
    "/orgs/current/cloud/disconnect/{provider}",
    response_model=CloudProviderAccountResponse,
)
async def disconnect_provider(
    provider: CloudProviderName,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> CloudProviderAccountResponse:
    org = _require_org(principal)
    require_owner(principal, action="cloud disconnect")
    try:
        return _svc(request, org).disconnect(provider.value)  # type: ignore[arg-type]
    except CloudProviderError as exc:
        raise _http_err(exc) from exc


@router.get(
    "/orgs/current/cloud/gpus",
    response_model=list[CloudGpuOffer],
)
async def list_cloud_gpus(
    provider: CloudProviderName,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> list[CloudGpuOffer]:
    org = _require_org(principal)
    try:
        return _svc(request, org).list_gpus(provider.value)  # type: ignore[arg-type]
    except CloudProviderError as exc:
        raise _http_err(exc) from exc


@router.get(
    "/orgs/current/cloud/quote",
    response_model=CloudLaunchQuote,
)
async def quote_cloud_launch(
    provider: CloudProviderName,
    gpu_type: str,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> CloudLaunchQuote:
    org = _require_org(principal)
    try:
        return _svc(request, org).quote_launch(
            provider=provider.value,  # type: ignore[arg-type]
            gpu_type=gpu_type,
        )
    except CloudProviderError as exc:
        raise _http_err(exc) from exc


@router.post(
    "/orgs/current/cloud/launch",
    response_model=RunnerResponse,
)
async def launch_cloud_runner(
    body: CloudLaunchRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> RunnerResponse:
    org = _require_org(principal)
    require_cloud_operator(principal, action="cloud launch")
    try:
        return _svc(request, org).launch(
            provider=body.provider.value,  # type: ignore[arg-type]
            gpu_type=body.gpu_type,
            quote_accepted_micros_hr=body.cost_estimate_micros_hr,
            spot=body.spot,
        )
    except CloudProviderError as exc:
        raise _http_err(exc) from exc


@router.get(
    "/orgs/current/runners",
    response_model=list[RunnerResponse],
)
async def list_org_runners(
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> list[RunnerResponse]:
    org = _require_org(principal)
    try:
        return _svc(request, org).list_runners()
    except CloudProviderError as exc:
        raise _http_err(exc) from exc


@router.post(
    "/orgs/current/runners/{runner_id}/stop",
    response_model=RunnerResponse,
)
async def stop_runner(
    runner_id: str,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> RunnerResponse:
    org = _require_org(principal)
    require_cloud_operator(principal, action="cloud stop")
    try:
        return _svc(request, org).stop(runner_id)
    except CloudProviderError as exc:
        raise _http_err(exc) from exc


@router.post(
    "/orgs/current/runners/{runner_id}/terminate",
    response_model=RunnerResponse,
)
async def terminate_runner(
    runner_id: str,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> RunnerResponse:
    org = _require_org(principal)
    require_cloud_operator(principal, action="cloud terminate")
    try:
        return _svc(request, org).terminate(runner_id)
    except CloudProviderError as exc:
        raise _http_err(exc) from exc


@router.post("/orgs/current/cloud/sweep-orphans")
async def sweep_orphans(
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    """Owner/operator only — destructive remote terminates."""
    org = _require_org(principal)
    persona = principal.get("persona")
    # Dev personas: only owner may sweep; unset persona allowed for API keys/tests.
    if persona in {"member", "viewer", "agent"}:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "forbidden",
                "message": "cloud orphan sweep requires owner persona",
            },
        )
    try:
        result = _svc(request, org).sweep_orphans()
        # Side-effect audit via outbox (Mongo when available, else memory).
        mongo = getattr(request.app.state, "mongo_db", None)
        if mongo is not None:
            from mymlfw.saas.db.outbox import enqueue_outbox_event

            await enqueue_outbox_event(
                mongo,
                event_type="cloud.orphan_sweep",
                payload=result,
                workspace_id=org.id,
            )
        else:
            from mymlfw.saas.control_plane import enqueue_memory_outbox

            enqueue_memory_outbox(
                event_type="cloud.orphan_sweep",
                payload=result,
                workspace_id=org.id,
            )
        return result
    except CloudProviderError as exc:
        raise _http_err(exc) from exc
