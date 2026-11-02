"""Project / workspace PATs — SHA-256 hashed at rest (binData), prefix shown once."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ulid import ULID

from mymlfw.saas.schemas import PatCreateResponse, PatPrincipal


def hash_pat(token: str) -> bytes:
    """Canonical at-rest form: SHA-256 digest as bytes (never store plaintext)."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def new_token_id() -> str:
    return f"tok_{ULID()}"


def _mint_plaintext(*, token_id: str) -> tuple[str, str]:
    """Return ``(plaintext, prefix)``. Prefix is safe to display in tables."""
    secret = secrets.token_urlsafe(24)
    # Prefix omits the secret; full token is shown once on create.
    prefix = f"mlp_{token_id.removeprefix('tok_')[:10]}"
    plaintext = f"{prefix}.{secret}"
    return plaintext, prefix


@dataclass(frozen=True)
class StoredPat:
    token_id: str
    token_hash: bytes
    token_prefix: str
    workspace_id: str
    project_id: str | None
    scopes: tuple[str, ...]
    label: str
    created_at: datetime
    revoked_at: datetime | None = None


class PatStore:
    """In-memory PAT registry for B2; Mongo ``agent_connections`` lands with E2."""

    def __init__(self) -> None:
        self._by_hash: dict[bytes, StoredPat] = {}
        self._by_id: dict[str, StoredPat] = {}

    def create(
        self,
        *,
        workspace_id: str,
        project_id: str | None = None,
        scopes: list[str] | None = None,
        label: str = "mcp-worker",
    ) -> PatCreateResponse:
        token_id = new_token_id()
        plaintext, prefix = _mint_plaintext(token_id=token_id)
        digest = hash_pat(plaintext)
        now = datetime.now(UTC)
        scope_tuple = tuple(scopes or ["mcp:worker"])
        stored = StoredPat(
            token_id=token_id,
            token_hash=digest,
            token_prefix=prefix,
            workspace_id=workspace_id,
            project_id=project_id,
            scopes=scope_tuple,
            label=label,
            created_at=now,
        )
        self._by_hash[digest] = stored
        self._by_id[token_id] = stored
        return PatCreateResponse(
            token_id=token_id,
            token_prefix=prefix,
            token=plaintext,
            workspace_id=workspace_id,
            project_id=project_id,
            scopes=list(scope_tuple),
        )

    def verify(self, token: str) -> PatPrincipal | None:
        if not token:
            return None
        digest = hash_pat(token.strip())
        stored = self._by_hash.get(digest)
        if stored is None or stored.revoked_at is not None:
            return None
        return PatPrincipal(
            token_id=stored.token_id,
            workspace_id=stored.workspace_id,
            project_id=stored.project_id,
            scopes=list(stored.scopes),
            label=stored.label,
        )

    def revoke(self, token_id: str) -> bool:
        stored = self._by_id.get(token_id)
        if stored is None or stored.revoked_at is not None:
            return False
        revoked = StoredPat(
            token_id=stored.token_id,
            token_hash=stored.token_hash,
            token_prefix=stored.token_prefix,
            workspace_id=stored.workspace_id,
            project_id=stored.project_id,
            scopes=stored.scopes,
            label=stored.label,
            created_at=stored.created_at,
            revoked_at=datetime.now(UTC),
        )
        self._by_id[token_id] = revoked
        self._by_hash[stored.token_hash] = revoked
        return True

    def export_audit_row(self, token_id: str) -> dict[str, Any] | None:
        """Safe row for ops tables — never includes the raw token."""
        stored = self._by_id.get(token_id)
        if stored is None:
            return None
        return {
            "token_id": stored.token_id,
            "token_prefix": stored.token_prefix,
            "workspace_id": stored.workspace_id,
            "project_id": stored.project_id,
            "scopes": list(stored.scopes),
            "label": stored.label,
            "created_at": stored.created_at,
            "revoked_at": stored.revoked_at,
            "token_hash_len": len(stored.token_hash),
        }


PAT_STORE = PatStore()
