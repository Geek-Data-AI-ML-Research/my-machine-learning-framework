"""Idempotency-Key middleware: IN_PROGRESS / no-cache 5xx."""

from __future__ import annotations

import json
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

IDEMPOTENCY_HEADER = "Idempotency-Key"
_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class InMemoryIdempotencyStore:
    """Process-local store; Redis-backed store swaps in behind the same API."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        return self._entries.get(key)

    def set_in_progress(self, key: str) -> bool:
        """Return True if this caller owns the key; False if already present."""
        if key in self._entries:
            return False
        self._entries[key] = {"status": "IN_PROGRESS", "started_at": time.time()}
        return True

    def set_result(
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

    def clear(self, key: str) -> None:
        self._entries.pop(key, None)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, store: InMemoryIdempotencyStore | None = None) -> None:
        super().__init__(app)
        self.store = store or InMemoryIdempotencyStore()

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.method not in _MUTATING:
            return await call_next(request)

        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not key:
            return await call_next(request)

        scope_key = f"{request.method}:{request.url.path}:{key}"
        existing = self.store.get(scope_key)
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

        if not self.store.set_in_progress(scope_key):
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
            self.store.set_result(
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
            self.store.clear(scope_key)
            raise


def replay_body_json(store: InMemoryIdempotencyStore, scope_key: str) -> Any:
    entry = store.get(scope_key)
    if not entry or entry.get("status") != "DONE":
        return None
    return json.loads(entry["body"])
