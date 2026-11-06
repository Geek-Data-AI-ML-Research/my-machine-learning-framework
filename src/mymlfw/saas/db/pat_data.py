"""Mongo-backed MCP PATs — SHA-256 ``binData`` only (never plaintext at rest)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from mymlfw.saas.pats import StoredPat, hash_pat, mint_plaintext, new_token_id
from mymlfw.saas.schemas import PatCreateResponse, PatPrincipal

AGENT_PATS = "agent_pats"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _principal(doc: dict[str, Any]) -> PatPrincipal:
    return PatPrincipal(
        token_id=doc["_id"],
        workspace_id=doc["workspace_id"],
        project_id=doc.get("project_id"),
        scopes=list(doc.get("scopes") or []),
        label=str(doc.get("label") or ""),
    )


def _audit_row(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_id": doc["_id"],
        "token_prefix": doc.get("token_prefix") or "",
        "workspace_id": doc["workspace_id"],
        "project_id": doc.get("project_id"),
        "scopes": list(doc.get("scopes") or []),
        "label": str(doc.get("label") or ""),
        "created_at": doc.get("created_at"),
        "revoked_at": doc.get("revoked_at"),
    }


class PatExistsError(Exception):
    """Active PAT already exists; caller must pass ``replace=True``."""

    def __init__(self, *, active: list[dict[str, Any]]) -> None:
        self.active = active
        super().__init__("pat_exists")


async def list_active_pats(
    db: AsyncDatabase, *, workspace_id: str
) -> list[dict[str, Any]]:
    cursor = db[AGENT_PATS].find(
        {
            "workspace_id": workspace_id,
            "revoked_at": None,
            "deleted_at": None,
        }
    ).sort("created_at", -1)
    return [_audit_row(doc) async for doc in cursor]


async def revoke_active_pats(
    db: AsyncDatabase, *, workspace_id: str
) -> list[str]:
    """Revoke every active PAT in the workspace. Returns revoked token ids."""
    active = await list_active_pats(db, workspace_id=workspace_id)
    revoked: list[str] = []
    for row in active:
        token_id = str(row["token_id"])
        if await revoke_pat(db, workspace_id=workspace_id, token_id=token_id):
            revoked.append(token_id)
    return revoked


async def create_pat(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str | None = None,
    scopes: list[str] | None = None,
    label: str = "mcp-worker",
    replace: bool = False,
) -> PatCreateResponse:
    """Mint a PAT. At most one active PAT per workspace unless ``replace``."""
    active = await list_active_pats(db, workspace_id=workspace_id)
    replaced: list[str] = []
    if active:
        if not replace:
            raise PatExistsError(active=active)
        replaced = await revoke_active_pats(db, workspace_id=workspace_id)

    token_id = new_token_id()
    plaintext, prefix = mint_plaintext(token_id=token_id)
    digest = hash_pat(plaintext)
    scope_list = list(scopes or ["mcp:worker"])
    now = _utcnow()
    doc: dict[str, Any] = {
        "_id": token_id,
        "token_hash": digest,
        "token_prefix": prefix,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "scopes": scope_list,
        "label": label,
        "created_at": now,
        "revoked_at": None,
        "deleted_at": None,
    }
    await db[AGENT_PATS].insert_one(doc)
    return PatCreateResponse(
        token_id=token_id,
        token_prefix=prefix,
        token=plaintext,
        workspace_id=workspace_id,
        project_id=project_id,
        scopes=scope_list,
        replaced_token_ids=replaced,
    )


async def verify_pat(db: AsyncDatabase, token: str) -> PatPrincipal | None:
    if not token or not token.strip():
        return None
    digest = hash_pat(token.strip())
    doc = await db[AGENT_PATS].find_one(
        {
            "token_hash": digest,
            "revoked_at": None,
            "deleted_at": None,
        }
    )
    if doc is None:
        return None
    return _principal(doc)


async def list_pats(db: AsyncDatabase, *, workspace_id: str) -> list[dict[str, Any]]:
    cursor = db[AGENT_PATS].find(
        {
            "workspace_id": workspace_id,
            "deleted_at": None,
        }
    ).sort("created_at", -1)
    rows: list[dict[str, Any]] = []
    async for doc in cursor:
        rows.append(_audit_row(doc))
    return rows


async def revoke_pat(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    token_id: str,
) -> bool:
    now = _utcnow()
    result = await db[AGENT_PATS].update_one(
        {
            "_id": token_id,
            "workspace_id": workspace_id,
            "revoked_at": None,
            "deleted_at": None,
        },
        {"$set": {"revoked_at": now}},
    )
    return bool(result.modified_count)


def stored_from_doc(doc: dict[str, Any]) -> StoredPat:
    return StoredPat(
        token_id=doc["_id"],
        token_hash=doc["token_hash"],
        token_prefix=str(doc.get("token_prefix") or ""),
        workspace_id=doc["workspace_id"],
        project_id=doc.get("project_id"),
        scopes=tuple(doc.get("scopes") or ()),
        label=str(doc.get("label") or ""),
        created_at=doc["created_at"],
        revoked_at=doc.get("revoked_at"),
    )
