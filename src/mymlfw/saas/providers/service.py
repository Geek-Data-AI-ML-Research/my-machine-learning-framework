"""Cloud provider accounts + unified runners + provision saga + orphan sweeper."""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from mymlfw.saas.ids import new_prefixed_id, new_runner_id
from mymlfw.saas.providers.aws import AwsClient, MockAwsTransport, generate_external_id
from mymlfw.saas.providers.runpod import MockRunPodTransport, RunPodClient
from mymlfw.saas.schemas import (
    CloudGpuOffer,
    CloudLaunchQuote,
    CloudProviderAccountResponse,
    CloudProviderName,
    FeatureFlags,
    OrgEntitlements,
    RunnerKind,
    RunnerLifecycleStatus,
    RunnerResponse,
)
from mymlfw.saas.secrets.envelope import (
    EnvelopeBlob,
    EnvelopeError,
    open_secret,
    seal_secret,
)

ProviderName = Literal["runpod", "aws"]
ORPHAN_SWEEPER_INTERVAL = timedelta(minutes=15)
DEFAULT_IDLE_TIMEOUT_MINUTES = 30


class CloudProviderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def new_cloud_account_id() -> str:
    return new_prefixed_id("cpa")


@dataclass
class InMemoryCloudStore:
    """Dict-backed ``cloud_provider_accounts`` + ``runners`` for unit tests."""

    accounts: dict[str, dict[str, Any]] = field(default_factory=dict)
    runners: dict[str, dict[str, Any]] = field(default_factory=dict)
    # org_id -> provider -> account_id
    by_org_provider: dict[str, dict[str, str]] = field(default_factory=dict)
    # sealed secrets by account_id (never listed in API/MCP)
    secrets: dict[str, EnvelopeBlob] = field(default_factory=dict)
    usage_micros_today: dict[str, int] = field(default_factory=dict)

    def account_for(self, org_id: str, provider: str) -> dict[str, Any] | None:
        aid = (self.by_org_provider.get(org_id) or {}).get(provider)
        if not aid:
            return None
        row = self.accounts.get(aid)
        return None if row is None else dict(row)


