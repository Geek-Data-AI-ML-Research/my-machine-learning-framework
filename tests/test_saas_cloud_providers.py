"""Cloud providers (RunPod + AWS) behind ``cloud_runners`` — mocked, no spend."""

from __future__ import annotations

import json
import os

import pytest

pydantic = pytest.importorskip("pydantic")


@pytest.fixture()
def org_id() -> str:
    return "org_01HCLOUDTESTORG00000000000"


def test_envelope_seal_open_roundtrip():
    from mymlfw.saas.secrets import open_secret, seal_secret

    blob = seal_secret("rp_secret_key_value")
    assert blob.kek_version >= 1
    assert blob.ciphertext != b"rp_secret_key_value"
    assert open_secret(blob).decode() == "rp_secret_key_value"
    meta = blob.public_meta()
    assert "ciphertext" not in meta
    assert meta["kek_version"] == blob.kek_version


def test_connect_runpod_and_aws_external_id_immutable(org_id: str):
    from mymlfw.saas.providers import default_cloud_service

    svc = default_cloud_service(org_id=org_id, cloud_runners=True)
    rp = svc.connect_runpod(api_key="runpod-test-key-xxxxxx")
    assert rp.provider.value == "runpod"
    assert rp.has_credentials is True
    assert rp.kek_version == 1
    assert rp.external_id is None

    aws = svc.connect_aws(role_arn="arn:aws:iam::123456789012:role/mymlfw-runner")
    assert aws.provider.value == "aws"
    assert aws.external_id and aws.external_id.startswith("mymlfw-")
    ext = aws.external_id

    # Reconnect keeps the same ExternalId (user cannot edit / rotate via API).
    aws2 = svc.connect_aws(
        role_arn="arn:aws:iam::123456789012:role/mymlfw-runner-v2",
        region="us-west-2",
    )
    assert aws2.external_id == ext
    assert aws2.role_arn.endswith("mymlfw-runner-v2")


def test_feature_flag_blocks_connect(org_id: str):
    from mymlfw.saas.providers import CloudProviderError, default_cloud_service

    svc = default_cloud_service(org_id=org_id, cloud_runners=False)
    with pytest.raises(CloudProviderError) as exc:
        svc.connect_runpod(api_key="runpod-test-key-xxxxxx")
    assert exc.value.code == "feature_disabled"


def test_quote_required_before_launch_and_saga(org_id: str):
    from mymlfw.saas.providers import CloudProviderError, default_cloud_service
    from mymlfw.saas.schemas import RunnerLifecycleStatus

    svc = default_cloud_service(org_id=org_id, cloud_runners=True)
    svc.connect_runpod(api_key="runpod-test-key-xxxxxx")
    offers = svc.list_gpus("runpod")
    assert offers
    gpu = offers[0].gpu_type
    quote = svc.quote_launch(provider="runpod", gpu_type=gpu)
    assert quote.cost_estimate_micros_hr > 0

    with pytest.raises(CloudProviderError) as missing:
        svc.launch(provider="runpod", gpu_type=gpu, quote_accepted_micros_hr=None)
    assert missing.value.code == "quote_required"

    with pytest.raises(CloudProviderError) as mismatch:
        svc.launch(
            provider="runpod",
            gpu_type=gpu,
            quote_accepted_micros_hr=quote.cost_estimate_micros_hr + 1,
        )
    assert mismatch.value.code == "quote_mismatch"

    runner = svc.launch(
        provider="runpod",
        gpu_type=gpu,
        quote_accepted_micros_hr=quote.cost_estimate_micros_hr,
    )
    assert runner.status == RunnerLifecycleStatus.online
    assert runner.provider_instance_id
    assert runner.cost_estimate_micros_hr == quote.cost_estimate_micros_hr
    # Saga left a Mongo/in-memory row keyed by runner_ulid.
    assert runner.runner_id in svc.store.runners
    row = svc.store.runners[runner.runner_id]
    assert row["status"] == "online"
    assert row["dead_man"]["enabled"] is True

    # Provider tags used for orphan correlation.
    remote = svc.runpod_transport.pods[runner.provider_instance_id]
    assert remote["tags"]["mymlfw_runner_id"] == runner.runner_id
    assert remote["tags"]["mymlfw_org_id"] == org_id


