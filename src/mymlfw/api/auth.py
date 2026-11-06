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
        """Dev-only: exchange code for a deterministic local user."""
        email = f"gh_{code[:12] or 'dev'}@users.noreply.github.com"
        password = "gh-oauth-stub"
        if email not in self.by_email:
            return self.register(email, password, "GitHub Dev")
        return self.login(email, password)

    def github_oauth_live(
        self,
        *,
        code: str,
        client_id: str,
        client_secret: str,
    ) -> TokenResponse:
        """Exchange GitHub OAuth code for a real user (billable identity path)."""
        import json
        import urllib.error
        import urllib.parse
        import urllib.request

        token_body = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
            }
        ).encode("utf-8")
        token_req = urllib.request.Request(
            "https://github.com/login/oauth/access_token",
            data=token_body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(token_req, timeout=20) as resp:  # noqa: S310
                token_payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ValueError("github_token_exchange_failed") from exc
        access = token_payload.get("access_token")
        if not access:
            raise ValueError("github_token_missing")
        user_req = urllib.request.Request(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "mymlfw-saas",
            },
        )
        try:
            with urllib.request.urlopen(user_req, timeout=20) as resp:  # noqa: S310
                profile = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ValueError("github_user_fetch_failed") from exc
        login = str(profile.get("login") or "github")
        email = str(profile.get("email") or f"{login}@users.noreply.github.com").lower()
        display = str(profile.get("name") or login)
        if email not in self.by_email:
            # Opaque local password — GitHub users re-auth via OAuth only.
            import secrets

            return self.register(email, secrets.token_urlsafe(32), display)
        user_id = self.by_email[email]
        token = f"tok_{ULID()}"
        self.sessions[token] = user_id
        return TokenResponse(
            access_token=token,
            user_id=user_id,
            org_id=self.memberships.get(user_id),
        )

    def update_feature_flags(self, org_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        org = self.orgs.get(org_id)
        if org is None:
            raise ValueError("org_not_found")
        flags = dict(org.get("feature_flags") or {})
        for key, value in updates.items():
            if value is not None:
                flags[key] = bool(value)
        org["feature_flags"] = flags
        return org

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
