"""ensure_saas_indexes: ESR, one-open-lever, partial outbox, TTL stubs, jsonSchema."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import IndexModel

# Exported for unit tests asserting definition presence.
ONE_OPEN_LEVER_INDEX: dict[str, Any] = {
    "keys": [("workspace_id", ASCENDING), ("project_id", ASCENDING), ("status", ASCENDING)],
    "name": "uniq_one_open_lever",
    "unique": True,
    "partialFilterExpression": {"status": "open", "deleted_at": None},
}

OUTBOX_PARTIAL_INDEX: dict[str, Any] = {
    "keys": [("created_at", ASCENDING)],
    "name": "outbox_active_created_at",
    "partialFilterExpression": {"status": {"$in": ["pending", "processing"]}},
}

ESR_TENANT_TIMELINE: dict[str, Any] = {
    "keys": [
        ("workspace_id", ASCENDING),
        ("project_id", ASCENDING),
        ("created_at", DESCENDING),
    ],
    "name": "esr_tenant_timeline",
}


def _index_model(spec: dict[str, Any]) -> IndexModel:
    keys = spec["keys"]
    kwargs = {k: v for k, v in spec.items() if k != "keys"}
    return IndexModel(keys, **kwargs)


async def ensure_saas_indexes(db: AsyncDatabase) -> None:
    """Create core indexes and soft jsonSchema validators where feasible."""
    experiments = db["experiments"]
    await experiments.create_indexes(
        [
            _index_model(ONE_OPEN_LEVER_INDEX),
            _index_model(ESR_TENANT_TIMELINE),
        ]
    )

    for name in (
        "project_goals",
        "missions",
        "dead_ends",
        "runs",
        "daily_progress",
        "memory_chunks",
        "autopilot_nodes",
        "project_credits",
    ):
        await db[name].create_indexes([_index_model(ESR_TENANT_TIMELINE)])

    missions = db["missions"]
    await missions.create_index(
        [
            ("workspace_id", ASCENDING),
            ("project_id", ASCENDING),
            ("status", ASCENDING),
            ("lease_expires_at", ASCENDING),
        ],
        name="mission_queue_lease",
    )

    outbox = db["outbox_events"]
    await outbox.create_indexes(
        [
            _index_model(OUTBOX_PARTIAL_INDEX),
            IndexModel(
                [("status", ASCENDING), ("processed_at", ASCENDING)],
                name="outbox_processed_ttl",
                # TTL applied when processed_at is set; expireAfterSeconds stub.
                expireAfterSeconds=7 * 24 * 3600,
                partialFilterExpression={"status": "processed"},
            ),
        ]
    )

    # Soft-delete TTL stub on projects (deleted_at must be a date for TTL to fire).
    await db["projects"].create_index(
        [("deleted_at", ASCENDING)],
        name="projects_soft_delete_ttl",
        expireAfterSeconds=30 * 24 * 3600,
        partialFilterExpression={"deleted_at": {"$type": "date"}},
    )

    await _apply_json_schema(db)


_CORE_TENANT_SCHEMA: dict[str, Any] = {
    "bsonType": "object",
    "required": ["workspace_id", "project_id", "schema_version"],
    "properties": {
        "workspace_id": {"bsonType": "string", "pattern": "^org_"},
        "project_id": {"bsonType": "string", "pattern": "^prj_"},
        "schema_version": {"bsonType": "int", "minimum": 1},
    },
}


async def _apply_json_schema(db: AsyncDatabase) -> None:
    for coll in ("experiments", "project_goals", "missions", "dead_ends"):
        try:
            await db.command(
                {
                    "collMod": coll,
                    "validator": {"$jsonSchema": _CORE_TENANT_SCHEMA},
                    "validationLevel": "moderate",
                }
            )
        except Exception:
            # Collection may not exist yet — create empty then retry once.
            await db.create_collection(coll)
            await db.command(
                {
                    "collMod": coll,
                    "validator": {"$jsonSchema": _CORE_TENANT_SCHEMA},
                    "validationLevel": "moderate",
                }
            )
