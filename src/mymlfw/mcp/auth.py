"""PAT verification for MCP (hashed lookup via saas.pats — no Mongo here)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from mymlfw.saas.pats import PAT_STORE, PatStore
from mymlfw.saas.schemas import PatPrincipal


@dataclass(frozen=True)
class McpAuthContext:
    principal: PatPrincipal
    lease_owner: str


def bearer_from_headers(headers: dict[str, str] | None) -> str | None:
    if not headers:
        return None
    for key, value in headers.items():
        if key.lower() == "authorization" and value.lower().startswith("bearer "):
            return value.split(" ", 1)[1].strip()
    return None


def idempotency_key_from(
    headers: dict[str, str] | None,
    explicit: str | None = None,
) -> str | None:
    """Prefer tool arg, then ``Idempotency-Key`` header (never query string)."""
    if explicit and explicit.strip():
        return explicit.strip()
    if not headers:
        return None
    for key, value in headers.items():
        if key.lower() == "idempotency-key" and value.strip():
            return value.strip()
    return None


def resolve_pat(
    token: str | None,
    *,
    store: PatStore | None = None,
) -> PatPrincipal | None:
    if not token:
        return None
    return (store or PAT_STORE).verify(token)


async def aresolve_pat(
    token: str | None,
    *,
    store: PatStore | None = None,
) -> PatPrincipal | None:
    if not token:
        return None
    store = store or PAT_STORE
    if hasattr(store, "averify"):
        return await store.averify(token)
    return store.verify(token)


def resolve_auth_context(
    *,
    headers: dict[str, str] | None = None,
    explicit_token: str | None = None,
    store: PatStore | None = None,
    env_token: str | None = None,
) -> McpAuthContext:
    """Resolve PAT from tool arg, Authorization header, or ``MYMLFW_MCP_PAT``.

    Prefer header / env over tool ``pat`` so secrets are not logged in stdio
    tool argument traces. Never accept PAT via query string.
    """
    token = (
        bearer_from_headers(headers)
        or env_token
        or os.environ.get("MYMLFW_MCP_PAT")
        or explicit_token
    )
    principal = resolve_pat(token, store=store)
    if principal is None:
        raise PermissionError("invalid_or_missing_pat")
    lease_owner = f"pat:{principal.token_id}"
    return McpAuthContext(principal=principal, lease_owner=lease_owner)


async def aresolve_auth_context(
    *,
    headers: dict[str, str] | None = None,
    explicit_token: str | None = None,
    store: PatStore | None = None,
    env_token: str | None = None,
) -> McpAuthContext:
    """Async resolve — uses Mongo ``agent_pats`` when the store is mongo-backed."""
    token = (
        bearer_from_headers(headers)
        or env_token
        or os.environ.get("MYMLFW_MCP_PAT")
        or explicit_token
    )
    principal = await aresolve_pat(token, store=store)
    if principal is None:
        raise PermissionError("invalid_or_missing_pat")
    lease_owner = f"pat:{principal.token_id}"
    return McpAuthContext(principal=principal, lease_owner=lease_owner)


def principal_has_scope(principal: PatPrincipal, *needed: str) -> bool:
    scopes = set(principal.scopes or ())
    if "mcp:admin" in scopes:
        return True
    return bool(scopes.intersection(needed))


def require_scopes(auth: McpAuthContext, *needed: str) -> None:
    if not principal_has_scope(auth.principal, *needed):
        raise PermissionError("insufficient_scope")


def auth_error_payload(exc: BaseException) -> dict[str, Any] | None:
    """Map auth PermissionError codes to MCP error envelopes."""
    code = str(exc) if isinstance(exc, PermissionError) else ""
    if code == "invalid_or_missing_pat":
        return {
            "error_code": "invalid_or_missing_pat",
            "message": "Provide Authorization: Bearer <pat> or MYMLFW_MCP_PAT",
            "suggested_fix": "Mint a PAT and set MYMLFW_MCP_PAT (prefer env over tool arg)",
        }
    if code == "pat_project_mismatch":
        return {
            "error_code": "pat_project_mismatch",
            "message": "PAT is pinned to a different project_id",
            "suggested_fix": "Use a workspace PAT or the pinned project_id",
        }
    if code == "insufficient_scope":
        return {
            "error_code": "insufficient_scope",
            "message": "PAT scopes do not allow this tool",
            "suggested_fix": "Mint a PAT with mcp:worker and/or mcp:cloud",
        }
    return None
