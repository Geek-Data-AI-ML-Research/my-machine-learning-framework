"""schema_version migration runner stub."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

MigrationFn = Callable[[AsyncDatabase], Awaitable[None]]

CURRENT_SCHEMA_VERSION = 1


async def _noop_v1(db: AsyncDatabase) -> None:
    await db["schema_migrations"].update_one(
        {"_id": "saas"},
        {
            "$set": {
                "version": 1,
                "description": "Wave 1 baseline",
            },
            "$setOnInsert": {"_id": "saas"},
        },
        upsert=True,
    )


MIGRATIONS: list[tuple[int, MigrationFn]] = [
    (1, _noop_v1),
]


async def get_schema_version(db: AsyncDatabase) -> int:
    doc = await db["schema_migrations"].find_one({"_id": "saas"})
    if not doc:
        return 0
    return int(doc.get("version", 0))


async def run_migrations(db: AsyncDatabase) -> dict[str, Any]:
    """Apply pending migrations in order. Safe to call on every boot."""
    current = await get_schema_version(db)
    applied: list[int] = []
    for version, fn in MIGRATIONS:
        if version <= current:
            continue
        await fn(db)
        await db["schema_migrations"].update_one(
            {"_id": "saas"},
            {"$set": {"version": version}},
            upsert=True,
        )
        applied.append(version)
        current = version
    return {"current": current, "applied": applied, "target": CURRENT_SCHEMA_VERSION}
