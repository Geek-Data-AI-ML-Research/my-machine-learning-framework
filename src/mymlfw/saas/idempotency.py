"""Service-level Idempotency-Key helper (mutations: MCP + future CLI)."""

from __future__ import annotations

import json
import time
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class IdempotencyConflict(Exception):
    error_code = "idempotency_in_progress"


class IdempotencyStore:
    """Process-local store; Redis swap keeps the same method names."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        return self._entries.get(key)

    def begin(self, key: str) -> bool:
        if key in self._entries:
            return False
        self._entries[key] = {"status": "IN_PROGRESS", "started_at": time.time()}
        return True

    def complete(self, key: str, payload: Any) -> None:
        self._entries[key] = {
            "status": "DONE",
            "payload": payload,
            "body": json.dumps(payload, default=str),
        }

    def clear(self, key: str) -> None:
        self._entries.pop(key, None)


async def run_idempotent(
    store: IdempotencyStore,
    *,
    scope: str,
    key: str | None,
    fn: Callable[[], Awaitable[T]],
) -> tuple[T, bool]:
    """Return ``(result, replayed)``. Missing key → execute once, not replayed."""
    if not key:
        return await fn(), False

    scope_key = f"{scope}:{key}"
    existing = store.get(scope_key)
    if existing is not None:
        if existing.get("status") == "IN_PROGRESS":
            raise IdempotencyConflict("Idempotency-Key still in progress")
        return existing["payload"], True

    if not store.begin(scope_key):
        raise IdempotencyConflict("Idempotency-Key still in progress")
    try:
        result = await fn()
        store.complete(scope_key, result)
        return result, False
    except Exception:
        store.clear(scope_key)
        raise
