"""MCP OAuth 2.1 PKCE S256 helpers (flag mcp_oauth)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any


def pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def issue_access_token(
    *,
    secret: str,
    workspace_id: str,
    project_id: str | None,
    aud: str = "mymlfw-mcp",
) -> str:
    body = {"aud": aud, "workspace_id": workspace_id, "project_id": project_id}
    raw = json.dumps(body, sort_keys=True).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    payload = base64.urlsafe_b64encode(raw).decode()
    return f"{payload}.{sig}"


def verify_access_token(token: str, *, secret: str, aud: str = "mymlfw-mcp") -> dict[str, Any]:
    payload, sig = token.split(".", 1)
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    expect = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        raise ValueError("bad_sig")
    body = json.loads(raw)
    if body.get("aud") != aud:
        raise ValueError("bad_aud")
    return body
