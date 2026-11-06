"""Worker entrypoint — fair-share claim + orphan sweeper + outbox drain."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mymlfw.saas.control_plane import drain_memory_outbox, get_shared_cloud_store
from mymlfw.saas.providers.service import InMemoryCloudStore
from mymlfw.worker.fair_share import FairShareConfig, FairShareQueue
from mymlfw.worker.orphan_sweeper import sweep_all_orgs


def run_once(queue: FairShareQueue | None = None) -> dict:
    """Single fair-share claim tick."""
    q = queue or FairShareQueue(FairShareConfig())
    job = q.claim_next()
    return {
        "claimed": job is not None,
        "job": job,
        "pending": q.pending_count(),
    }


def run_orphan_sweep(
    *,
    store: InMemoryCloudStore | None = None,
    cloud_runners: bool = True,
) -> dict[str, Any]:
    """15m cadence hook — terminate unprotected tagged remotes."""
    return sweep_all_orgs(
        store=store or get_shared_cloud_store(),
        cloud_runners=cloud_runners,
    )


async def drain_mongo_outbox(*, limit: int = 50) -> list[dict[str, Any]]:
    """Claim + mark processed for pending Mongo outbox events when URI is set."""
    uri = os.environ.get("MYMLFW_MONGO_URI", "").strip()
    if not uri:
        return []
    db_name = os.environ.get("MYMLFW_MONGO_DB", "mymlfw").strip() or "mymlfw"
    from mymlfw.saas.db.client import create_saas_mongo_client, get_saas_database
    from mymlfw.saas.db.outbox import claim_next_outbox_event, mark_outbox_processed

    client = create_saas_mongo_client(uri)
    try:
        db = get_saas_database(client, db_name)
        drained: list[dict[str, Any]] = []
        for _ in range(limit):
            event = await claim_next_outbox_event(db)
            if event is None:
                break
            # Side-effect handlers land per event_type; mark processed after claim.
            await mark_outbox_processed(db, event["_id"])
            drained.append(
                {
                    "event_id": event["_id"],
                    "event_type": event.get("event_type"),
                    "workspace_id": event.get("workspace_id"),
                    "status": "processed",
                }
            )
        return drained
    finally:
        await client.close()


def main() -> None:
    mongo_drained = asyncio.run(drain_mongo_outbox())
    print(
        json.dumps(
            {
                "claim": run_once(),
                "orphan_sweep": run_orphan_sweep(),
                "outbox_memory": drain_memory_outbox(),
                "outbox_mongo": mongo_drained,
            },
            default=str,
        )
    )


if __name__ == "__main__":
    main()
