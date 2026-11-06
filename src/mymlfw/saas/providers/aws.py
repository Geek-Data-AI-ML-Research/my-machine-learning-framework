"""AWS EC2 GPU provider — ExternalId + IMDSv2 hop=1; mockable for CI."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any, Protocol

from mymlfw.saas.ids import new_prefixed_id

# Locked GPU families for CFN/TF allowlist (no Admin PassRole).
AWS_GPU_FAMILY_ALLOWLIST: frozenset[str] = frozenset(
    {"g5", "g6", "p4d", "p4de", "p5", "p5e"}
)

IMDSV2_METADATA_OPTIONS: dict[str, Any] = {
    "HttpTokens": "required",
    "HttpPutResponseHopLimit": 1,
    "HttpEndpoint": "enabled",
}


class AwsTransport(Protocol):
    def list_gpus(self) -> list[dict[str, Any]]: ...

    def run_instances(self, *, spec: dict[str, Any]) -> dict[str, Any]: ...

    def stop_instances(self, *, instance_id: str) -> dict[str, Any]: ...

    def terminate_instances(self, *, instance_id: str) -> dict[str, Any]: ...

    def list_tagged_instances(self, *, org_id: str) -> list[dict[str, Any]]: ...


MOCK_AWS_GPU_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "gpu_type": "g5.xlarge",
        "gpu_id": "g5.xlarge",
        "family": "g5",
        "stock": 8,
        "cost_estimate_micros_hr": 1_006_000,
        "region": "us-east-1",
        "vram_gb": 24,
        "spot_ok": True,
    },
    {
        "gpu_type": "g5.2xlarge",
        "gpu_id": "g5.2xlarge",
        "family": "g5",
        "stock": 4,
        "cost_estimate_micros_hr": 1_212_000,
        "region": "us-east-1",
        "vram_gb": 24,
        "spot_ok": True,
    },
    {
        "gpu_type": "p4d.24xlarge",
        "gpu_id": "p4d.24xlarge",
        "family": "p4d",
        "stock": 0,
        "cost_estimate_micros_hr": 32_772_600,
        "region": "us-west-2",
        "vram_gb": 320,
        "spot_ok": True,
    },
)


def generate_external_id() -> str:
    """Server-generated ExternalId — immutable by the user after connect."""
    return f"mymlfw-{secrets.token_urlsafe(24)}"


@dataclass
class MockAwsTransport:
    """In-memory EC2 stand-in (pytest / CI)."""

    instances: dict[str, dict[str, Any]] = field(default_factory=dict)
    catalog: tuple[dict[str, Any], ...] = MOCK_AWS_GPU_CATALOG
    fail_create: bool = False

    def list_gpus(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.catalog]

    def run_instances(self, *, spec: dict[str, Any]) -> dict[str, Any]:
        if self.fail_create:
            raise RuntimeError("aws_run_instances_failed")
        family = str(spec.get("family") or "")
        if family and family not in AWS_GPU_FAMILY_ALLOWLIST:
            raise ValueError(f"gpu_family_denied:{family}")
        instance_id = f"i-{new_prefixed_id('job')[4:16].lower()}"
        row = {
            "instance_id": instance_id,
            "status": "running",
            "tags": dict(spec.get("tags") or {}),
            "gpu_type": spec.get("gpu_type"),
            "client_token": spec.get("client_token"),
            "metadata_options": dict(spec.get("metadata_options") or IMDSV2_METADATA_OPTIONS),
            "cost_estimate_micros_hr": int(spec.get("cost_estimate_micros_hr") or 0),
            "spot": bool(spec.get("spot")),
        }
        self.instances[instance_id] = row
        return dict(row)

    def stop_instances(self, *, instance_id: str) -> dict[str, Any]:
        row = self.instances.get(instance_id)
        if row is None:
            raise KeyError(instance_id)
        row["status"] = "stopped"
        return dict(row)

    def terminate_instances(self, *, instance_id: str) -> dict[str, Any]:
        row = self.instances.pop(instance_id, None)
        if row is None:
            raise KeyError(instance_id)
        row["status"] = "terminated"
        return dict(row)

    def list_tagged_instances(self, *, org_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in self.instances.values():
            tags = row.get("tags") or {}
            if tags.get("mymlfw_org_id") == org_id:
                out.append(dict(row))
        return out


@dataclass
class LiveAwsTransport:
    """Live EC2 via STS AssumeRole + ExternalId (billable). Requires boto3."""

    role_arn: str
    external_id: str
    region: str = "us-east-1"
    session_name: str = "mymlfw-runner"

    def _ec2(self) -> Any:
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "pip install boto3 to launch AWS runners with a connected role ARN"
            ) from exc
        sts = boto3.client("sts", region_name=self.region)
        assumed = sts.assume_role(
            RoleArn=self.role_arn,
            RoleSessionName=self.session_name[:64],
            ExternalId=self.external_id,
            DurationSeconds=3600,
        )
        creds = assumed["Credentials"]
        return boto3.client(
            "ec2",
            region_name=self.region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )

    def list_gpus(self) -> list[dict[str, Any]]:
        # Price book from allowlist; stock probed via DescribeInstanceTypeOfferings.
        ec2 = self._ec2()
        out: list[dict[str, Any]] = []
        for row in MOCK_AWS_GPU_CATALOG:
            family = str(row["family"])
            if family not in AWS_GPU_FAMILY_ALLOWLIST:
                continue
            stock = int(row["stock"])
            try:
                resp = ec2.describe_instance_type_offerings(
                    LocationType="availability-zone",
                    Filters=[
                        {"Name": "instance-type", "Values": [row["gpu_type"]]},
                    ],
                )
                stock = len(resp.get("InstanceTypeOfferings") or []) or stock
            except Exception:  # noqa: BLE001 — fall back to catalog stock
                pass
            item = dict(row)
            item["stock"] = stock
            item["region"] = self.region
            out.append(item)
        return out

    def run_instances(self, *, spec: dict[str, Any]) -> dict[str, Any]:
        import os

        family = str(spec.get("family") or "")
        if family and family not in AWS_GPU_FAMILY_ALLOWLIST:
            raise ValueError(f"gpu_family_denied:{family}")
        ami = os.environ.get("MYMLFW_AWS_AMI_ID", "").strip()
        if not ami:
            raise RuntimeError(
                "Set MYMLFW_AWS_AMI_ID to a GPU AMI in the connected account/region "
                "before launching AWS runners"
            )
        subnet = os.environ.get("MYMLFW_AWS_SUBNET_ID", "").strip() or None
        sg = os.environ.get("MYMLFW_AWS_SECURITY_GROUP_ID", "").strip()
        security_groups = [sg] if sg else None
        tags = dict(spec.get("tags") or {})
        client_token = str(spec.get("client_token") or new_prefixed_id("job"))
        market: dict[str, Any] | None = None
        if bool(spec.get("spot")):
            market = {
                "MarketType": "spot",
                "SpotOptions": {
                    "SpotInstanceType": "one-time",
                    "InstanceInterruptionBehavior": "terminate",
                },
            }
        kwargs: dict[str, Any] = {
            "ImageId": ami,
            "InstanceType": str(spec.get("gpu_type")),
            "MinCount": 1,
            "MaxCount": 1,
            "ClientToken": client_token[:64],
            "MetadataOptions": dict(spec.get("metadata_options") or IMDSV2_METADATA_OPTIONS),
            "TagSpecifications": [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "mymlfw_runner_id", "Value": str(tags.get("mymlfw_runner_id") or "")},
                        {"Key": "mymlfw_org_id", "Value": str(tags.get("mymlfw_org_id") or "")},
                        {"Key": "Name", "Value": f"mymlfw-{tags.get('mymlfw_runner_id') or client_token}"[:60]},
                    ],
                }
            ],
        }
        if subnet:
            kwargs["SubnetId"] = subnet
        if security_groups:
            kwargs["SecurityGroupIds"] = security_groups
        if market:
            kwargs["InstanceMarketOptions"] = market
        resp = self._ec2().run_instances(**kwargs)
        inst = (resp.get("Instances") or [None])[0]
        if not inst:
            raise RuntimeError("aws_run_instances_empty")
        instance_id = str(inst["InstanceId"])
        return {
            "instance_id": instance_id,
            "status": str(inst.get("State", {}).get("Name") or "pending"),
            "tags": tags,
            "gpu_type": spec.get("gpu_type"),
            "client_token": client_token,
            "metadata_options": kwargs["MetadataOptions"],
            "cost_estimate_micros_hr": int(spec.get("cost_estimate_micros_hr") or 0),
            "spot": bool(spec.get("spot")),
        }

    def stop_instances(self, *, instance_id: str) -> dict[str, Any]:
        self._ec2().stop_instances(InstanceIds=[instance_id])
        return {"instance_id": instance_id, "status": "stopped"}

    def terminate_instances(self, *, instance_id: str) -> dict[str, Any]:
        self._ec2().terminate_instances(InstanceIds=[instance_id])
        return {"instance_id": instance_id, "status": "terminated"}

    def list_tagged_instances(self, *, org_id: str) -> list[dict[str, Any]]:
        resp = self._ec2().describe_instances(
            Filters=[
                {"Name": "tag:mymlfw_org_id", "Values": [org_id]},
                {
                    "Name": "instance-state-name",
                    "Values": ["pending", "running", "stopping", "stopped"],
                },
            ]
        )
        out: list[dict[str, Any]] = []
        for reservation in resp.get("Reservations") or []:
            for inst in reservation.get("Instances") or []:
                tag_map = {
                    t["Key"]: t["Value"] for t in (inst.get("Tags") or []) if "Key" in t
                }
                out.append(
                    {
                        "instance_id": str(inst["InstanceId"]),
                        "status": str((inst.get("State") or {}).get("Name") or ""),
                        "tags": {
                            "mymlfw_org_id": tag_map.get("mymlfw_org_id", org_id),
                            "mymlfw_runner_id": tag_map.get("mymlfw_runner_id", ""),
                        },
                    }
                )
        return out


@dataclass
class AwsClient:
    """Assume-role style client. Credentials = role_arn + server ExternalId."""

    role_arn: str
    external_id: str
    region: str = "us-east-1"
    transport: AwsTransport | None = None

    def __post_init__(self) -> None:
        if self.transport is None:
            from mymlfw.saas.providers.mode import use_cloud_mock

            if use_cloud_mock():
                self.transport = MockAwsTransport()
            else:
                self.transport = LiveAwsTransport(
                    role_arn=self.role_arn,
                    external_id=self.external_id,
                    region=self.region,
                )

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
        spot: bool = True,
    ) -> dict[str, Any]:
        assert self.transport is not None
        family = gpu_type.split(".", 1)[0]
        if family not in AWS_GPU_FAMILY_ALLOWLIST:
            raise ValueError(f"gpu_family_denied:{family}")
        return self.transport.run_instances(
            spec={
                "gpu_type": gpu_type,
                "family": family,
                "cost_estimate_micros_hr": cost_estimate_micros_hr,
                "idle_timeout_minutes": idle_timeout_minutes,
                "spot": spot,
                "role_arn": self.role_arn,
                "external_id": self.external_id,
                "region": self.region,
                # Two-phase saga correlation — EC2 ClientToken == runner_ulid.
                "client_token": runner_id,
                "metadata_options": IMDSV2_METADATA_OPTIONS,
                "tags": {
                    "mymlfw_runner_id": runner_id,
                    "mymlfw_org_id": org_id,
                },
            }
        )

    def stop(self, *, instance_id: str) -> dict[str, Any]:
        assert self.transport is not None
        return self.transport.stop_instances(instance_id=instance_id)

    def terminate(self, *, instance_id: str) -> dict[str, Any]:
        assert self.transport is not None
        return self.transport.terminate_instances(instance_id=instance_id)

    def list_orphans_candidates(self, *, org_id: str) -> list[dict[str, Any]]:
        assert self.transport is not None
        return self.transport.list_tagged_instances(org_id=org_id)

    def spot_requeue_policy(self) -> dict[str, Any]:
        """Spot 2m notice → checkpoint + requeue without infra strike."""
        return {
            "poll_instance_action_seconds": 5,
            "notice_window_seconds": 120,
            "on_preempt": "spot_preempted_requeue",
            "infra_strike": False,
        }
