"""Process-local audit + webhook hooks for Project Brain advise egress."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

_AUDIT: list[dict[str, Any]] = []
_WEBHOOK_SINKS: list[Callable[[dict[str, Any]], None]] = []


def reset_brain_audit_for_tests() -> None:
    _AUDIT.clear()
    _WEBHOOK_SINKS.clear()


def register_webhook_sink(fn: Callable[[dict[str, Any]], None]) -> None:
    _WEBHOOK_SINKS.append(fn)


def record_brain_event(
    event: str,
    *,
    workspace_id: str,
    project_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "event": event,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "payload": payload or {},
        "at": datetime.now(UTC).isoformat(),
    }
    _AUDIT.append(row)
    for sink in list(_WEBHOOK_SINKS):
        try:
            sink(row)
        except Exception:
            pass
    return row


def list_brain_audit(*, project_id: str | None = None) -> list[dict[str, Any]]:
    if project_id is None:
        return list(_AUDIT)
    return [r for r in _AUDIT if r.get("project_id") == project_id]
