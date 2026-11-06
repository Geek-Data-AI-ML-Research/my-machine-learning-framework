"""Cloud transport mode: live when the user sealed credentials; mock for CI."""

from __future__ import annotations

import os


def use_cloud_mock() -> bool:
    """Return True when providers must not call real RunPod/AWS APIs.

    - ``MYMLFW_CLOUD_MOCK=1`` → always mock (local sandbox).
    - ``MYMLFW_CLOUD_MOCK=0`` → always live (billable once credentials exist).
    - ``PYTEST_CURRENT_TEST`` set → mock (pytest safety net).
    - Otherwise → **live** so a sealed RunPod API key / AWS role ARN actually spends.
    """
    raw = os.environ.get("MYMLFW_CLOUD_MOCK", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))
