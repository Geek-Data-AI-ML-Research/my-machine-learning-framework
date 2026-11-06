"""outbox_events helpers: enqueue + atomic claim (pending → processing)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from ulid import ULID


def new_outbox_id() -> str:
    return f"obx_{ULID()}"


async def enqueue_outbox_event(
    db: AsyncDatabase,
    *,
    event_type: str,
    payload: dict[str, Any],
    workspace_id: str,
    project_id: str | None = None,
    session: Any | None = None,
) -> str:
    event_id = new_outbox_id()
    now = datetime.now(UTC)
    doc = {
        "_id": event_id,
        "event_type": event_type,
        "payload": payload,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "status": "pending",
        "created_at": now,
        "processed_at": None,
        "schema_version": 1,
    }
    kwargs: dict[str, Any] = {}
    if session is not None:
        kwargs["session"] = session
    await db["outbox_events"].insert_one(doc, **kwargs)
    return event_id


async def claim_next_outbox_event(db: AsyncDatabase) -> dict[str, Any] | None:
    """Atomically claim one pending event → processing."""
    now = datetime.now(UTC)
    return await db["outbox_events"].find_one_and_update(
        {"status": "pending"},
        {"$set": {"status": "processing", "claimed_at": now}},
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def mark_outbox_processed(db: AsyncDatabase, event_id: str) -> None:
    now = datetime.now(UTC)
    await db["outbox_events"].update_one(
        {"_id": event_id},
        {"$set": {"status": "processed", "processed_at": now}},
    )
