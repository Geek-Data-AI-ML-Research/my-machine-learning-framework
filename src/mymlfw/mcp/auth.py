"""PAT verification for MCP (hashed lookup via saas.pats — no Mongo here)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from mymlfw.saas.pats import PAT_STORE, PatStore
from mymlfw.saas.schemas import PatPrincipal


@dataclass(frozen=True)
class McpAuthContext:
    principal: PatPrincipal
    lease_owner: str


def bearer_from_headers(headers: dict[str, str] | None) -> str | None:
    if not headers:
        return None
    # Header maps may be case-insensitive; normalize.
    for key, value in headers.items():
        if key.lower() == "authorization" and value.lower().startswith("bearer "):
            return value.split(" ", 1)[1].strip()
    return None


def resolve_pat(
    token: str | None,
    *,
    store: PatStore | None = None,
) -> PatPrincipal | None:
    if not token:
        return None
    return (store or PAT_STORE).verify(token)


def resolve_auth_context(
    *,
    headers: dict[str, str] | None = None,
    explicit_token: str | None = None,
    store: PatStore | None = None,
    env_token: str | None = None,
) -> McpAuthContext:
    """Resolve PAT from tool arg, Authorization header, or ``MYMLFW_MCP_PAT``."""
    token = (
        explicit_token
        or bearer_from_headers(headers)
        or env_token
        or os.environ.get("MYMLFW_MCP_PAT")
    )
    principal = resolve_pat(token, store=store)
    if principal is None:
        raise PermissionError("invalid_or_missing_pat")
    lease_owner = f"pat:{principal.token_id}"
    return McpAuthContext(principal=principal, lease_owner=lease_owner)
