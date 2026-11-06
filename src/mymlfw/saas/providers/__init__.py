"""Cloud provider connectors (RunPod / AWS) behind feature flag ``cloud_runners``.

Local BYOC runner is the Day-3 default. Envelope vault + two-phase provision
saga + 15m orphan sweeper + dead-man self-stop ship with this package.
"""

from __future__ import annotations

from typing import Any, Literal

from mymlfw.saas.providers.aws import (
    AWS_GPU_FAMILY_ALLOWLIST,
    IMDSV2_METADATA_OPTIONS,
    AwsClient,
    LiveAwsTransport,
    MockAwsTransport,
    generate_external_id,
)
from mymlfw.saas.providers.runpod import LiveRunPodTransport, MockRunPodTransport, RunPodClient
from mymlfw.saas.providers.service import (
    ORPHAN_SWEEPER_INTERVAL,
    CloudProviderError,
    CloudProviderService,
    InMemoryCloudStore,
    dead_man_bootstrap,
    default_cloud_service,
    mint_short_lived_runner_token,
    pick_runner_auto,
)

ProviderName = Literal["runpod", "aws"]


def connect_provider_stub(provider: ProviderName, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Back-compat shim — delegates to ``CloudProviderService`` when credentials given."""
    api_key = _kwargs.get("api_key")
    role_arn = _kwargs.get("role_arn")
    org_id = str(_kwargs.get("org_id") or "org_01HCOMPATCLOUD000000000000")
    svc = default_cloud_service(org_id=org_id, cloud_runners=True)
    if provider == "runpod" and api_key:
        return svc.connect_runpod(api_key=str(api_key)).model_dump(mode="json")
    if provider == "aws" and role_arn:
        return svc.connect_aws(
            role_arn=str(role_arn),
            region=str(_kwargs.get("region") or "us-east-1"),
        ).model_dump(mode="json")
    return {
        "status": "credentials_required",
        "provider": provider,
        "detail": "Pass api_key (runpod) or role_arn (aws); enable feature_flags.cloud_runners",
        "feature_flag": "cloud_runners",
    }


def list_gpus_stub(provider: ProviderName, **kwargs: Any) -> list[dict[str, Any]]:
    """List offers only after the caller supplies sealed credentials."""
    api_key = kwargs.get("api_key")
    role_arn = kwargs.get("role_arn")
    org_id = str(kwargs.get("org_id") or "org_01HCOMPATCLOUD000000000000")
    svc = default_cloud_service(org_id=org_id, cloud_runners=True)
    if provider == "runpod" and api_key:
        svc.connect_runpod(api_key=str(api_key))
    elif provider == "aws" and role_arn:
        svc.connect_aws(
            role_arn=str(role_arn),
            region=str(kwargs.get("region") or "us-east-1"),
        )
    else:
        raise CloudProviderError(
            "credentials_required",
            "Pass api_key or role_arn; list_gpus does not invent credentials.",
        )
    return [o.model_dump(mode="json") for o in svc.list_gpus(provider)]


__all__ = [
    "AWS_GPU_FAMILY_ALLOWLIST",
    "IMDSV2_METADATA_OPTIONS",
    "AwsClient",
    "CloudProviderError",
    "CloudProviderService",
    "InMemoryCloudStore",
    "LiveAwsTransport",
    "LiveRunPodTransport",
    "MockAwsTransport",
    "MockRunPodTransport",
    "ORPHAN_SWEEPER_INTERVAL",
    "ProviderName",
    "RunPodClient",
    "connect_provider_stub",
    "dead_man_bootstrap",
    "default_cloud_service",
    "generate_external_id",
    "list_gpus_stub",
    "mint_short_lived_runner_token",
    "pick_runner_auto",
]
