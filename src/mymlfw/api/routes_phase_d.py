"""Kaggle, git, credits, and elicitation HTTP routes."""

from __future__ import annotations

from typing import Any

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request

from mymlfw.api.deps import get_current_principal, require_owner
from mymlfw.saas.elicitation import ElicitationError, confirm_elicitation
from mymlfw.saas.git_sync import (
    git_sync_plan,
    mission_complete_git_job,
    verify_github_webhook,
)
from mymlfw.saas.kaggle_client import KaggleClientError, resolve_kaggle_token
from mymlfw.saas.kaggle_service import (
    gated_kaggle_push,
    import_competition_data,
    ingest_discussion,
    intel_panel,
    open_sealed_kaggle_token,
    package_submission,
    rate_limit,
    refresh_intel_cache,
    seal_kaggle_token,
    submission_distribution_diff,
    sync_competition_from_kaggle,
    verify_public_notebook,
)
from mymlfw.saas.provenance import (
    export_credits_bundle,
    render_provenance_ascii_board,
    sync_harvest_on_complete,
    verify_project_licenses,
)
from mymlfw.saas.writeup import render_writeup

router = APIRouter(prefix="/v1", tags=["phase-d"])


def _org(principal: dict[str, Any]) -> Any:
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    return org


@router.post("/projects/{project_id}/credits/harvest")
async def harvest_credits(
    project_id: str,
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    org = _org(principal)
    credits, outbox = sync_harvest_on_complete(
        workspace_id=org.id,
        project_id=project_id,
        source=str(body.get("source") or ""),
    )
    return {
        "credits": credits,
        "outbox": outbox,
        "ascii_board": render_provenance_ascii_board(credits),
    }


@router.post("/projects/{project_id}/credits/verify")
async def verify_credits(
    project_id: str,
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    _org(principal)
    _ = project_id
    return verify_project_licenses(
        body.get("credits") or [],
        gate=str(body.get("gate") or "kaggle_submit"),
    )


@router.post("/projects/{project_id}/credits/export")
async def export_credits(
    project_id: str,
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, str]:
    _org(principal)
    _ = project_id
    return export_credits_bundle(body.get("credits") or [], title=str(body.get("title") or "campaign"))


def _mongo(request: Request) -> Any:
    return getattr(request.app.state, "mongo_db", None)


async def _project_competition(
    request: Request, org_id: str, project_id: str, fallback: str
) -> tuple[str, dict[str, Any] | None]:
    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        proj = await project_data.get_project(mongo, org_id, project_id)
        if proj is None:
            raise HTTPException(status_code=404, detail="project_not_found")
        comp = str(proj.get("kaggle_competition") or fallback or "").strip()
        return comp or fallback, proj
    # Dev fallback when Mongo did not bind: read competition from BRAIN_STORE.
    from mymlfw.saas.brain_store import BRAIN_STORE

    proj = BRAIN_STORE.get_project(org_id, project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    comp = str(proj.get("kaggle_competition") or fallback or "").strip()
    return comp or fallback, proj


@router.get("/projects/{project_id}/kaggle/intel")
async def kaggle_intel(
    project_id: str,
    request: Request,
    competition: str = "",
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    org = _org(principal)
    ip = request.client.host if request.client else "local"
    try:
        rate_limit(ip)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    comp, proj = await _project_competition(
        request, org.id, project_id, competition or "demo"
    )
    cached = None
    if proj and isinstance(proj.get("kaggle_intel"), dict):
        cached = proj["kaggle_intel"]
    return intel_panel(competition=comp, cached=cached)


@router.post("/projects/{project_id}/kaggle/discussions")
async def kaggle_discussion(
    project_id: str,
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    org = _org(principal)
    return ingest_discussion(
        text=str(body.get("text") or ""),
        author=str(body.get("author") or "unknown"),
        workspace_id=org.id,
        project_id=project_id,
    )


@router.post("/projects/{project_id}/kaggle/refresh")
async def kaggle_refresh(
    project_id: str,
    body: dict[str, Any],
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    """Sync intel from Kaggle Public API when credentials exist; else accept cache payload."""
    org = _org(principal)
    ip = request.client.host if request.client else "local"
    try:
        rate_limit(ip)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    live = bool(body.get("live", True))
    comp_fallback = str(body.get("competition") or "")
    comp, proj = await _project_competition(
        request, org.id, project_id, comp_fallback or "demo"
    )
    if not live:
        panel = refresh_intel_cache(
            competition=comp,
            discussions=list(body.get("discussions") or []),
            kernels=list(body.get("kernels") or []),
            refreshed_by="client",
        )
    else:
        token = _project_kaggle_token(proj)
        try:
            panel = sync_competition_from_kaggle(
                competition=comp,
                token=token,
                team_hint=str(body.get("team") or "") or None,
            )
        except KaggleClientError as exc:
            raise HTTPException(
                status_code=502, detail=f"{exc.code}:{exc.message}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        panel = await project_data.store_project_kaggle_intel(
            mongo, workspace_id=org.id, project_id=project_id, panel=panel
        )
    else:
        from mymlfw.saas.brain_store import BRAIN_STORE
        from mymlfw.saas.db.kaggle_docs import intel_doc_for_mongo

        panel = intel_doc_for_mongo(panel)
        BRAIN_STORE.set_kaggle_intel(org.id, project_id, panel)
    # Never echo secrets.
    return {k: v for k, v in panel.items() if not str(k).startswith("_")}


def _project_kaggle_token(proj: dict[str, Any] | None) -> str:
    if proj and isinstance(proj.get("kaggle_token_blob"), dict):
        try:
            return open_sealed_kaggle_token(proj["kaggle_token_blob"])
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400, detail=f"kaggle_token_unseal_failed:{exc}"
            ) from exc
    return resolve_kaggle_token()


@router.post("/projects/{project_id}/kaggle/import-data")
async def kaggle_import_data(
    project_id: str,
    body: dict[str, Any],
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    """Import competition file inventory (+ optional zip download via Kaggle API)."""
    org = _org(principal)
    ip = request.client.host if request.client else "local"
    try:
        rate_limit(ip)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    comp_fallback = str(body.get("competition") or "")
    comp, proj = await _project_competition(
        request, org.id, project_id, comp_fallback or "demo"
    )
    if not comp or comp == "demo":
        raise HTTPException(status_code=400, detail="kaggle_competition_required")
    download = bool(body.get("download", True))
    file_name = body.get("file_name")
    file_name_s = str(file_name).strip() if file_name else None
    token = _project_kaggle_token(proj)
    try:
        result = import_competition_data(
            competition=comp,
            workspace_id=org.id,
            project_id=project_id,
            token=token,
            download=download,
            file_name=file_name_s,
        )
    except KaggleClientError as exc:
        raise HTTPException(
            status_code=502, detail=f"{exc.code}:{exc.message}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    mongo = _mongo(request)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        inventory = await project_data.store_project_kaggle_data(
            mongo,
            workspace_id=org.id,
            project_id=project_id,
            inventory=result["inventory"],
            credit=result.get("credit"),
        )
        result = {**result, "inventory": inventory}
    else:
        from mymlfw.saas.brain_store import BRAIN_STORE
        from mymlfw.saas.db.kaggle_docs import inventory_doc_for_mongo

        inventory = inventory_doc_for_mongo(result["inventory"])
        BRAIN_STORE.set_kaggle_data(org.id, project_id, inventory)
        result = {**result, "inventory": inventory}
    return result


@router.post("/projects/{project_id}/kaggle/push")
async def kaggle_push(
    project_id: str,
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    _org(principal)
    _ = project_id
    persona = principal.get("persona") or "human"
    try:
        return gated_kaggle_push(actor=persona if persona != "unset" else "human", credits=list(body.get("credits") or []))
    except Exception as exc:
        code = getattr(exc, "code", "kaggle_push_refused")
        raise HTTPException(status_code=403, detail=code) from exc


@router.post("/projects/{project_id}/kaggle/token")
async def kaggle_seal_token(
    project_id: str,
    body: dict[str, Any],
    request: Request,
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    org = _org(principal)
    require_owner(principal, action="seal kaggle token")
    token = str(body.get("token") or "")
    if not token:
        raise HTTPException(status_code=400, detail="token_required")
    sealed = seal_kaggle_token(token)
    blob = sealed.pop("_blob", None)
    mongo = _mongo(request)
    if mongo is not None and blob is not None:
        from mymlfw.saas.db import project_data

        proj = await project_data.get_project(mongo, org.id, project_id)
        if proj is None:
            raise HTTPException(status_code=404, detail="project_not_found")
        await project_data.store_project_kaggle_token(
            mongo, workspace_id=org.id, project_id=project_id, blob=blob
        )
    return sealed


@router.post("/projects/{project_id}/kaggle/diff")
async def kaggle_diff(
    project_id: str,
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    _org(principal)
    _ = project_id
    return submission_distribution_diff(
        [float(x) for x in body.get("left") or []],
        [float(x) for x in body.get("right") or []],
    )


@router.post("/projects/{project_id}/kaggle/package")
async def kaggle_package(
    project_id: str,
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    _org(principal)
    _ = project_id
    return package_submission(
        files=list(body.get("files") or []),
        final2=list(body.get("final2") or []),
    )


@router.post("/projects/{project_id}/kaggle/verify-notebook")
async def kaggle_verify_nb(
    project_id: str,
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    org = _org(principal)
    try:
        return verify_public_notebook(
            source=str(body.get("source") or ""),
            workspace_id=org.id,
            project_id=project_id,
            author=str(body.get("author") or "unknown"),
            dispatch=str(body.get("dispatch") or "sandbox"),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/projects/{project_id}/git/plan")
async def git_plan(
    project_id: str,
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    _org(principal)
    plan = git_sync_plan(
        installation_id=body.get("installation_id"),
        pat_fallback=bool(body.get("pat_fallback")),
    )
    plan["job"] = mission_complete_git_job(
        project_id=project_id, mission_id=str(body.get("mission_id") or "")
    )
    return plan


@router.post("/github/webhook")
async def github_webhook(request: Request) -> dict[str, Any]:
    body = await request.body()
    ok = verify_github_webhook(
        body=body,
        signature=request.headers.get("x-hub-signature-256", ""),
        secret=request.headers.get("x-webhook-secret", ""),
        delivery_id=request.headers.get("x-github-delivery", ""),
    )
    if not ok:
        raise HTTPException(status_code=401, detail="webhook_rejected")
    return {"ok": True}


@router.post("/elicitation/confirm")
async def elicitation_confirm(
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, str]:
    persona = principal.get("persona") or "human"
    if persona in {"agent", "viewer"}:
        raise HTTPException(status_code=403, detail="human_only")
    try:
        return confirm_elicitation(actor=persona if persona != "owner" else "owner", action=str(body.get("action") or "confirm"))
    except ElicitationError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from exc


@router.post("/projects/{project_id}/writeup")
async def project_writeup(
    project_id: str,
    body: dict[str, Any],
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, str]:
    _org(principal)
    _ = project_id
    text = render_writeup(
        title=str(body.get("title") or "Writeup"),
        summary=str(body.get("summary") or ""),
        credits=list(body.get("credits") or []),
    )
    return {"markdown": text}


@router.post("/auth/passkey/options")
async def passkey_options(
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    """WebAuthn registration options. Challenge is single-use random bytes."""
    require_owner(principal, action="passkey enroll")
    user = principal["user"]
    return {
        "challenge": secrets.token_urlsafe(32),
        "rp_id": "localhost",
        "user_id": user.id,
        "pub_key_cred_params": [{"type": "public-key", "alg": -7}],
    }