def test_aws_imdsv2_and_client_token(org_id: str):
    from mymlfw.saas.providers import IMDSV2_METADATA_OPTIONS, default_cloud_service

    svc = default_cloud_service(org_id=org_id, cloud_runners=True)
    svc.connect_aws(role_arn="arn:aws:iam::123456789012:role/mymlfw-runner")
    offers = [o for o in svc.list_gpus("aws") if o.stock > 0]
    assert offers
    gpu = offers[0].gpu_type
    quote = svc.quote_launch(provider="aws", gpu_type=gpu)
    runner = svc.launch(
        provider="aws",
        gpu_type=gpu,
        quote_accepted_micros_hr=quote.cost_estimate_micros_hr,
        spot=True,
    )
    remote = svc.aws_transport.instances[runner.provider_instance_id]
    assert remote["client_token"] == runner.runner_id
    assert remote["metadata_options"] == IMDSV2_METADATA_OPTIONS
    assert remote["metadata_options"]["HttpPutResponseHopLimit"] == 1
    assert remote["tags"]["mymlfw_org_id"] == org_id


def test_orphan_sweeper_terminates_tagged_without_row(org_id: str):
    from mymlfw.saas.providers import default_cloud_service

    svc = default_cloud_service(org_id=org_id, cloud_runners=True)
    svc.connect_runpod(api_key="runpod-test-key-xxxxxx")
    # Plant an orphan remote with tags but no runners row.
    orphan = svc.runpod_transport.create_pod(
        spec={
            "gpu_type": "NVIDIA GeForce RTX 4090",
            "cost_estimate_micros_hr": 440_000,
            "tags": {
                "mymlfw_runner_id": "rnr_01HORPHAN00000000000000000",
                "mymlfw_org_id": org_id,
            },
        }
    )
    assert orphan["instance_id"] in svc.runpod_transport.pods
    result = svc.sweep_orphans()
    assert result["interval_minutes"] == 15
    assert any(t["instance_id"] == orphan["instance_id"] for t in result["terminated"])
    assert orphan["instance_id"] not in svc.runpod_transport.pods


def test_stop_terminate_lifecycle(org_id: str):
    from mymlfw.saas.providers import default_cloud_service
    from mymlfw.saas.schemas import RunnerLifecycleStatus

    svc = default_cloud_service(org_id=org_id, cloud_runners=True)
    svc.connect_runpod(api_key="runpod-test-key-xxxxxx")
    gpu = svc.list_gpus("runpod")[0].gpu_type
    quote = svc.quote_launch(provider="runpod", gpu_type=gpu)
    runner = svc.launch(
        provider="runpod",
        gpu_type=gpu,
        quote_accepted_micros_hr=quote.cost_estimate_micros_hr,
    )
    stopped = svc.stop(runner.runner_id)
    assert stopped.status == RunnerLifecycleStatus.stopped
    gone = svc.terminate(runner.runner_id)
    assert gone.status == RunnerLifecycleStatus.terminated


