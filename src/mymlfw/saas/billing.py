"""Usage events + billing rollup (Int64 cost_micros only)."""

from __future__ import annotations

from typing import Any

_EVENTS: list[dict[str, Any]] = []


def reset_billing_for_tests() -> None:
    _EVENTS.clear()


def record_usage_event(
    *,
    workspace_id: str,
    cost_micros: int,
    kind: str,
) -> dict[str, Any]:
    if not isinstance(cost_micros, int) or isinstance(cost_micros, bool):
        raise TypeError("cost_micros must be int")
    row = {
        "workspace_id": workspace_id,
        "cost_micros": int(cost_micros),
        "kind": kind,
    }
    _EVENTS.append(row)
    return row


def billing_summary(workspace_id: str) -> dict[str, Any]:
    total = sum(e["cost_micros"] for e in _EVENTS if e["workspace_id"] == workspace_id)
    return {"workspace_id": workspace_id, "cost_micros": int(total), "n": len(_EVENTS)}
