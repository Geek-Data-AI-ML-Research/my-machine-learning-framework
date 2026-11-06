"""Idempotency-Key middleware: IN_PROGRESS / no-cache 5xx; Redis when bound."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mymlfw.saas.redis_control import IDEMPOTENCY_PREFIX, get_redis

IDEMPOTENCY_HEADER = "Idempotency-Key"
_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# SaaS mutators must send Idempotency-Key (AGENTS.md). Auth + high-frequency
# runner heartbeats are exempt.
_REQUIRE_PREFIXES = ("/v1/orgs/", "/v1/projects/")
_EXEMPT_PREFIXES = ("/v1/auth/", "/v1/runners/")
_DEFAULT_TTL_S = 24 * 3600


def _requires_idempotency_key(method: str, path: str) -> bool:
    if method not in _MUTATING:
        return False
    if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
        return False
    if path == "/v1/projects" or path.startswith("/v1/projects/"):
        return True
    return any(path.startswith(p) for p in _REQUIRE_PREFIXES)


class IdempotencyStore(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def set_in_progress(self, key: str) -> bool: ...

    async def set_result(
        self,
        key: str,
        *,
        status_code: int,
        body: bytes,
        headers: dict[str, str],
    ) -> None: ...

    async def clear(self, key: str) -> None: ...


class InMemoryIdempotencyStore:
    """Process-local store; used when Redis is unset / unavailable."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        return self._entries.get(key)

    async def set_in_progress(self, key: str) -> bool:
        """Return True if this caller owns the key; False if already present."""
        if key in self._entries:
            return False
        self._entries[key] = {"status": "IN_PROGRESS", "started_at": time.time()}
        return True

    async def set_result(
        self,
        key: str,
        *,
        status_code: int,
        body: bytes,
        headers: dict[str, str],
    ) -> None:
        # Do not cache 5xx / 429 (anti-drift).
        if status_code >= 500 or status_code == 429:
            self._entries.pop(key, None)
            return
        self._entries[key] = {
            "status": "DONE",
            "status_code": status_code,
            "body": body,
            "headers": headers,
        }

    async def clear(self, key: str) -> None:
        self._entries.pop(key, None)


class RedisIdempotencyStore:
    """Redis-backed Idempotency-Key results (IN_PROGRESS / DONE replay)."""

    def __init__(self, redis: Any, *, ttl_s: int = _DEFAULT_TTL_S) -> None:
        self._r = redis
        self._ttl = ttl_s

    def _rk(self, key: str) -> str:
        return f"{IDEMPOTENCY_PREFIX}{key}"

    async def get(self, key: str) -> dict[str, Any] | None:
        raw = await self._r.get(self._rk(key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        obj = json.loads(raw)
        if isinstance(obj.get("body"), str):
            # Stored as latin-1 round-trip for arbitrary bytes.
            obj["body"] = obj["body"].encode("latin-1")
        return obj

    async def set_in_progress(self, key: str) -> bool:
        payload = json.dumps(
            {"status": "IN_PROGRESS", "started_at": time.time()}
        )
        # SET NX — only the first caller owns the key.
        ok = await self._r.set(
            self._rk(key), payload, nx=True, ex=self._ttl
        )
        return bool(ok)

    async def set_result(
        self,
        key: str,
        *,
        status_code: int,
        body: bytes,
        headers: dict[str, str],
    ) -> None:
        if status_code >= 500 or status_code == 429:
            await self.clear(key)
            return
        payload = json.dumps(
            {
                "status": "DONE",
                "status_code": status_code,
                "body": body.decode("latin-1"),
                "headers": headers,
            }
        )
        await self._r.set(self._rk(key), payload, ex=self._ttl)

    async def clear(self, key: str) -> None:
        await self._r.delete(self._rk(key))


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, store: IdempotencyStore | None = None) -> None:
        super().__init__(app)
        self.store = store
        self._fallback = InMemoryIdempotencyStore()

    def _resolve_store(self, request: Request) -> IdempotencyStore:
        if self.store is not None:
            return self.store
        bound = getattr(request.app.state, "idempotency_store", None)
        if bound is not None:
            return bound
        # Live Redis attached after lifespan without swapping middleware store.
        redis = getattr(request.app.state, "redis", None) or get_redis()
        if redis is not None:
            return RedisIdempotencyStore(redis)
        return self._fallback

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.method not in _MUTATING:
            return await call_next(request)

        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not key:
            if _requires_idempotency_key(request.method, request.url.path):
                return JSONResponse(
                    {
                        "error_code": "idempotency_key_required",
                        "message": "Mutating SaaS routes require Idempotency-Key",
                        "suggested_fix": "Send a unique Idempotency-Key header (UUID)",
                    },
                    status_code=400,
                    headers={"Cache-Control": "no-store"},
                )
            return await call_next(request)

        store = self._resolve_store(request)
        scope_key = f"{request.method}:{request.url.path}:{key}"
        existing = await store.get(scope_key)
        if existing is not None:
            if existing.get("status") == "IN_PROGRESS":
                return JSONResponse(
                    {
                        "error_code": "idempotency_in_progress",
                        "message": "Request with this Idempotency-Key is still in progress",
                        "suggested_fix": "Retry the same Idempotency-Key after a short delay",
                    },
                    status_code=409,
                    headers={"Cache-Control": "no-store"},
                )
            return Response(
                content=existing["body"],
                status_code=int(existing["status_code"]),
                headers={
                    **existing.get("headers", {}),
                    "Cache-Control": "no-store",
                    "X-Idempotency-Replayed": "true",
                },
                media_type="application/json",
            )

        if not await store.set_in_progress(scope_key):
            return JSONResponse(
                {
                    "error_code": "idempotency_in_progress",
                    "message": "Request with this Idempotency-Key is still in progress",
                    "suggested_fix": "Retry the same Idempotency-Key after a short delay",
                },
                status_code=409,
                headers={"Cache-Control": "no-store"},
            )

        try:
            response = await call_next(request)
            body = b""
            async for chunk in response.body_iterator:
                body += chunk if isinstance(chunk, bytes) else chunk.encode()
            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in {"content-length", "content-encoding"}
            }
            await store.set_result(
                scope_key,
                status_code=response.status_code,
                body=body,
                headers=headers,
            )
            if response.status_code >= 500 or response.status_code == 429:
                headers = {**headers, "Cache-Control": "no-store"}
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )
        except Exception:
            await store.clear(scope_key)
            raise


async def replay_body_json(store: IdempotencyStore, scope_key: str) -> Any:
    entry = await store.get(scope_key)
    if not entry or entry.get("status") != "DONE":
        return None
    body = entry["body"]
    if isinstance(body, bytes):
        return json.loads(body)
    return json.loads(body)