def test_pick_runner_auto_prefers_local_then_cheapest_cloud():
    from mymlfw.saas.providers import pick_runner_auto
    from mymlfw.worker.fair_share import FairShareQueue

    runners = [
        {
            "_id": "rnr_cloud_expensive",
            "runner_id": "rnr_cloud_expensive",
            "kind": "runpod_pod",
            "status": "online",
            "cost_estimate_micros_hr": 3_000_000,
        },
        {
            "_id": "rnr_cloud_cheap",
            "runner_id": "rnr_cloud_cheap",
            "kind": "aws_ec2",
            "status": "online",
            "cost_estimate_micros_hr": 500_000,
        },
    ]
    picked = pick_runner_auto(runners)
    assert picked is not None
    assert picked["runner_id"] == "rnr_cloud_cheap"

    with_local = [
        {
            "_id": "rnr_local",
            "runner_id": "rnr_local",
            "kind": "local",
            "status": "online",
            "cost_estimate_micros_hr": 0,
        },
        *runners,
    ]
    assert pick_runner_auto(with_local)["runner_id"] == "rnr_local"

    q = FairShareQueue(runners_for_org=lambda _oid: with_local)
    q.enqueue(org_id="org_x", job={"runner": "auto", "job_id": "job_1"})
    claimed = q.claim_next()
    assert claimed is not None
    assert claimed["runner_id"] == "rnr_local"
    assert claimed["runner_pick"] == "auto"


def test_connect_provider_stub_still_reports_flag():
    from mymlfw.saas.providers import connect_provider_stub

    assert connect_provider_stub("runpod")["feature_flag"] == "cloud_runners"
    assert connect_provider_stub("aws")["status"] == "credentials_required"


