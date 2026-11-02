"""FastAPI dependencies (get_project_db stub for Wave 1)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request

from mymlfw.api.auth import AUTH_STORE
from mymlfw.saas.db.project_db import ProjectScopedDB


async def get_current_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    token = authorization.split(" ", 1)[1].strip()
    principal = AUTH_STORE.resolve(token)
    if not principal:
        raise HTTPException(status_code=401, detail="invalid_token")
    return principal


async def get_project_db(
    request: Request,
    project_id: str,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectScopedDB:
    """Wave 1 stub: requires auth + org; real membership checks land with Mongo projects."""
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    mongo = getattr(request.app.state, "mongo_db", None)
    if mongo is None:
        raise HTTPException(status_code=503, detail="mongo_unavailable")
    return ProjectScopedDB(
        mongo, workspace_id=org.id, project_id=project_id
    )
