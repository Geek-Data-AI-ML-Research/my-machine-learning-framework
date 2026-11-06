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
        "project_sources",
        "project_roadmap_strategies",
        "runs",
        "oof_artifacts",
        "daily_progress",
        "memory_chunks",
        "autopilot_sessions",
        "autopilot_nodes",
        "project_credits",
        "project_axioms",
        "public_snapshots",
        "runners",
    ):
        await db[name].create_indexes([_index_model(ESR_TENANT_TIMELINE)])

    # Org-scoped cloud provider accounts (one connected row per provider).
    await db["cloud_provider_accounts"].create_indexes(
        [
            IndexModel(
                [("org_id", ASCENDING), ("provider", ASCENDING)],
                name="uniq_org_cloud_provider",
                unique=True,
                partialFilterExpression={
                    "status": "connected",
                    "deleted_at": None,
                },
            ),
            IndexModel(
                [("org_id", ASCENDING), ("updated_at", DESCENDING)],
                name="cloud_accounts_org_timeline",
            ),
        ]
    )

    await db["runners"].create_index(
        [
            ("org_id", ASCENDING),
            ("status", ASCENDING),
            ("kind", ASCENDING),
        ],
        name="runners_org_status_kind",
        partialFilterExpression={"deleted_at": None},
    )

    # Parallel R0 updates: distinct nd_ docs keyed by session (no embedded arrays).
    await db["autopilot_nodes"].create_index(
        [
            ("workspace_id", ASCENDING),
            ("project_id", ASCENDING),
            ("session_id", ASCENDING),
            ("created_at", ASCENDING),
        ],
        name="autopilot_nodes_by_session",
        partialFilterExpression={"deleted_at": None},
    )
    await db["autopilot_sessions"].create_index(
        [
            ("workspace_id", ASCENDING),
            ("project_id", ASCENDING),
            ("status", ASCENDING),
        ],
        name="autopilot_sessions_active",
        partialFilterExpression={
            "status": {"$in": ["running", "paused"]},
            "deleted_at": None,
        },
    )
    # At most one running/paused Autopilot session per project (Mongo path).
    await db["autopilot_sessions"].create_index(
        [("workspace_id", ASCENDING), ("project_id", ASCENDING)],
        name="uniq_active_autopilot_session",
        unique=True,
        partialFilterExpression={
            "status": {"$in": ["running", "paused"]},
            "deleted_at": None,
        },
    )
    # Unified lever/autopilot mutex on projects document.
    await db["projects"].create_index(
        [("workspace_id", ASCENDING), ("_id", ASCENDING)],
        name="projects_tenant_pk",
        unique=True,
        partialFilterExpression={"deleted_at": None},
    )
    await db["projects"].create_index(
        [("active_execution_lock.holder_id", ASCENDING)],
        name="projects_execution_lock_holder",
        partialFilterExpression={
            "active_execution_lock": {"$type": "object"},
            "deleted_at": None,
        },
    )
    # Stale pending OOF uploads: query by status + created_at (TTL purge in worker).
    await db["oof_artifacts"].create_index(
        [
            ("workspace_id", ASCENDING),
            ("project_id", ASCENDING),
            ("status", ASCENDING),
            ("created_at", ASCENDING),
        ],
        name="oof_pending_upload",
        partialFilterExpression={"status": "pending_upload", "deleted_at": None},
    )

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

    await db["mcp_gap_reports"].create_indexes(
        [
            IndexModel(
                [("workspace_id", ASCENDING), ("created_at", DESCENDING)],
                name="mcp_gaps_workspace_timeline",
                partialFilterExpression={"deleted_at": None},
            ),
            IndexModel(
                [
                    ("workspace_id", ASCENDING),
                    ("project_id", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="mcp_gaps_project_timeline",
                partialFilterExpression={
                    "deleted_at": None,
                    "project_id": {"$type": "string"},
                },
            ),
        ]
    )

    # MCP PATs — hash lookup + workspace listing (plaintext never stored).
    await db["agent_pats"].create_indexes(
        [
            IndexModel(
                [("token_hash", ASCENDING)],
                name="uniq_agent_pat_hash",
                unique=True,
                partialFilterExpression={"deleted_at": None},
            ),
            IndexModel(
                [("workspace_id", ASCENDING), ("created_at", DESCENDING)],
                name="agent_pats_workspace_timeline",
                partialFilterExpression={"deleted_at": None},
            ),
        ]
    )

    await db["public_snapshots"].create_index(
        [("slug", ASCENDING)],
        name="public_snapshots_slug_unique",
        unique=True,
    )

    outbox = db["outbox_events"]
    await outbox.create_indexes(
        [
            _index_model(OUTBOX_PARTIAL_INDEX),
            IndexModel(
                # TTL indexes must be single-field (Mongo rejects compound + expireAfterSeconds).
                [("processed_at", ASCENDING)],
                name="outbox_processed_ttl",
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

    await _ensure_usage_events_timeseries(db)
    await _apply_json_schema(db)


async def _ensure_usage_events_timeseries(db: AsyncDatabase) -> None:
    """Create ``usage_events`` as a time-series collection when missing."""
    names = await db.list_collection_names()
    if "usage_events" in names:
        return
    try:
        await db.create_collection(
            "usage_events",
            timeseries={
                "timeField": "created_at",
                "metaField": "meta",
                "granularity": "seconds",
            },
            expireAfterSeconds=90 * 24 * 3600,
        )
    except Exception:
        # Standalone / older servers may reject time-series; fall back to plain.
        if "usage_events" not in await db.list_collection_names():
            await db.create_collection("usage_events")


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