@dataclass
class CloudProviderService:
    """Org-scoped cloud connect / launch / stop behind ``cloud_runners``."""

    org_id: str
    store: InMemoryCloudStore
    feature_flags: FeatureFlags = field(default_factory=FeatureFlags)
    entitlements: OrgEntitlements = field(default_factory=OrgEntitlements)
    runpod_transport: Any | None = None  # MockRunPodTransport | LiveRunPodTransport
    aws_transport: Any | None = None  # MockAwsTransport | LiveAwsTransport
    idle_timeout_minutes: int = DEFAULT_IDLE_TIMEOUT_MINUTES

    def require_flag(self) -> None:
        if not self.feature_flags.cloud_runners:
            raise CloudProviderError(
                "feature_disabled",
                "Enable org feature_flags.cloud_runners to use cloud providers",
            )

    def _account_response(self, doc: dict[str, Any]) -> CloudProviderAccountResponse:
        provider = CloudProviderName(doc["provider"])
        return CloudProviderAccountResponse(
            account_id=doc["_id"],
            org_id=doc["org_id"],
            provider=provider,
            status=doc["status"],
            role_arn=doc.get("role_arn"),
            external_id=doc.get("external_id") if provider == CloudProviderName.aws else None,
            region=doc.get("region"),
            has_credentials=bool(doc.get("has_credentials")),
            kek_version=int(doc.get("kek_version") or 0) or None,
            connected_at=doc.get("connected_at"),
        )

    def _runner_response(self, doc: dict[str, Any]) -> RunnerResponse:
        return RunnerResponse(
            runner_id=doc["_id"],
            org_id=doc["org_id"],
            kind=RunnerKind(doc["kind"]),
            status=RunnerLifecycleStatus(doc["status"]),
            provider=CloudProviderName(doc["provider"]) if doc.get("provider") else None,
            region=doc.get("region") or "",
            gpu_type=doc.get("gpu_type") or "",
            cost_estimate_micros_hr=int(doc.get("cost_estimate_micros_hr") or 0),
            provider_instance_id=doc.get("provider_instance_id"),
            idle_timeout_minutes=int(
                doc.get("idle_timeout_minutes") or self.idle_timeout_minutes
            ),
            last_heartbeat_at=doc.get("last_heartbeat_at"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    def connect_runpod(self, *, api_key: str) -> CloudProviderAccountResponse:
        self.require_flag()
        if not api_key.strip():
            raise CloudProviderError("invalid_api_key", "RunPod API key required")
        existing = self.store.account_for(self.org_id, "runpod")
        now = datetime.now(UTC)
        try:
            sealed = seal_secret(api_key.strip())
        except EnvelopeError as exc:
            raise CloudProviderError(exc.code, exc.message) from exc
        if existing:
            account_id = existing["_id"]
            doc = self.store.accounts[account_id]
            doc.update(
                {
                    "status": "connected",
                    "has_credentials": True,
                    "kek_version": sealed.kek_version,
                    "connected_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                }
            )
        else:
            account_id = new_cloud_account_id()
            doc = {
                "_id": account_id,
                "org_id": self.org_id,
                "provider": "runpod",
                "status": "connected",
                "has_credentials": True,
                "kek_version": sealed.kek_version,
                "role_arn": None,
                "external_id": None,
                "region": None,
                "connected_at": now,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
                "schema_version": 1,
            }
            self.store.accounts[account_id] = doc
            self.store.by_org_provider.setdefault(self.org_id, {})["runpod"] = account_id
        self.store.secrets[account_id] = sealed
        # Probe catalog with the sealed key (live RunPod HTTP unless mock mode).
        client = self._runpod_client(api_key.strip())
        _ = client.list_gpus()
        return self._account_response(doc)

    def connect_aws(
        self,
        *,
        role_arn: str,
        region: str = "us-east-1",
    ) -> CloudProviderAccountResponse:
        self.require_flag()
        if not role_arn.startswith("arn:aws:iam::"):
            raise CloudProviderError("invalid_role_arn", "Expected arn:aws:iam::… role ARN")
        existing = self.store.account_for(self.org_id, "aws")
        now = datetime.now(UTC)
        if existing and existing.get("external_id"):
            # ExternalId is immutable once issued.
            external_id = existing["external_id"]
            account_id = existing["_id"]
            doc = self.store.accounts[account_id]
            doc.update(
                {
                    "role_arn": role_arn,
                    "region": region,
                    "status": "connected",
                    "has_credentials": True,
                    "connected_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                }
            )
        elif existing:
            # Reuse row; mint ExternalId once if a prior incomplete row lacked it.
            account_id = existing["_id"]
            doc = self.store.accounts[account_id]
            external_id = str(existing.get("external_id") or generate_external_id())
            doc.update(
                {
                    "role_arn": role_arn,
                    "region": region,
                    "external_id": external_id,
                    "status": "connected",
                    "has_credentials": True,
                    "connected_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                }
            )
        else:
            external_id = generate_external_id()
            account_id = new_cloud_account_id()
            doc = {
                "_id": account_id,
                "org_id": self.org_id,
                "provider": "aws",
                "status": "connected",
                "has_credentials": True,
                "kek_version": None,
                "role_arn": role_arn,
                "external_id": external_id,
                "region": region,
                "connected_at": now,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
                "schema_version": 1,
            }
            self.store.accounts[account_id] = doc
            self.store.by_org_provider.setdefault(self.org_id, {})["aws"] = account_id
        # Envelope stub for STS session material placeholder (role assume later).
        try:
            sealed = seal_secret(f"{role_arn}|{external_id}")
        except EnvelopeError as exc:
            raise CloudProviderError(exc.code, exc.message) from exc
        doc["kek_version"] = sealed.kek_version
        self.store.secrets[account_id] = sealed
        client = self._aws_client(role_arn=role_arn, external_id=external_id, region=region)
        _ = client.list_gpus()
        return self._account_response(doc)

    def disconnect(self, provider: ProviderName) -> CloudProviderAccountResponse:
        self.require_flag()
        doc = self.store.account_for(self.org_id, provider)
        if doc is None:
            raise CloudProviderError("not_connected", f"{provider} is not connected")
        now = datetime.now(UTC)
        row = self.store.accounts[doc["_id"]]
        row["status"] = "disconnected"
        row["has_credentials"] = False
        row["updated_at"] = now
        row["deleted_at"] = now
        self.store.secrets.pop(doc["_id"], None)
        return self._account_response(row)

    def list_accounts(self) -> list[CloudProviderAccountResponse]:
        self.require_flag()
        out: list[CloudProviderAccountResponse] = []
        for provider in ("runpod", "aws"):
            doc = self.store.account_for(self.org_id, provider)
            if doc and doc.get("status") == "connected":
                out.append(self._account_response(doc))
        return out

    def list_gpus(self, provider: ProviderName) -> list[CloudGpuOffer]:
        self.require_flag()
        client = self._client_for(provider)
        rows = client.list_gpus()
        return [
            CloudGpuOffer(
                provider=CloudProviderName(provider),
                gpu_type=str(r["gpu_type"]),
                gpu_id=str(r.get("gpu_id") or r["gpu_type"]),
                stock=int(r.get("stock") or 0),
                cost_estimate_micros_hr=int(r["cost_estimate_micros_hr"]),
                region=str(r.get("region") or ""),
                vram_gb=int(r.get("vram_gb") or 0),
                spot_ok=bool(r.get("spot_ok", provider == "aws")),
            )
            for r in rows
        ]

    def quote_launch(
        self, *, provider: ProviderName, gpu_type: str
    ) -> CloudLaunchQuote:
        self.require_flag()
        offers = self.list_gpus(provider)
        match = next((o for o in offers if o.gpu_type == gpu_type or o.gpu_id == gpu_type), None)
        if match is None:
            raise CloudProviderError("unknown_gpu_type", f"No offer for {gpu_type}")
        if match.stock <= 0:
            raise CloudProviderError("out_of_stock", f"{gpu_type} has no stock")
        used = int(self.store.usage_micros_today.get(self.org_id, 0))
        cap = int(self.entitlements.max_cloud_micros_day)
        return CloudLaunchQuote(
            provider=CloudProviderName(provider),
            gpu_type=match.gpu_type,
            cost_estimate_micros_hr=match.cost_estimate_micros_hr,
            region=match.region,
            max_cloud_micros_day=cap,
            used_cloud_micros_today=used,
            within_entitlement=cap <= 0 or (used + match.cost_estimate_micros_hr) <= cap,
        )

    def launch(
        self,
        *,
        provider: ProviderName,
        gpu_type: str,
        quote_accepted_micros_hr: int | None = None,
        spot: bool = True,
    ) -> RunnerResponse:
        """Two-phase saga: insert ``provisioning`` runner, then create remote."""
        self.require_flag()
        quote = self.quote_launch(provider=provider, gpu_type=gpu_type)
        if quote_accepted_micros_hr is None:
            raise CloudProviderError(
                "quote_required",
                "Pass cost_estimate_micros_hr from quote before create",
            )
        if int(quote_accepted_micros_hr) != quote.cost_estimate_micros_hr:
            raise CloudProviderError(
                "quote_mismatch",
                "Quoted micros/hr does not match current offer — re-quote",
            )
        if not quote.within_entitlement and self.entitlements.max_cloud_micros_day > 0:
            raise CloudProviderError(
                "cloud_budget_exceeded",
                "Launch would exceed max_cloud_micros_day entitlement",
            )
        account = self.store.account_for(self.org_id, provider)
        if account is None or account.get("status") != "connected":
            raise CloudProviderError("not_connected", f"Connect {provider} first")

        now = datetime.now(UTC)
        runner_id = new_runner_id()
        kind = (
            RunnerKind.runpod_pod if provider == "runpod" else RunnerKind.aws_ec2
        )
        doc: dict[str, Any] = {
            "_id": runner_id,
            "org_id": self.org_id,
            "kind": kind.value,
            "status": RunnerLifecycleStatus.provisioning.value,
            "provider": provider,
            "region": quote.region,
            "gpu_type": quote.gpu_type,
            "cost_estimate_micros_hr": quote.cost_estimate_micros_hr,
            "provider_instance_id": None,
            "idle_timeout_minutes": self.idle_timeout_minutes,
            "last_heartbeat_at": None,
            "account_id": account["_id"],
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
            "schema_version": 1,
            "dead_man": dead_man_bootstrap(
                idle_timeout_minutes=self.idle_timeout_minutes
            ),
        }
        # Phase 1: persist runners row BEFORE remote create.
        self.store.runners[runner_id] = doc

        try:
            if provider == "runpod":
                api_key = self._runpod_api_key(account["_id"])
                remote = self._runpod_client(api_key).create(
                    runner_id=runner_id,
                    org_id=self.org_id,
                    gpu_type=quote.gpu_type,
                    cost_estimate_micros_hr=quote.cost_estimate_micros_hr,
                    idle_timeout_minutes=self.idle_timeout_minutes,
                )
            else:
                remote = self._aws_client(
                    role_arn=account["role_arn"],
                    external_id=account["external_id"],
                    region=account.get("region") or "us-east-1",
                ).create(
                    runner_id=runner_id,
                    org_id=self.org_id,
                    gpu_type=quote.gpu_type,
                    cost_estimate_micros_hr=quote.cost_estimate_micros_hr,
                    idle_timeout_minutes=self.idle_timeout_minutes,
                    spot=spot,
                )
        except Exception as exc:
            doc["status"] = RunnerLifecycleStatus.error.value
            doc["updated_at"] = datetime.now(UTC)
            doc["error"] = type(exc).__name__
            raise CloudProviderError(
                "provision_failed",
                "Remote provision failed — retry after quote; check provider status",
            ) from exc

        doc["provider_instance_id"] = remote["instance_id"]
        doc["status"] = RunnerLifecycleStatus.online.value
        doc["updated_at"] = datetime.now(UTC)
        # Reserve 1hr at launch; stop/terminate accrues extra elapsed hours.
        self._add_usage(quote.cost_estimate_micros_hr)
        self._emit_outbox(
            "cloud.runner.launched",
            {
                "runner_id": runner_id,
                "provider": provider,
                "gpu_type": quote.gpu_type,
                "cost_estimate_micros_hr": quote.cost_estimate_micros_hr,
                "provider_instance_id": remote["instance_id"],
            },
        )
        return self._runner_response(doc)

    def _emit_outbox(self, event_type: str, payload: dict[str, Any]) -> None:
        """Side-effect audit: memory outbox always; Mongo when wired by caller."""
        from mymlfw.saas.control_plane import enqueue_memory_outbox

        enqueue_memory_outbox(
            event_type=event_type,
            payload=payload,
            workspace_id=self.org_id,
        )

    def _add_usage(self, micros: int) -> None:
        self.store.usage_micros_today[self.org_id] = (
            int(self.store.usage_micros_today.get(self.org_id, 0)) + int(micros)
        )

    def _accrue_elapsed_beyond_reserve(self, doc: dict[str, Any]) -> None:
        """Charge additional full hours beyond the 1hr launch reserve."""
        created = doc.get("created_at")
        if not isinstance(created, datetime):
            return
        rate = int(doc.get("cost_estimate_micros_hr") or 0)
        if rate <= 0:
            return
        elapsed_hours = max(
            0.0, (datetime.now(UTC) - created).total_seconds() / 3600.0
        )
        extra = max(0, int(math.ceil(elapsed_hours)) - 1)
        if extra:
            self._add_usage(extra * rate)

    def stop(self, runner_id: str) -> RunnerResponse:
        self.require_flag()
        doc = self._get_runner(runner_id)
        instance_id = doc.get("provider_instance_id")
        if not instance_id:
            # Failed / stuck provisioning rows can be locally stopped without remote.
            if doc.get("status") in {
                RunnerLifecycleStatus.error.value,
                RunnerLifecycleStatus.provisioning.value,
            }:
                doc["status"] = RunnerLifecycleStatus.stopped.value
                doc["updated_at"] = datetime.now(UTC)
                return self._runner_response(doc)
            raise CloudProviderError("no_instance", "Runner has no provider instance")
        provider = doc["provider"]
        if provider == "runpod":
            self._runpod_client(self._runpod_api_key(doc["account_id"])).stop(
                instance_id=instance_id
            )
        else:
            account = self.store.accounts[doc["account_id"]]
            self._aws_client(
                role_arn=account["role_arn"],
                external_id=account["external_id"],
                region=account.get("region") or "us-east-1",
            ).stop(instance_id=instance_id)
        self._accrue_elapsed_beyond_reserve(doc)
        doc["status"] = RunnerLifecycleStatus.stopped.value
        doc["updated_at"] = datetime.now(UTC)
        return self._runner_response(doc)

    def terminate(self, runner_id: str) -> RunnerResponse:
        self.require_flag()
        doc = self._get_runner(runner_id)
        instance_id = doc.get("provider_instance_id")
        provider = doc.get("provider")
        if instance_id and provider:
            try:
                if provider == "runpod":
                    self._runpod_client(self._runpod_api_key(doc["account_id"])).terminate(
                        instance_id=instance_id
                    )
                else:
                    account = self.store.accounts[doc["account_id"]]
                    self._aws_client(
                        role_arn=account["role_arn"],
                        external_id=account["external_id"],
                        region=account.get("region") or "us-east-1",
                    ).terminate(instance_id=instance_id)
            except KeyError:
                pass
        if doc.get("status") not in {
            RunnerLifecycleStatus.error.value,
            RunnerLifecycleStatus.provisioning.value,
        }:
            self._accrue_elapsed_beyond_reserve(doc)
        doc["status"] = RunnerLifecycleStatus.terminated.value
        doc["updated_at"] = datetime.now(UTC)
        doc["deleted_at"] = datetime.now(UTC)
        return self._runner_response(doc)

    def list_runners(self) -> list[RunnerResponse]:
        # Read-only: local BYOC runners list without cloud_runners; cloud kinds
        # still appear only when the org has connected providers (flag for mutators).
        rows = [
            r
            for r in self.store.runners.values()
            if r.get("org_id") == self.org_id
            and r.get("deleted_at") is None
            and r.get("status") != RunnerLifecycleStatus.error.value
        ]
        if not self.feature_flags.cloud_runners:
            rows = [r for r in rows if r.get("kind") == RunnerKind.local.value]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [self._runner_response(r) for r in rows]

    def sweep_orphans(self) -> dict[str, Any]:
        """Terminate remotes tagged for this org that are unprotected.

        Protected = online/starting/stopped/stopping with a live row.
        ``provisioning`` / ``error`` rows do NOT protect remotes (saga crash window).
        Intended cadence: every 15 minutes from the worker.
        """
        self.require_flag()
        protected_statuses = {
            RunnerLifecycleStatus.online.value,
            RunnerLifecycleStatus.starting.value,
            RunnerLifecycleStatus.stopped.value,
            RunnerLifecycleStatus.stopping.value,
            RunnerLifecycleStatus.terminating.value,
        }
        protected_ids = {
            r["_id"]
            for r in self.store.runners.values()
            if r.get("org_id") == self.org_id
            and r.get("deleted_at") is None
            and r.get("status") in protected_statuses
        }
        # Also terminate remotes for stale failed local rows, then soft-delete them.
        stale_rows = [
            r
            for r in self.store.runners.values()
            if r.get("org_id") == self.org_id
            and r.get("deleted_at") is None
            and r.get("status")
            in {
                RunnerLifecycleStatus.provisioning.value,
                RunnerLifecycleStatus.error.value,
            }
        ]
        terminated: list[dict[str, str]] = []
        for provider in ("runpod", "aws"):
            account = self.store.account_for(self.org_id, provider)
            if account is None or account.get("status") != "connected":
                continue
            client = self._client_for(provider)
            for remote in client.list_orphans_candidates(org_id=self.org_id):
                tags = remote.get("tags") or {}
                runner_id = tags.get("mymlfw_runner_id")
                if runner_id and runner_id in protected_ids:
                    continue
                instance_id = remote["instance_id"]
                try:
                    client.terminate(instance_id=instance_id)
                except KeyError:
                    continue
                terminated.append(
                    {
                        "provider": provider,
                        "instance_id": instance_id,
                        "runner_id": str(runner_id or ""),
                    }
                )
        for row in stale_rows:
            row["status"] = RunnerLifecycleStatus.terminated.value
            row["updated_at"] = datetime.now(UTC)
            row["deleted_at"] = datetime.now(UTC)
        return {
            "interval_minutes": int(ORPHAN_SWEEPER_INTERVAL.total_seconds() // 60),
            "terminated": terminated,
            "stale_rows_closed": len(stale_rows),
            "swept_at": datetime.now(UTC).isoformat(),
        }

    def _get_runner(self, runner_id: str) -> dict[str, Any]:
        doc = self.store.runners.get(runner_id)
        if doc is None or doc.get("org_id") != self.org_id:
            raise CloudProviderError("runner_not_found", f"Unknown runner {runner_id}")
        return doc

    def _runpod_api_key(self, account_id: str) -> str:
        blob = self.store.secrets.get(account_id)
        if blob is None:
            raise CloudProviderError("missing_secret", "RunPod API key not sealed")
        return open_secret(blob).decode("utf-8")

    def _runpod_client(self, api_key: str) -> RunPodClient:
        # Cache transport so create → stop share state. Live when the user
        # sealed a key (unless MYMLFW_CLOUD_MOCK=1 / pytest).
        from mymlfw.saas.providers.mode import use_cloud_mock
        from mymlfw.saas.providers.runpod import LiveRunPodTransport

        if use_cloud_mock():
            if self.runpod_transport is None:
                self.runpod_transport = MockRunPodTransport()
        elif (
            self.runpod_transport is None
            or not isinstance(self.runpod_transport, LiveRunPodTransport)
            or getattr(self.runpod_transport, "api_key", None) != api_key
        ):
            self.runpod_transport = LiveRunPodTransport(api_key=api_key)
        return RunPodClient(api_key=api_key, transport=self.runpod_transport)

    def _aws_client(
        self, *, role_arn: str, external_id: str, region: str
    ) -> AwsClient:
        from mymlfw.saas.providers.aws import LiveAwsTransport
        from mymlfw.saas.providers.mode import use_cloud_mock

        if use_cloud_mock():
            if self.aws_transport is None:
                self.aws_transport = MockAwsTransport()
        elif (
            self.aws_transport is None
            or not isinstance(self.aws_transport, LiveAwsTransport)
            or getattr(self.aws_transport, "role_arn", None) != role_arn
            or getattr(self.aws_transport, "external_id", None) != external_id
            or getattr(self.aws_transport, "region", None) != region
        ):
            self.aws_transport = LiveAwsTransport(
                role_arn=role_arn, external_id=external_id, region=region
            )
        return AwsClient(
            role_arn=role_arn,
            external_id=external_id,
            region=region,
            transport=self.aws_transport,
        )

    def _client_for(self, provider: ProviderName) -> RunPodClient | AwsClient:
        account = self.store.account_for(self.org_id, provider)
        if account is None or account.get("status") != "connected":
            raise CloudProviderError("not_connected", f"Connect {provider} first")
        if provider == "runpod":
            return self._runpod_client(self._runpod_api_key(account["_id"]))
        return self._aws_client(
            role_arn=account["role_arn"],
            external_id=account["external_id"],
            region=account.get("region") or "us-east-1",
        )


def dead_man_bootstrap(*, idle_timeout_minutes: int = DEFAULT_IDLE_TIMEOUT_MINUTES) -> dict[str, Any]:
    """Runner image dead-man: self-stop if API unreachable and idle past timeout."""
    return {
        "enabled": True,
        "idle_timeout_minutes": idle_timeout_minutes,
        "on_api_unreachable": "self_stop",
        "ec2_terminate_on_shutdown": True,
        "runpod_stop_hook": True,
        "token_kind": "job_scoped",
        "job_token_ttl_hours": 2,
        "note": (
            "Survives control-plane crash: runner self-stops without waiting "
            "for orchestrator orphan sweeper"
        ),
    }


def pick_runner_auto(
    runners: list[dict[str, Any] | RunnerResponse],
    *,
    prefer_gpu: bool = True,
    min_vram_gb: int = 0,
) -> dict[str, Any] | None:
    """Job ``auto`` picker: ready local → else cheapest fitting cloud GPU."""
    rows: list[dict[str, Any]] = []
    for r in runners:
        if isinstance(r, RunnerResponse):
            rows.append(r.model_dump())
        else:
            rows.append(r)

    def _status(row: dict[str, Any]) -> str:
        s = row.get("status")
        return s.value if hasattr(s, "value") else str(s or "")

    def _kind(row: dict[str, Any]) -> str:
        k = row.get("kind")
        return k.value if hasattr(k, "value") else str(k or "")

    ready = [
        r
        for r in rows
        if _status(r) in {"online", "idle", "ready"}
        and r.get("deleted_at") is None
    ]
    locals_ready = [r for r in ready if _kind(r) == RunnerKind.local.value]
    if locals_ready:
        return dict(locals_ready[0])

    if not prefer_gpu:
        return dict(ready[0]) if ready else None

    cloud = [
        r
        for r in ready
        if _kind(r)
        in {
            RunnerKind.runpod_pod.value,
            RunnerKind.runpod_serverless.value,
            RunnerKind.aws_ec2.value,
        }
    ]
    if min_vram_gb:
        cloud = [r for r in cloud if int(r.get("vram_gb") or 0) >= min_vram_gb]
    if not cloud:
        return None
    cloud.sort(key=lambda r: int(r.get("cost_estimate_micros_hr") or 0))
    return dict(cloud[0])


def mint_short_lived_runner_token() -> tuple[str, bytes]:
    """Short-lived bootstrap token hashed at rest (SHA-256)."""
    import hashlib

    raw = f"rtn_{secrets.token_urlsafe(32)}"
    return raw, hashlib.sha256(raw.encode("utf-8")).digest()


def default_cloud_service(
    *,
    org_id: str,
    cloud_runners: bool = True,
    max_cloud_micros_day: int = 10_000_000,
    store: InMemoryCloudStore | None = None,
) -> CloudProviderService:
    from mymlfw.saas.providers.mode import use_cloud_mock

    mock = use_cloud_mock()
    return CloudProviderService(
        org_id=org_id,
        store=store or InMemoryCloudStore(),
        feature_flags=FeatureFlags(cloud_runners=cloud_runners),
        entitlements=OrgEntitlements(max_cloud_micros_day=max_cloud_micros_day),
        runpod_transport=MockRunPodTransport() if mock else None,
        aws_transport=MockAwsTransport() if mock else None,
    )
