"""SaaS-side helpers for MCP cloud tools (keeps mcp/ handlers thin)."""

from __future__ import annotations

from typing import Any

from mymlfw.saas.control_plane import (
    get_org_entitlements,
    get_org_feature_flags,
    get_shared_cloud_store,
)
from mymlfw.saas.providers.service import CloudProviderService, InMemoryCloudStore
from mymlfw.saas.schemas import FeatureFlags


def cloud_service_for_org(
    org_id: str,
    *,
    cloud_store: Any | None = None,
) -> tuple[CloudProviderService, bool]:
    """Return ``(service, cloud_runners_enabled)`` from org policy only.

    Never elevates feature flags. Callers that need the flag on must use the
    owner API ``PATCH /v1/orgs/current/feature-flags``.
    """
    store = (
        cloud_store
        if isinstance(cloud_store, InMemoryCloudStore)
        else get_shared_cloud_store()
    )
    enabled = bool(get_org_feature_flags(org_id).cloud_runners)
    svc = CloudProviderService(
        org_id=org_id,
        store=store,
        feature_flags=FeatureFlags(cloud_runners=enabled),
        entitlements=get_org_entitlements(org_id),
    )
    return svc, enabled
