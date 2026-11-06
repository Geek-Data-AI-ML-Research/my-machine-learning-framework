"""15-minute orphan cloud runner sweeper (worker cadence)."""

from __future__ import annotations

from typing import Any

from mymlfw.saas.providers.service import (
    ORPHAN_SWEEPER_INTERVAL,
    CloudProviderService,
    InMemoryCloudStore,
)


def sweep_all_orgs(
    *,
    store: InMemoryCloudStore,
    org_ids: list[str] | None = None,
    cloud_runners: bool = True,
) -> dict[str, Any]:
    """Run ``sweep_orphans`` for each org that has connected accounts."""
    orgs = org_ids or sorted(
        {
            doc["org_id"]
            for doc in store.accounts.values()
            if doc.get("status") == "connected" and doc.get("org_id")
        }
    )
    results: list[dict[str, Any]] = []
    for org_id in orgs:
        svc = CloudProviderService(
            org_id=org_id,
            store=store,
        )
        # Honor flag via FeatureFlags default; callers enable for worker jobs.
        from mymlfw.saas.schemas import FeatureFlags

        svc.feature_flags = FeatureFlags(cloud_runners=cloud_runners)
        if not cloud_runners:
            continue
        try:
            results.append({"org_id": org_id, **svc.sweep_orphans()})
        except Exception as exc:  # noqa: BLE001 — worker must continue other orgs
            results.append(
                {
                    "org_id": org_id,
                    "error_code": getattr(exc, "code", type(exc).__name__),
                    "message": getattr(exc, "message", str(exc)),
                }
            )
    return {
        "interval_minutes": int(ORPHAN_SWEEPER_INTERVAL.total_seconds() // 60),
        "orgs": results,
    }
