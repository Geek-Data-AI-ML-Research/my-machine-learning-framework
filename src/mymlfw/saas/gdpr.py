"""GDPR export / erase helpers (soft-delete markers, no hard drop)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def export_project(docs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {"exported_at": datetime.now(UTC).isoformat(), "collections": docs}


def erase_project(docs: dict[str, list[dict[str, Any]]]) -> int:
    now = datetime.now(UTC).isoformat()
    n = 0
    for rows in docs.values():
        for row in rows:
            if row.get("deleted_at"):
                continue
            row["deleted_at"] = now
            n += 1
    return n
