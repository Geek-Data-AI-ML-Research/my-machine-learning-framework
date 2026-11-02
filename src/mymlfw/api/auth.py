"""GitHub OAuth stub + local email/password for Compose."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from passlib.hash import argon2
from ulid import ULID

from mymlfw.saas.schemas import (
    FeatureFlags,
    OrgEntitlements,
    OrgResponse,
    TokenResponse,
    UserResponse,
)


def new_user_id() -> str:
    return f"usr_{ULID()}"


def new_org_id() -> str:
    return f"org_{ULID()}"


def hash_password(password: str) -> str:
    return argon2.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return argon2.verify(password, password_hash)


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


class DevAuthStore:
    """In-memory users/orgs for Wave 1 Compose without requiring Mongo for auth tests."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.by_email: dict[str, str] = {}
        self.orgs: dict[str, dict[str, Any]] = {}
        self.memberships: dict[str, str] = {}  # user_id -> org_id
        self.sessions: dict[str, str] = {}  # token -> user_id
        self.personas: dict[str, str] = {}  # user_id -> persona

    def register(self, email: str, password: str, display_name: str) -> TokenResponse:
        email = email.lower()
        if email in self.by_email:
            raise ValueError("email_taken")
        user_id = new_user_id()
        org_id = new_org_id()
        self.users[user_id] = {
            "id": user_id,
            "email": email,
            "display_name": display_name,
            "password_hash": hash_password(password),
        }
        self.by_email[email] = user_id
        self.orgs[org_id] = {
            "id": org_id,
            "slug": f"org-{org_id[-6:].lower()}",
            "name": f"{display_name}'s org",
            "plan": "dev",
            "entitlements": OrgEntitlements().model_dump(),
            "feature_flags": FeatureFlags().model_dump(),
        }
        self.memberships[user_id] = org_id
        token = f"tok_{ULID()}"
        self.sessions[token] = user_id
        return TokenResponse(access_token=token, user_id=user_id, org_id=org_id)

    def login(self, email: str, password: str) -> TokenResponse:
        email = email.lower()
        user_id = self.by_email.get(email)
        if not user_id:
            raise ValueError("invalid_credentials")
        user = self.users[user_id]
        if not verify_password(password, user["password_hash"]):
            raise ValueError("invalid_credentials")
        token = f"tok_{ULID()}"
        self.sessions[token] = user_id
        return TokenResponse(
            access_token=token,
            user_id=user_id,
            org_id=self.memberships.get(user_id),
        )

    def github_oauth_stub(self, code: str) -> TokenResponse:
        """Stub: exchange code for a deterministic dev user."""
        email = f"gh_{code[:12] or 'dev'}@users.noreply.github.com"
        password = "gh-oauth-stub"
        if email not in self.by_email:
            return self.register(email, password, "GitHub Dev")
        return self.login(email, password)

    def resolve(self, token: str) -> dict[str, Any] | None:
        user_id = self.sessions.get(token)
        if not user_id:
            return None
        user = self.users[user_id]
        org_id = self.memberships.get(user_id)
        org = self.orgs.get(org_id) if org_id else None
        return {
            "user": UserResponse(
                id=user["id"], email=user["email"], display_name=user["display_name"]
            ),
            "org": OrgResponse(**org) if org else None,
            "persona": self.personas.get(user_id),
        }

    def set_persona(self, user_id: str, persona: str) -> None:
        self.personas[user_id] = persona


def sign_dev_cookie(secret: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


AUTH_STORE = DevAuthStore()


def seed_dev_personas(store: DevAuthStore | None = None) -> None:
    """Seed owner/member/viewer personas for the DEV switcher."""
    store = store or AUTH_STORE
    for persona, email in (
        ("owner", "owner@localhost"),
        ("member", "member@localhost"),
        ("viewer", "viewer@localhost"),
    ):
        if email in store.by_email:
            continue
        try:
            tok = store.register(email, "devpassword", persona.title())
            store.set_persona(tok.user_id, persona)
        except ValueError:
            pass
    _ = time.time  # keep import used for future session TTL