def test_cli_connect_gpus_launch_quote(org_id: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MYMLFW_ORG_ID", org_id)
    monkeypatch.setenv("MYMLFW_CLOUD_RUNNERS", "1")
    from mymlfw.saas.providers import cli as cloud_cli

    # Reset process-local store between tests.
    cloud_cli.reset_cli_service()

    connected = json.loads(
        cloud_cli.cloud_connect(provider="runpod", api_key="runpod-cli-key-xxxxxx")
    )
    assert connected["provider"] == "runpod"
    gpus = json.loads(cloud_cli.cloud_gpus(provider="runpod"))
    assert gpus["gpus"]
    gpu_type = gpus["gpus"][0]["gpu_type"]
    quoted = json.loads(
        cloud_cli.cloud_launch(provider="runpod", gpu_type=gpu_type, quote_only=True)
    )
    assert quoted["cost_estimate_micros_hr"] > 0
    launched = json.loads(cloud_cli.cloud_launch(provider="runpod", gpu_type=gpu_type))
    assert launched["runner"]["status"] == "online"
    listed = json.loads(cloud_cli.cloud_list())
    assert listed["runners"]


def test_mcp_runners_resource_has_no_secrets(org_id: str):
    from mymlfw.mcp.tools import resource_org_runners
    from mymlfw.saas.providers import default_cloud_service

    svc = default_cloud_service(org_id=org_id, cloud_runners=True)
    svc.connect_runpod(api_key="super-secret-runpod-key")
    gpu = svc.list_gpus("runpod")[0].gpu_type
    quote = svc.quote_launch(provider="runpod", gpu_type=gpu)
    svc.launch(
        provider="runpod",
        gpu_type=gpu,
        quote_accepted_micros_hr=quote.cost_estimate_micros_hr,
    )
    payload = resource_org_runners(
        org_id=org_id, cloud_service=svc, cloud_runners_enabled=True
    )
    blob = json.dumps(payload)
    assert "super-secret-runpod-key" not in blob
    assert "ciphertext" not in blob
    assert payload["feature_flag"] == "cloud_runners"
    assert len(payload["runners"]) == 1


@pytest.mark.asyncio
async def test_cloud_api_routes_gated_then_enabled():
    fastapi = pytest.importorskip("fastapi")
    httpx = pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient

    from mymlfw.api.app import create_app
    from mymlfw.api.auth import AUTH_STORE
    from mymlfw.api.settings import Settings

    _ = fastapi
    AUTH_STORE.users.clear()
    AUTH_STORE.by_email.clear()
    AUTH_STORE.orgs.clear()
    AUTH_STORE.memberships.clear()
    AUTH_STORE.sessions.clear()
    AUTH_STORE.personas.clear()

    app = create_app(Settings(mongo_uri="", redis_url="", env="dev"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post(
            "/v1/auth/register",
            json={
                "email": "cloud@example.com",
                "password": "password123",
                "display_name": "Cloud",
            },
        )
        assert reg.status_code == 200
        token = reg.json()["access_token"]
        org_id = reg.json()["org_id"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "cloud-block-1",
        }

        blocked = await client.post(
            "/v1/orgs/current/cloud/connect/runpod",
            headers=headers,
            json={"api_key": "runpod-test-key-xxxxxx"},
        )
        assert blocked.status_code == 403

        AUTH_STORE.orgs[org_id]["feature_flags"]["cloud_runners"] = True
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "cloud-ok-1",
        }
        ok = await client.post(
            "/v1/orgs/current/cloud/connect/runpod",
            headers=headers,
            json={"api_key": "runpod-test-key-xxxxxx"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["provider"] == "runpod"
        assert "api_key" not in ok.json()

        gpus = await client.get(
            "/v1/orgs/current/cloud/gpus",
            headers={"Authorization": f"Bearer {token}"},
            params={"provider": "runpod"},
        )
        assert gpus.status_code == 200
        gpu_type = gpus.json()[0]["gpu_type"]
        micros = gpus.json()[0]["cost_estimate_micros_hr"]

        launched = await client.post(
            "/v1/orgs/current/cloud/launch",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "cloud-launch-1",
            },
            json={
                "provider": "runpod",
                "gpu_type": gpu_type,
                "cost_estimate_micros_hr": micros,
            },
        )
        assert launched.status_code == 200, launched.text
        runner_id = launched.json()["runner_id"]

        runners = await client.get(
            "/v1/orgs/current/runners",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert runners.status_code == 200
        assert any(r["runner_id"] == runner_id for r in runners.json())


def test_envelope_requires_kek_in_production(monkeypatch):
    from mymlfw.saas.secrets.envelope import EnvelopeError, seal_secret

    monkeypatch.setenv("MYMLFW_ENV", "production")
    monkeypatch.delenv("MYMLFW_KEK_V1", raising=False)
    monkeypatch.delenv("MYMLFW_REQUIRE_KEK", raising=False)
    with pytest.raises(EnvelopeError) as ei:
        seal_secret("secret-value")
    assert ei.value.code == "kek_missing"


def test_provision_fail_create_marks_error_and_sweeper_cleans(org_id: str):
    from mymlfw.saas.providers import default_cloud_service
    from mymlfw.saas.providers.runpod import MockRunPodTransport
    from mymlfw.saas.providers.service import CloudProviderError

    svc = default_cloud_service(org_id=org_id, cloud_runners=True)
    transport = MockRunPodTransport(fail_create=True)
    svc.runpod_transport = transport
    svc.connect_runpod(api_key="runpod-test-key-xxxxxx")
    gpus = svc.list_gpus("runpod")
    gpu = gpus[0].gpu_type
    quote = svc.quote_launch(provider="runpod", gpu_type=gpu)
    with pytest.raises(CloudProviderError) as ei:
        svc.launch(
            provider="runpod",
            gpu_type=gpu,
            quote_accepted_micros_hr=quote.cost_estimate_micros_hr,
        )
    assert ei.value.code == "provision_failed"
    # Simulate crash window: remote exists while row is error without protection.
    transport.fail_create = False
    # Plant an orphan remote with no protected runner row
    planted = transport.create_pod(
        spec={
            "tags": {
                "mymlfw_org_id": org_id,
                "mymlfw_runner_id": "rnr_orphan_unprotected",
            }
        }
    )
    swept = svc.sweep_orphans()
    assert any(t["instance_id"] == planted["instance_id"] for t in swept["terminated"])


def test_cloud_mock_mode_respects_env(monkeypatch):
    from mymlfw.saas.providers.mode import use_cloud_mock
    from mymlfw.saas.providers.runpod import LiveRunPodTransport, MockRunPodTransport
    from mymlfw.saas.providers.service import CloudProviderService, InMemoryCloudStore
    from mymlfw.saas.schemas import FeatureFlags, OrgEntitlements

    monkeypatch.setenv("MYMLFW_CLOUD_MOCK", "1")
    assert use_cloud_mock() is True
    monkeypatch.setenv("MYMLFW_CLOUD_MOCK", "0")
    assert use_cloud_mock() is False

    # Live path constructs LiveRunPodTransport when mock is off.
    svc = CloudProviderService(
        org_id="org_01HLIVEMODETEST00000000000",
        store=InMemoryCloudStore(),
        feature_flags=FeatureFlags(cloud_runners=True),
        entitlements=OrgEntitlements(max_cloud_micros_day=0),
    )
    client = svc._runpod_client("rp_live_key_for_mode_test")
    assert isinstance(client.transport, LiveRunPodTransport)
    assert client.transport.api_key == "rp_live_key_for_mode_test"

    monkeypatch.setenv("MYMLFW_CLOUD_MOCK", "1")
    svc2 = CloudProviderService(
        org_id="org_01HMOCKMODETEST00000000000",
        store=InMemoryCloudStore(),
        feature_flags=FeatureFlags(cloud_runners=True),
        entitlements=OrgEntitlements(max_cloud_micros_day=0),
    )
    client2 = svc2._runpod_client("ignored-under-mock")
    assert isinstance(client2.transport, MockRunPodTransport)


@pytest.mark.asyncio
async def test_mcp_connect_and_launch_under_mock(org_id: str, monkeypatch):
    from mymlfw.mcp import tools as mcp_tools
    from mymlfw.saas.control_plane import set_org_policy
    from mymlfw.saas.pats import PatStore
    from mymlfw.saas.providers.service import InMemoryCloudStore
    from mymlfw.saas.schemas import FeatureFlags

    monkeypatch.setenv("MYMLFW_CLOUD_MOCK", "1")
    set_org_policy(org_id, feature_flags=FeatureFlags(cloud_runners=True))
    store = InMemoryCloudStore()
    pats = PatStore()
    minted = pats.create(workspace_id=org_id, scopes=["mcp:worker"])
    connected = await mcp_tools.tool_connect_cloud_provider(
        provider="runpod",
        pats=pats,
        cloud_store=store,
        pat=minted.token,
        api_key="runpod-mcp-secret-key",
        idempotency_key="mcp-connect-1",
    )
    assert connected.get("provider") == "runpod"
    assert "api_key" not in connected
    assert "runpod-mcp-secret-key" not in json.dumps(connected)

    gpus = await mcp_tools.tool_list_cloud_gpus(
        provider="runpod", pats=pats, cloud_store=store, pat=minted.token
    )
    assert gpus["gpus"]
    gpu_type = gpus["gpus"][0]["gpu_type"]
    quote = await mcp_tools.tool_quote_cloud_launch(
        provider="runpod",
        gpu_type=gpu_type,
        pats=pats,
        cloud_store=store,
        pat=minted.token,
    )
    missing = await mcp_tools.tool_launch_cloud_runner(
        provider="runpod",
        gpu_type=gpu_type,
        cost_estimate_micros_hr=quote["cost_estimate_micros_hr"],
        pats=pats,
        cloud_store=store,
        pat=minted.token,
    )
    assert missing["error_code"] == "idempotency_key_required"

    launched = await mcp_tools.tool_launch_cloud_runner(
        provider="runpod",
        gpu_type=gpu_type,
        cost_estimate_micros_hr=quote["cost_estimate_micros_hr"],
        pats=pats,
        cloud_store=store,
        pat=minted.token,
        idempotency_key="mcp-launch-1",
    )
    assert launched["status"] == "online"
    assert "runpod-mcp-secret-key" not in json.dumps(launched)
