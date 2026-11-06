"""RunPod provider adapter — live REST when the user seals an API key; mock for CI."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from mymlfw.saas.ids import new_prefixed_id

DEFAULT_RUNNER_IMAGE = os.environ.get(
    "MYMLFW_RUNNER_IMAGE",
    "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
)
RUNPOD_REST_BASE = os.environ.get(
    "MYMLFW_RUNPOD_API_BASE", "https://rest.runpod.io/v1"
).rstrip("/")


class RunPodTransport(Protocol):
    def list_gpus(self) -> list[dict[str, Any]]: ...

    def create_pod(self, *, spec: dict[str, Any]) -> dict[str, Any]: ...

    def stop_pod(self, *, instance_id: str) -> dict[str, Any]: ...

    def terminate_pod(self, *, instance_id: str) -> dict[str, Any]: ...

    def list_tagged_pods(self, *, org_id: str) -> list[dict[str, Any]]: ...


# Catalog micros/hr (USD * 1e6). CI/unit tests never hit the live API.
MOCK_GPU_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "gpu_type": "NVIDIA GeForce RTX 4090",
        "gpu_id": "NVIDIA GeForce RTX 4090",
        "stock": 12,
        "cost_estimate_micros_hr": 440_000,
        "region": "EU-RO-1",
        "vram_gb": 24,
    },
    {
        "gpu_type": "NVIDIA A100 80GB",
        "gpu_id": "NVIDIA A100 80GB PCIe",
        "stock": 3,
        "cost_estimate_micros_hr": 1_890_000,
        "region": "US-OR-1",
        "vram_gb": 80,
    },
    {
        "gpu_type": "NVIDIA H100 80GB",
        "gpu_id": "NVIDIA H100 80GB HBM3",
        "stock": 1,
        "cost_estimate_micros_hr": 3_390_000,
        "region": "US-CA-2",
        "vram_gb": 80,
    },
)


@dataclass
class MockRunPodTransport:
    """In-memory RunPod stand-in used by pytest (zero cloud spend)."""

    pods: dict[str, dict[str, Any]] = field(default_factory=dict)
    catalog: tuple[dict[str, Any], ...] = MOCK_GPU_CATALOG
    fail_create: bool = False

    def list_gpus(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.catalog]

    def create_pod(self, *, spec: dict[str, Any]) -> dict[str, Any]:
        if self.fail_create:
            raise RuntimeError("runpod_create_failed")
        instance_id = f"rp_{new_prefixed_id('job')[4:]}"
        row = {
            "instance_id": instance_id,
            "status": "RUNNING",
            "tags": dict(spec.get("tags") or {}),
            "gpu_type": spec.get("gpu_type"),
            "cost_estimate_micros_hr": int(spec.get("cost_estimate_micros_hr") or 0),
        }
        self.pods[instance_id] = row
        return dict(row)

    def stop_pod(self, *, instance_id: str) -> dict[str, Any]:
        row = self.pods.get(instance_id)
        if row is None:
            raise KeyError(instance_id)
        row["status"] = "EXITED"
        return dict(row)

    def terminate_pod(self, *, instance_id: str) -> dict[str, Any]:
        row = self.pods.pop(instance_id, None)
        if row is None:
            raise KeyError(instance_id)
        row["status"] = "TERMINATED"
        return dict(row)

    def list_tagged_pods(self, *, org_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in self.pods.values():
            tags = row.get("tags") or {}
            if tags.get("mymlfw_org_id") == org_id:
                out.append(dict(row))
        return out


def _usd_to_micros(usd: Any) -> int:
    try:
        return max(0, int(round(float(usd) * 1_000_000)))
    except (TypeError, ValueError):
        return 0


@dataclass
class LiveRunPodTransport:
    """Live RunPod REST using the sealed user API key (billable)."""

    api_key: str
    base_url: str = RUNPOD_REST_BASE
    timeout_s: float = 60.0

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"runpod_http_{exc.code}:{detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"runpod_unreachable:{exc}") from exc

    def list_gpus(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/gpuTypes")
        rows = payload if isinstance(payload, list) else payload.get("data") or payload.get("gpuTypes") or []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            gpu_id = str(row.get("id") or row.get("gpuTypeId") or row.get("displayName") or "")
            if not gpu_id:
                continue
            price = (
                row.get("securePrice")
                or row.get("communityPrice")
                or row.get("lowestPrice")
                or row.get("price")
                or 0
            )
            if isinstance(price, dict):
                price = price.get("minimum") or price.get("uninterruptible") or 0
            stock = row.get("secureStock") or row.get("communityStock") or row.get("stock") or row.get("count")
            if stock is None:
                stock = 1 if price else 0
            out.append(
                {
                    "gpu_type": gpu_id,
                    "gpu_id": gpu_id,
                    "stock": int(stock),
                    "cost_estimate_micros_hr": _usd_to_micros(price),
                    "region": str(row.get("dataCenterId") or row.get("region") or ""),
                    "vram_gb": int(row.get("memoryInGb") or row.get("vram_gb") or 0),
                    "spot_ok": bool(row.get("communityPrice") is not None),
                }
            )
        if not out:
            raise RuntimeError("runpod_empty_gpu_catalog: check API key scopes")
        return out

    def create_pod(self, *, spec: dict[str, Any]) -> dict[str, Any]:
        tags = dict(spec.get("tags") or {})
        gpu_type = str(spec.get("gpu_type") or "")
        image = str(spec.get("image") or DEFAULT_RUNNER_IMAGE)
        name = f"mymlfw-{tags.get('mymlfw_runner_id') or spec.get('client_token') or 'runner'}"[:60]
        body: dict[str, Any] = {
            "name": name,
            "imageName": image,
            "gpuTypeIds": [gpu_type],
            "gpuCount": 1,
            "cloudType": "SECURE",
            "computeType": "GPU",
            "containerDiskInGb": int(os.environ.get("MYMLFW_RUNPOD_DISK_GB", "50")),
            "volumeInGb": int(os.environ.get("MYMLFW_RUNPOD_VOLUME_GB", "20")),
            "ports": ["22/tcp", "8888/http"],
            "env": {
                "MYMLFW_RUNNER_ID": str(tags.get("mymlfw_runner_id") or ""),
                "MYMLFW_ORG_ID": str(tags.get("mymlfw_org_id") or ""),
                "MYMLFW_CLIENT_TOKEN": str(spec.get("client_token") or ""),
            },
        }
        idle = int(spec.get("idle_timeout_minutes") or 0)
        if idle > 0:
            # Best-effort hint for templates that honor idle shutdown.
            body["env"]["MYMLFW_IDLE_TIMEOUT_MINUTES"] = str(idle)
        payload = self._request("POST", "/pods", body=body)
        instance_id = str(
            payload.get("id")
            or payload.get("podId")
            or (payload.get("pod") or {}).get("id")
            or ""
        )
        if not instance_id:
            raise RuntimeError(f"runpod_create_missing_id:{payload!r}"[:300])
        return {
            "instance_id": instance_id,
            "status": str(payload.get("desiredStatus") or payload.get("status") or "RUNNING"),
            "tags": tags,
            "gpu_type": gpu_type,
            "cost_estimate_micros_hr": int(spec.get("cost_estimate_micros_hr") or 0),
            "raw": {"id": instance_id},
        }

    def stop_pod(self, *, instance_id: str) -> dict[str, Any]:
        payload = self._request("POST", f"/pods/{instance_id}/stop")
        return {"instance_id": instance_id, "status": "EXITED", "raw": payload}

    def terminate_pod(self, *, instance_id: str) -> dict[str, Any]:
        payload = self._request("DELETE", f"/pods/{instance_id}")
        return {"instance_id": instance_id, "status": "TERMINATED", "raw": payload}

    def list_tagged_pods(self, *, org_id: str) -> list[dict[str, Any]]:
        payload = self._request("GET", "/pods")
        rows = payload if isinstance(payload, list) else payload.get("pods") or payload.get("data") or []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            env = row.get("env") or {}
            tags = {
                "mymlfw_org_id": env.get("MYMLFW_ORG_ID") or "",
                "mymlfw_runner_id": env.get("MYMLFW_RUNNER_ID") or "",
            }
            if tags["mymlfw_org_id"] and tags["mymlfw_org_id"] != org_id:
                continue
            # Include pods we tagged for this org, or untagged orphans we cannot attribute
            # only when env matches; skip foreign orgs.
            if tags["mymlfw_org_id"] == org_id or (
                not tags["mymlfw_org_id"] and env.get("MYMLFW_CLIENT_TOKEN")
            ):
                out.append(
                    {
                        "instance_id": str(row.get("id") or ""),
                        "status": str(row.get("desiredStatus") or row.get("status") or ""),
                        "tags": tags,
                    }
                )
        return [r for r in out if r["instance_id"]]


@dataclass
class RunPodClient:
    """Thin RunPod facade. Inject ``transport`` in tests; live uses sealed API key."""

    api_key: str
    transport: RunPodTransport | None = None
    _http_factory: Callable[[], RunPodTransport] | None = None

    def __post_init__(self) -> None:
        if self.transport is None:
            from mymlfw.saas.providers.mode import use_cloud_mock

            if use_cloud_mock():
                self.transport = MockRunPodTransport()
            else:
                self.transport = LiveRunPodTransport(api_key=self.api_key)

    def list_gpus(self) -> list[dict[str, Any]]:
        assert self.transport is not None
        return self.transport.list_gpus()

    def cost_estimate_micros_hr(self, gpu_type: str) -> int:
        for row in self.list_gpus():
            if row["gpu_type"] == gpu_type or row.get("gpu_id") == gpu_type:
                return int(row["cost_estimate_micros_hr"])
        raise KeyError(f"unknown_gpu_type:{gpu_type}")

    def create(
        self,
        *,
        runner_id: str,
        org_id: str,
        gpu_type: str,
        cost_estimate_micros_hr: int,
        idle_timeout_minutes: int = 30,
        image: str | None = None,
    ) -> dict[str, Any]:
        assert self.transport is not None
        return self.transport.create_pod(
            spec={
                "gpu_type": gpu_type,
                "cost_estimate_micros_hr": cost_estimate_micros_hr,
                "idle_timeout_minutes": idle_timeout_minutes,
                "image": image or DEFAULT_RUNNER_IMAGE,
                "tags": {
                    "mymlfw_runner_id": runner_id,
                    "mymlfw_org_id": org_id,
                },
                "client_token": runner_id,
            }
        )

    def stop(self, *, instance_id: str) -> dict[str, Any]:
        assert self.transport is not None
        return self.transport.stop_pod(instance_id=instance_id)

    def terminate(self, *, instance_id: str) -> dict[str, Any]:
        assert self.transport is not None
        return self.transport.terminate_pod(instance_id=instance_id)

    def list_orphans_candidates(self, *, org_id: str) -> list[dict[str, Any]]:
        assert self.transport is not None
        return self.transport.list_tagged_pods(org_id=org_id)
