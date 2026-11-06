"""Process-shared control-plane state for API / MCP / worker / CLI.

Production deploys still prefer Mongo for durability; this module ensures
single-process Compose and unit tests share one cloud store + org flags so
surfaces do not diverge. Swap stores behind these accessors when Mongo repos land.
"""

from __future__ import annotations

from typing import Any

from mymlfw.saas.providers.service import InMemoryCloudStore
from mymlfw.saas.schemas import FeatureFlags, OrgEntitlements

# One shared in-process cloud store (API ↔ MCP ↔ worker ↔ CLI).
_CLOUD_STORE = InMemoryCloudStore()
# org_id → feature flags / entitlements (authoritative for MCP + workers).
_ORG_FLAGS: dict[str, FeatureFlags] = {}
_ORG_ENTS: dict[str, OrgEntitlements] = {}
# In-memory outbox when Mongo is unavailable (worker drains this list).
_MEMORY_OUTBOX: list[dict[str, Any]] = []


def get_shared_cloud_store() -> InMemoryCloudStore:
    return _CLOUD_STORE


def reset_shared_cloud_store() -> InMemoryCloudStore:
    """Test helper — clears shared cloud state."""
    global _CLOUD_STORE
    _CLOUD_STORE = InMemoryCloudStore()
    return _CLOUD_STORE


def set_org_policy(
    org_id: str,
    *,
    feature_flags: FeatureFlags | dict[str, Any] | None = None,
    entitlements: OrgEntitlements | dict[str, Any] | None = None,
) -> None:
    if feature_flags is not None:
        if isinstance(feature_flags, FeatureFlags):
            _ORG_FLAGS[org_id] = feature_flags
        else:
            _ORG_FLAGS[org_id] = FeatureFlags(**feature_flags)
    if entitlements is not None:
        if isinstance(entitlements, OrgEntitlements):
            _ORG_ENTS[org_id] = entitlements
        else:
            _ORG_ENTS[org_id] = OrgEntitlements(**entitlements)


def get_org_feature_flags(org_id: str) -> FeatureFlags:
    return _ORG_FLAGS.get(org_id) or FeatureFlags()


def get_org_entitlements(org_id: str) -> OrgEntitlements:
    return _ORG_ENTS.get(org_id) or OrgEntitlements()


def sync_org_policy_from_principal(principal: dict[str, Any]) -> None:
    """Call after auth resolve so MCP/worker see the same flags as API."""
    org = principal.get("org")
    if org is None:
        return
    org_id = getattr(org, "id", None) or (org.get("id") if isinstance(org, dict) else None)
    if not org_id:
        return
    flags = getattr(org, "feature_flags", None)
    if flags is None and isinstance(org, dict):
        flags = org.get("feature_flags")
    ents = getattr(org, "entitlements", None)
    if ents is None and isinstance(org, dict):
        ents = org.get("entitlements")
    set_org_policy(org_id, feature_flags=flags, entitlements=ents)


def enqueue_memory_outbox(
    *,
    event_type: str,
    payload: dict[str, Any],
    workspace_id: str,
    project_id: str | None = None,
) -> str:
    from ulid import ULID

    event_id = f"obx_{ULID()}"
    _MEMORY_OUTBOX.append(
        {
            "_id": event_id,
            "event_type": event_type,
            "payload": payload,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "status": "pending",
        }
    )
    return event_id


def drain_memory_outbox(*, limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while _MEMORY_OUTBOX and len(out) < limit:
        row = _MEMORY_OUTBOX.pop(0)
        row["status"] = "processed"
        out.append(row)
    return out


def reset_control_plane_for_tests() -> None:
    reset_shared_cloud_store()
    _ORG_FLAGS.clear()
    _ORG_ENTS.clear()
    _MEMORY_OUTBOX.clear()
