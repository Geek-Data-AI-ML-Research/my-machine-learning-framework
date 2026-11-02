"""Cloud provider connectors (RunPod / AWS) — stub until ``pc-cloud-providers``.

Local BYOC runner is the Day-3 default. Envelope vault + provision saga land
with the cloud track behind feature flag ``cloud_runners``.
"""

from __future__ import annotations

from typing import Any, Literal


ProviderName = Literal["runpod", "aws"]


def connect_provider_stub(provider: ProviderName, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {
        "status": "not_implemented",
        "provider": provider,
        "detail": "pc-cloud-providers: envelope creds + provision/attach not started",
        "feature_flag": "cloud_runners",
    }


def list_gpus_stub(provider: ProviderName) -> list[dict[str, Any]]:
    _ = provider
    return []
