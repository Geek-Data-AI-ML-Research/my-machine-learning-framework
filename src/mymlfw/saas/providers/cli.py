"""CLI helpers for ``mymlfw cloud connect|list|gpus|launch|stop|terminate``."""

from __future__ import annotations

import json
import os
from typing import Any

from mymlfw.errors import MymlfwError
from mymlfw.saas.providers.service import (
    CloudProviderError,
    CloudProviderService,
    InMemoryCloudStore,
    default_cloud_service,
)

# Shared control-plane store so CLI ↔ API ↔ worker see the same runners.
_CLI_SVC: CloudProviderService | None = None


def _org_id() -> str:
    return os.environ.get("MYMLFW_ORG_ID", "org_01HCLI0CLOUD0ORG0000000000").strip()


def _flag_enabled() -> bool:
    # Fail closed: require MYMLFW_CLOUD_RUNNERS=1 (matches org feature_flags default off).
    raw = os.environ.get("MYMLFW_CLOUD_RUNNERS", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _cli_store() -> InMemoryCloudStore:
    from mymlfw.saas.control_plane import get_shared_cloud_store

    return get_shared_cloud_store()


def cli_service() -> CloudProviderService:
    global _CLI_SVC
    store = _cli_store()
    if _CLI_SVC is None or _CLI_SVC.org_id != _org_id():
        _CLI_SVC = default_cloud_service(
            org_id=_org_id(),
            cloud_runners=_flag_enabled(),
            store=store,
        )
    else:
        _CLI_SVC.feature_flags.cloud_runners = _flag_enabled()
        _CLI_SVC.store = store
    return _CLI_SVC


def reset_cli_service() -> None:
    """Test helper: drop process-local service + shared store."""
    global _CLI_SVC
    from mymlfw.saas.control_plane import reset_shared_cloud_store

    _CLI_SVC = None
    reset_shared_cloud_store()


def _dump(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(mode="json"), indent=2, sort_keys=True)
    return json.dumps(obj, indent=2, sort_keys=True, default=str)


def _wrap(exc: CloudProviderError) -> MymlfwError:
    return MymlfwError(exc.code, exc.message)


def cloud_connect(
    *,
    provider: str,
    api_key: str | None = None,
    role_arn: str | None = None,
    region: str = "us-east-1",
) -> str:
    svc = cli_service()
    try:
        if provider == "runpod":
            if not api_key:
                raise MymlfwError("USAGE", "Pass --api-key for RunPod connect")
            return _dump(svc.connect_runpod(api_key=api_key))
        if provider == "aws":
            if not role_arn:
                raise MymlfwError("USAGE", "Pass --role-arn for AWS connect")
            return _dump(svc.connect_aws(role_arn=role_arn, region=region))
        raise MymlfwError("USAGE", "provider must be runpod|aws")
    except CloudProviderError as exc:
        raise _wrap(exc) from exc


def cloud_disconnect(*, provider: str) -> str:
    try:
        return _dump(cli_service().disconnect(provider))  # type: ignore[arg-type]
    except CloudProviderError as exc:
        raise _wrap(exc) from exc


def cloud_list() -> str:
    svc = cli_service()
    try:
        accounts = [a.model_dump(mode="json") for a in svc.list_accounts()]
        runners = [r.model_dump(mode="json") for r in svc.list_runners()]
        return _dump({"accounts": accounts, "runners": runners})
    except CloudProviderError as exc:
        raise _wrap(exc) from exc


def cloud_gpus(*, provider: str) -> str:
    try:
        offers = [o.model_dump(mode="json") for o in cli_service().list_gpus(provider)]  # type: ignore[arg-type]
        return _dump({"provider": provider, "gpus": offers})
    except CloudProviderError as exc:
        raise _wrap(exc) from exc


def cloud_launch(
    *,
    provider: str,
    gpu_type: str,
    quote_only: bool = False,
    spot: bool = True,
) -> str:
    svc = cli_service()
    try:
        quote = svc.quote_launch(provider=provider, gpu_type=gpu_type)  # type: ignore[arg-type]
        if quote_only:
            return _dump(quote)
        runner = svc.launch(
            provider=provider,  # type: ignore[arg-type]
            gpu_type=gpu_type,
            quote_accepted_micros_hr=quote.cost_estimate_micros_hr,
            spot=spot,
        )
        return _dump(
            {
                "quote": quote.model_dump(mode="json"),
                "runner": runner.model_dump(mode="json"),
            }
        )
    except CloudProviderError as exc:
        raise _wrap(exc) from exc


def cloud_stop(*, runner_id: str) -> str:
    try:
        return _dump(cli_service().stop(runner_id))
    except CloudProviderError as exc:
        raise _wrap(exc) from exc


def cloud_terminate(*, runner_id: str) -> str:
    try:
        return _dump(cli_service().terminate(runner_id))
    except CloudProviderError as exc:
        raise _wrap(exc) from exc
