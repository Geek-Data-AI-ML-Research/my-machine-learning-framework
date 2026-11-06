"""FastAPI dependencies (auth + optional ProjectScopedDB)."""

from __future__ import annotations

from typing import Annotated, Any, Iterable

from fastapi import Depends, Header, HTTPException, Request

from mymlfw.api.auth import AUTH_STORE
from mymlfw.saas.brain_store import BRAIN_STORE
from mymlfw.saas.control_plane import sync_org_policy_from_principal
from mymlfw.saas.db.project_db import ProjectScopedDB

# Personas that may mutate org policy / seal secrets / spend cloud budget.
_OWNER_ROLES = frozenset({"owner"})
_OPERATOR_ROLES = frozenset({"owner", "member", "editor"})
_BLOCKED_BILLABLE = frozenset({"viewer", "agent", "pat"})


def require_org_role(
    principal: dict[str, Any],
    *,
    allowed: Iterable[str],
    action: str,
) -> None:
    """Enforce persona RBAC. ``None`` persona = API-key/test path (allowed)."""
    persona = principal.get("persona")
    if persona is None:
        return
    allowed_set = frozenset(allowed)
    if persona in allowed_set:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "error_code": "forbidden_role",
            "message": f"{action} requires one of: {sorted(allowed_set)}",
            "persona": persona,
        },
    )


def require_owner(principal: dict[str, Any], *, action: str) -> None:
    require_org_role(principal, allowed=_OWNER_ROLES, action=action)


def require_cloud_operator(principal: dict[str, Any], *, action: str) -> None:
    """Owner/member may launch; viewer/agent cannot spend."""
    persona = principal.get("persona")
    if persona in _BLOCKED_BILLABLE:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "forbidden_role",
                "message": f"{action} requires owner or member persona",
                "persona": persona,
            },
        )
    if persona is not None and persona not in _OPERATOR_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "forbidden_role",
                "message": f"{action} requires owner or member persona",
                "persona": persona,
            },
        )


async def get_current_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    token = authorization.split(" ", 1)[1].strip()
    mongo = getattr(request.app.state, "mongo_db", None)
    if mongo is not None:
        from mymlfw.saas.db import auth_data

        principal = await auth_data.resolve_session(mongo, token)
    else:
        # Unit-test / no-Mongo path only — Compose always binds Mongo.
        principal = AUTH_STORE.resolve(token)
    if not principal:
        raise HTTPException(status_code=401, detail="invalid_token")
    sync_org_policy_from_principal(principal)
    return principal


async def require_project_in_org(
    request: Request,
    principal: dict[str, Any],
    project_id: str,
) -> Any:
    """Membership / existence gate for ``/v1/projects/{project_id}/*`` routes.

    When Mongo is up, project rows live in Mongo (not BRAIN_STORE).
    """
    org = principal.get("org")
    if org is None:
        raise HTTPException(status_code=403, detail="no_org")
    mongo = getattr(request.app.state, "mongo_db", None)
    if mongo is not None:
        from mymlfw.saas.db import project_data

        proj = await project_data.get_project(mongo, org.id, project_id)
        if proj is None:
            raise HTTPException(status_code=404, detail="project_not_found")
        return org

    proj = BRAIN_STORE.get_project(org.id, project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    return org


async def get_project_db(
    request: Request,
    project_id: str,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectScopedDB:
    """Requires auth + project membership; returns scoped DB when Mongo is up."""
    org = await require_project_in_org(request, principal, project_id)
    mongo = getattr(request.app.state, "mongo_db", None)
    if mongo is None:
        raise HTTPException(status_code=503, detail="mongo_unavailable")
    return ProjectScopedDB(
        mongo, workspace_id=org.id, project_id=project_id
    )


async def get_optional_project_db(
    request: Request,
    project_id: str,
    principal: Annotated[dict[str, Any], Depends(get_current_principal)],
) -> ProjectScopedDB | None:
    """Like ``get_project_db`` but returns None when Mongo is offline (dev/tests)."""
    org = await require_project_in_org(request, principal, project_id)
    mongo = getattr(request.app.state, "mongo_db", None)
    if mongo is None:
        return None
    return ProjectScopedDB(mongo, workspace_id=org.id, project_id=project_id)
