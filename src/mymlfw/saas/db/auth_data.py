"""Mongo-backed auth: ``users``, ``orgs``, ``auth_sessions``.

Session tokens are stored as SHA-256 ``binData`` only (never plaintext).
Password hashes stay as Argon2 PHC strings (not reversible tokens).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase
from ulid import ULID

from mymlfw.api.auth import (
    hash_password,
    hash_token,
    new_org_id,
    new_user_id,
    verify_password,
)
from mymlfw.saas.schemas import (
    FeatureFlags,
    OrgEntitlements,
    OrgResponse,
    TokenResponse,
    UserResponse,
)

USERS = "users"
ORGS = "orgs"
SESSIONS = "auth_sessions"

_SESSION_TTL = timedelta(days=30)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _org_response(doc: dict[str, Any]) -> OrgResponse:
    return OrgResponse(
        id=doc["_id"],
        slug=doc["slug"],
        name=doc["name"],
        plan=str(doc.get("plan") or "dev"),
        entitlements=OrgEntitlements(**(doc.get("entitlements") or {})),
        feature_flags=FeatureFlags(**(doc.get("feature_flags") or {})),
    )


def _user_response(doc: dict[str, Any]) -> UserResponse:
    return UserResponse(
        id=doc["_id"],
        email=doc["email"],
        display_name=doc["display_name"],
    )


async def get_user_by_email(db: AsyncDatabase, email: str) -> dict[str, Any] | None:
    return await db[USERS].find_one(
        {"email": email.lower().strip(), "deleted_at": None}
    )


async def get_user_by_id(db: AsyncDatabase, user_id: str) -> dict[str, Any] | None:
    return await db[USERS].find_one({"_id": user_id, "deleted_at": None})


async def get_org(db: AsyncDatabase, org_id: str) -> dict[str, Any] | None:
    return await db[ORGS].find_one({"_id": org_id, "deleted_at": None})


async def register_user(
    db: AsyncDatabase,
    *,
    email: str,
    password: str,
    display_name: str,
    persona: str | None = None,
) -> TokenResponse:
    email_n = email.lower().strip()
    existing = await get_user_by_email(db, email_n)
    if existing is not None:
        raise ValueError("email_taken")

    now = _utcnow()
    user_id = new_user_id()
    org_id = new_org_id()
    user_doc = {
        "_id": user_id,
        "email": email_n,
        "display_name": display_name.strip() or "dev",
        "password_hash": hash_password(password),
        "org_id": org_id,
        "persona": persona,
        "schema_version": 1,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    org_doc = {
        "_id": org_id,
        "slug": f"org-{org_id[-6:].lower()}",
        "name": f"{display_name}'s org",
        "plan": "dev",
        "owner_user_id": user_id,
        "entitlements": OrgEntitlements().model_dump(),
        "feature_flags": FeatureFlags().model_dump(),
        "schema_version": 1,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    await db[ORGS].insert_one(org_doc)
    await db[USERS].insert_one(user_doc)
    token = await create_session(db, user_id=user_id)
    return TokenResponse(access_token=token, user_id=user_id, org_id=org_id)


async def login_user(db: AsyncDatabase, *, email: str, password: str) -> TokenResponse:
    user = await get_user_by_email(db, email)
    if user is None:
        raise ValueError("invalid_credentials")
    if not verify_password(password, user["password_hash"]):
        raise ValueError("invalid_credentials")
    token = await create_session(db, user_id=user["_id"])
    return TokenResponse(
        access_token=token,
        user_id=user["_id"],
        org_id=user.get("org_id"),
    )


async def create_session(db: AsyncDatabase, *, user_id: str) -> str:
    now = _utcnow()
    token = f"tok_{ULID()}"
    doc = {
        "_id": f"ses_{ULID()}",
        "user_id": user_id,
        "token_hash": hash_token(token),
        "created_at": now,
        "expires_at": now + _SESSION_TTL,
        "revoked_at": None,
        "schema_version": 1,
    }
    await db[SESSIONS].insert_one(doc)
    return token


async def resolve_session(db: AsyncDatabase, token: str) -> dict[str, Any] | None:
    digest = hash_token(token)
    now = _utcnow()
    session = await db[SESSIONS].find_one(
        {
            "token_hash": digest,
            "revoked_at": None,
            "expires_at": {"$gt": now},
        }
    )
    if session is None:
        return None
    user = await get_user_by_id(db, session["user_id"])
    if user is None:
        return None
    org = None
    org_id = user.get("org_id")
    if org_id:
        org_doc = await get_org(db, org_id)
        if org_doc is not None:
            org = _org_response(org_doc)
    return {
        "user": _user_response(user),
        "org": org,
        "persona": user.get("persona"),
    }


async def set_user_persona(db: AsyncDatabase, user_id: str, persona: str) -> None:
    await db[USERS].update_one(
        {"_id": user_id, "deleted_at": None},
        {"$set": {"persona": persona, "updated_at": _utcnow()}},
    )


async def update_org_feature_flags(
    db: AsyncDatabase, org_id: str, updates: dict[str, Any]
) -> dict[str, Any]:
    org = await get_org(db, org_id)
    if org is None:
        raise ValueError("org_not_found")
    flags = dict(org.get("feature_flags") or {})
    for key, value in updates.items():
        if value is not None:
            flags[key] = bool(value)
    await db[ORGS].update_one(
        {"_id": org_id, "deleted_at": None},
        {"$set": {"feature_flags": flags, "updated_at": _utcnow()}},
    )
    org["feature_flags"] = flags
    return org


async def ensure_dev_persona(
    db: AsyncDatabase,
    *,
    persona: str,
    email: str,
    password: str = "devpassword",
) -> TokenResponse | None:
    """Idempotent seed: create user+org if missing; return None if already present."""
    existing = await get_user_by_email(db, email)
    if existing is not None:
        if existing.get("persona") != persona:
            await set_user_persona(db, existing["_id"], persona)
        return None
    return await register_user(
        db,
        email=email,
        password=password,
        display_name=persona.title(),
        persona=persona,
    )


async def github_register_or_login(
    db: AsyncDatabase,
    *,
    email: str,
    display_name: str,
    password: str,
) -> TokenResponse:
    existing = await get_user_by_email(db, email)
    if existing is None:
        return await register_user(
            db, email=email, password=password, display_name=display_name
        )
    return await login_user(db, email=email, password=password)
