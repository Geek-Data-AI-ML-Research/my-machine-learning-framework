"""Phase C starter: OOF pending→ready, runner env, fair-share, notebook_chunker."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

pydantic = pytest.importorskip("pydantic")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_oof_pending_confirm_ready_flow():
    from mymlfw.saas.artifacts import ArtifactError, default_memory_service
    from mymlfw.saas.schemas import OofArtifactConfirmRequest, OofArtifactCreateRequest

    svc, store = default_memory_service()
    body_bytes = b"oof-matrix-bytes"
    create = OofArtifactCreateRequest(
        experiment_id="exp_01HTESTEXPERIMENT00000000000",
        content_length=len(body_bytes),
        content_sha256=_sha(body_bytes),
        filename="oof.npz",
    )
    presign = svc.create_upload(create)
    assert presign.status.value == "pending_upload"
    assert "Content-Length" in presign.headers
    assert presign.headers["x-amz-checksum-sha256"] == _sha(body_bytes)

    with pytest.raises(ArtifactError) as missing:
        svc.confirm(presign.oof_id)
    assert missing.value.code == "oof_object_missing"

    store.put_bytes(presign.object_key, body_bytes)
    ready = svc.confirm(presign.oof_id, OofArtifactConfirmRequest())
    assert ready.status.value == "ready"
    assert ready.ready_at is not None
    assert ready.content_length == len(body_bytes)

    # Idempotent confirm when already ready.
    again = svc.confirm(presign.oof_id)
    assert again.status.value == "ready"


def test_oof_length_mismatch_blocks_ready():
    from mymlfw.saas.artifacts import ArtifactError, default_memory_service
    from mymlfw.saas.schemas import OofArtifactCreateRequest

    svc, store = default_memory_service()
    create = OofArtifactCreateRequest(
        experiment_id="exp_01HTESTEXPERIMENT00000000000",
        content_length=10,
        content_sha256=_sha(b"0123456789"),
    )
    presign = svc.create_upload(create)
    store.put_bytes(presign.object_key, b"short")
    with pytest.raises(ArtifactError) as exc:
        svc.confirm(presign.oof_id)
    assert exc.value.code == "oof_length_mismatch"
    assert svc.get(presign.oof_id).status.value == "pending_upload"


def test_oof_expire_stale_pending():
    from mymlfw.saas.artifacts import ArtifactError, default_memory_service
    from mymlfw.saas.schemas import OofArtifactCreateRequest

    svc, _store = default_memory_service()
    create = OofArtifactCreateRequest(
        experiment_id="exp_01HTESTEXPERIMENT00000000000",
        content_length=4,
        content_sha256=_sha(b"abcd"),
    )
    presign = svc.create_upload(create)
    doc = svc.repo.get(presign.oof_id)
    assert doc is not None
    doc["expires_at"] = datetime.now(UTC) - timedelta(minutes=1)
    svc.repo.save(doc)
    n = svc.expire_stale_pending()
    assert n == 1
    assert svc.get(presign.oof_id).status.value == "expired"
    with pytest.raises(ArtifactError) as exc:
        svc.confirm(presign.oof_id)
    assert exc.value.code == "oof_expired"


def test_runner_env_forbids_mongo_uri():
    from mymlfw.runner.env import RunnerEnvError, validate_runner_env

    with pytest.raises(RunnerEnvError):
        validate_runner_env(
            {
                "MYMLFW_API_URL": "http://127.0.0.1:8000",
                "MYMLFW_RUNNER_TOKEN": "rnr_tok",
                "MYMLFW_MONGO_URI": "mongodb://secret",
            }
        )
    cleaned = validate_runner_env(
        {
            "MYMLFW_API_URL": "http://127.0.0.1:8000",
            "MYMLFW_RUNNER_TOKEN": "rnr_tok",
        }
    )
    assert "MONGO" not in cleaned


def test_runner_heartbeat_and_job_token_claim():
    from mymlfw.runner.client import RunnerClient, mint_job_token_stub

    client = RunnerClient(runner_id="rnr_01HTESTRUNNER0000000000000")
    hb = client.heartbeat(status="idle")
    assert hb.accepted is True
    empty = client.claim_job()
    assert empty.claimed is False

    job_id = client.enqueue_stub_job(run_id="run_01HTESTRUN000000000000000")
    claim = client.claim_job()
    assert claim.claimed is True
    assert claim.credentials is not None
    assert claim.credentials.job_id == job_id
    assert claim.credentials.job_token
    assert claim.credentials.sandbox_notes
    assert "Mongo" in " ".join(claim.credentials.sandbox_notes) or any(
        "Mongo" in n for n in claim.credentials.sandbox_notes
    )

    creds = mint_job_token_stub()
    delta = creds.expires_at - datetime.now(UTC)
    assert timedelta(hours=1, minutes=50) < delta <= timedelta(hours=2, minutes=1)


def test_fair_share_round_robin_and_cap():
    from mymlfw.worker.fair_share import FairShareConfig, FairShareQueue

    q = FairShareQueue(FairShareConfig(max_concurrent_jobs_per_org=1))
    q.enqueue(org_id="org_a", job={"id": "1"})
    q.enqueue(org_id="org_a", job={"id": "2"})
    q.enqueue(org_id="org_b", job={"id": "3"})

    first = q.claim_next()
    second = q.claim_next()
    assert first is not None and second is not None
    assert {first["org_id"], second["org_id"]} == {"org_a", "org_b"}
    # org_a still has a pending job but is at concurrency cap.
    third = q.claim_next()
    assert third is None
    q.complete(first["org_id"])
    third = q.claim_next()
    assert third is not None
    assert third["org_id"] == "org_a"


def test_research_modes_and_error_slices_shape():
    from mymlfw.saas.research import ResearchRunService, suggested_next_mode
    from mymlfw.saas.schemas import ErrorSliceItem, ResearchRunCreateRequest, ResearchRunMode

    svc = ResearchRunService(
        workspace_id="org_01HTESTWORKSPACE0000000000",
        project_id="prj_01HTESTPROJECT000000000000",
    )
    run = svc.create_run(ResearchRunCreateRequest(mode=ResearchRunMode.fold0_smoke))
    assert run.mode == ResearchRunMode.fold0_smoke
    resource = svc.get_error_slices(run.run_id)
    assert resource.status == "empty"
    assert resource.slices == []

    filled = svc.set_error_slices_stub(
        run.run_id,
        oof_id="oof_01HTESTOOF0000000000000000",
        slices=[
            ErrorSliceItem(
                slice_key="long_seq",
                label="long sequence",
                n_examples=3,
                mean_residual=0.42,
                example_ids=["a", "b", "c"],
            )
        ],
    )
    assert filled.status == "ready"
    assert suggested_next_mode(ResearchRunMode.fold0_smoke) == ResearchRunMode.full_cv
    assert suggested_next_mode(ResearchRunMode.full_cv) is None


def test_notebook_chunker_hypothesis_code_output_units():
    from mymlfw.saas.rag.notebook_chunker import chunk_notebook_dict

    nb = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Hypothesis: try fold0 smoke\n"]},
            {
                "cell_type": "code",
                "source": ["def train_fold0(x):\n    return x\n"],
                "outputs": [{"text": ["ok\n"]}],
            },
            {"cell_type": "markdown", "source": "next idea"},
            {
                "cell_type": "code",
                "source": "class Model:\n    pass\n",
                "outputs": [],
            },
        ]
    }
    units = chunk_notebook_dict(nb)
    assert len(units) == 2
    assert "Hypothesis" in units[0].hypothesis_md
    assert "def train_fold0" in units[0].code
    assert units[0].output_preview.strip() == "ok"
    assert "def:train_fold0" in units[0].ast_tags
    assert "class:Model" in units[1].ast_tags


def test_ensemble_ready_and_autopilot_feature_flag():
    from mymlfw.saas.autopilot import FEATURE_FLAG, reset_autopilot_store, start_autopilot
    from mymlfw.saas.ensemble import plan_ensemble
    from mymlfw.saas.providers import connect_provider_stub

    plan = plan_ensemble(["oof_1", "oof_2"], mode="auto")
    assert plan["status"] == "ready"
    assert plan["mode"] == "auto"
    reset_autopilot_store()
    started = start_autopilot(
        workspace_id="org_byoc",
        project_id="prj_byoc_ap",
        night_shift_enabled=True,
        max_probes=2,
    )
    assert started["feature_flag"] == FEATURE_FLAG == "night_shift"
    assert started["auto_kaggle_submit"] is False
    assert connect_provider_stub("runpod")["feature_flag"] == "cloud_runners"


@pytest.mark.asyncio
async def test_phase_c_api_oof_and_sse_train_strip():
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
                "email": "byoc@localhost",
                "password": "devpassword",
                "display_name": "BYOC",
            },
        )
        assert reg.status_code == 200
        token = reg.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        payload = b"npz-bytes"
        create = await client.post(
            "/v1/projects/prj_01HTESTPROJECT000000000000/oof-artifacts",
            headers={**auth, "Idempotency-Key": "byoc-oof-1"},
            json={
                "experiment_id": "exp_01HTESTEXPERIMENT00000000000",
                "content_length": len(payload),
                "content_sha256": _sha(payload),
                "filename": "oof.npz",
            },
        )
        assert create.status_code == 200, create.text
        body = create.json()
        oof_id = body["oof_id"]
        object_key = body["object_key"]

        # Simulate upload into the in-memory store behind the route.
        from mymlfw.api.routes_phase_c import _artifact_services

        svc = list(_artifact_services(app.state).values())[0]
        svc.store.put_bytes(object_key, payload)

        confirm = await client.post(
            f"/v1/projects/prj_01HTESTPROJECT000000000000/oof-artifacts/{oof_id}/confirm",
            headers={**auth, "Idempotency-Key": "byoc-confirm-1"},
            json={},
        )
        assert confirm.status_code == 200, confirm.text
        assert confirm.json()["status"] == "ready"

        run = await client.post(
            "/v1/projects/prj_01HTESTPROJECT000000000000/research-runs",
            headers={**auth, "Idempotency-Key": "byoc-run-1"},
            json={"mode": "fold0_smoke"},
        )
        assert run.status_code == 200
        assert run.json()["mode"] == "fold0_smoke"

        events = await client.get("/v1/events", headers=auth)
        assert events.status_code == 200
        assert "event: hello" in events.text
        assert "train_strip" not in events.text
