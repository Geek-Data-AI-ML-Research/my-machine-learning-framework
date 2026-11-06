"""Regression tests for Bugbot + security review findings."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from mymlfw.api.app import create_app
from mymlfw.api.auth import AUTH_STORE
from mymlfw.saas.autopilot import (
    expire_wall_budget_if_needed,
    get_autopilot_store,
    halt_autopilot,
    rollback_autopilot_start,
    start_autopilot,
)
from mymlfw.saas.ensemble import EnsembleError, maybe_subsample_indices, promote_blend_to_experiment
from mymlfw.saas.schemas import FeatureFlags


@pytest.fixture(autouse=True)
def _reset():
    from mymlfw.saas.autopilot import reset_autopilot_store

    reset_autopilot_store()
    yield
    reset_autopilot_store()


def test_rollback_autopilot_start_clears_session_and_lock():
    out = start_autopilot(
        workspace_id="org_rb",
        project_id="prj_rb",
        night_shift_enabled=True,
    )
    sid = out["session"]["id"]
    store = get_autopilot_store()
    assert sid in store.sessions
    rollback_autopilot_start(
        workspace_id="org_rb", project_id="prj_rb", session_id=sid
    )
    assert sid not in store.sessions
    from mymlfw.saas.autopilot import execution_lock_key

    assert store.locks.get(execution_lock_key("org_rb", "prj_rb")) is None
    # Retry start succeeds (no 12h stuck lock).
    again = start_autopilot(
        workspace_id="org_rb",
        project_id="prj_rb",
        night_shift_enabled=True,
    )
    assert again["status"] == "running"


def test_halt_releases_lock_and_api_halt_route():
    out = start_autopilot(
        workspace_id="org_h",
        project_id="prj_h",
        night_shift_enabled=True,
    )
    sid = out["session"]["id"]
    halted = halt_autopilot(
        project_id="prj_h", session_id=sid, workspace_id="org_h"
    )
    assert halted["status"] == "halted"
    from mymlfw.saas.autopilot import execution_lock_key

    assert get_autopilot_store().locks.get(execution_lock_key("org_h", "prj_h")) is None

    app = create_app()
    client = TestClient(app)
    reg = client.post(
        "/v1/auth/register",
        json={
            "email": "halt@localhost",
            "password": "devpassword",
            "display_name": "Halt",
        },
    )
    token = reg.json()["access_token"]
    org_id = reg.json()["org_id"]
    AUTH_STORE.orgs[org_id]["feature_flags"] = FeatureFlags(night_shift=True).model_dump()
    started = client.post(
        "/v1/projects/prj_01HHALTAPI000000000000000/autopilot/start",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "halt-start"},
        json={"hours": 1, "max_probes": 4},
    )
    assert started.status_code == 200, started.text
    sid2 = started.json()["session"]["id"]
    resp = client.post(
        "/v1/projects/prj_01HHALTAPI000000000000000/autopilot/halt",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "halt-1"},
        json={"session_id": sid2, "reason": "operator_halt"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "halted"


def test_wall_budget_expires_on_status_helper():
    out = start_autopilot(
        workspace_id="org_w",
        project_id="prj_w",
        hours=0.0001,
        night_shift_enabled=True,
    )
    sid = out["session"]["id"]
    store = get_autopilot_store()
    store.sessions[sid].started_at = datetime.now(UTC) - timedelta(hours=2)
    expired = expire_wall_budget_if_needed(
        project_id="prj_w", session_id=sid, workspace_id="org_w"
    )
    assert expired is not None
    assert expired["status"] == "completed"
    from mymlfw.saas.autopilot import execution_lock_key

    assert store.locks.get(execution_lock_key("org_w", "prj_w")) is None


def test_feature_flags_require_owner_persona():
    app = create_app()
    client = TestClient(app)
    reg = client.post(
        "/v1/auth/register",
        json={
            "email": "viewer-ff@localhost",
            "password": "devpassword",
            "display_name": "Viewer",
        },
    )
    token = reg.json()["access_token"]
    user_id = reg.json()["user_id"]
    AUTH_STORE.set_persona(user_id, "viewer")
    denied = client.patch(
        "/v1/orgs/current/feature-flags",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "ff-viewer-deny",
        },
        json={"cloud_runners": True},
    )
    assert denied.status_code == 403
    AUTH_STORE.set_persona(user_id, "owner")
    ok = client.patch(
        "/v1/orgs/current/feature-flags",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "ff-owner-ok",
        },
        json={"cloud_runners": True},
    )
    assert ok.status_code == 200, ok.text


def test_cloud_connect_denied_for_viewer():
    app = create_app()
    client = TestClient(app)
    reg = client.post(
        "/v1/auth/register",
        json={
            "email": "viewer-cloud@localhost",
            "password": "devpassword",
            "display_name": "Viewer",
        },
    )
    token = reg.json()["access_token"]
    user_id = reg.json()["user_id"]
    org_id = reg.json()["org_id"]
    AUTH_STORE.set_persona(user_id, "viewer")
    AUTH_STORE.orgs[org_id]["feature_flags"]["cloud_runners"] = True
    denied = client.post(
        "/v1/orgs/current/cloud/connect/runpod",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "viewer-connect",
        },
        json={"api_key": "runpod-test-key-xxxxxx"},
    )
    assert denied.status_code == 403


def test_autopilot_tick_requires_attestation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MYMLFW_AUTOPILOT_ALLOW_UNATTESTED", raising=False)
    app = create_app()
    client = TestClient(app)
    reg = client.post(
        "/v1/auth/register",
        json={
            "email": "tick@localhost",
            "password": "devpassword",
            "display_name": "Tick",
        },
    )
    token = reg.json()["access_token"]
    org_id = reg.json()["org_id"]
    AUTH_STORE.orgs[org_id]["feature_flags"] = FeatureFlags(night_shift=True).model_dump()
    started = client.post(
        "/v1/projects/prj_01HTICKATTEST00000000000000/autopilot/start",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "tick-start"},
        json={"hours": 1, "max_probes": 4},
    )
    assert started.status_code == 200, started.text
    sid = started.json()["session"]["id"]
    denied = client.post(
        "/v1/projects/prj_01HTICKATTEST00000000000000/autopilot/tick",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "tick-1"},
        json={"session_id": sid, "smoke_ok": True, "fold0_delta": 0.01},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["error_code"] == "unattested_metrics"
    monkeypatch.setenv("MYMLFW_AUTOPILOT_ALLOW_UNATTESTED", "1")
    ok = client.post(
        "/v1/projects/prj_01HTICKATTEST00000000000000/autopilot/tick",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "tick-2"},
        json={"session_id": sid, "smoke_ok": True, "fold0_delta": 0.01},
    )
    assert ok.status_code == 200, ok.text


def test_subsample_keeps_every_fold():
    import numpy as np

    n = 100
    folds = np.array([i % 5 for i in range(n)], dtype=np.int64)
    # Force subsample with tiny ceiling.
    idx, hint = maybe_subsample_indices(
        n, c=1000, m=1000, folds=folds, ceiling=50_000, allow_subsample=True
    )
    assert idx is not None
    assert hint is not None
    kept = set(int(x) for x in np.unique(folds[idx]).tolist())
    assert kept == {0, 1, 2, 3, 4}


def test_promote_requires_ready_lineage():
    with pytest.raises(EnsembleError) as ei:
        promote_blend_to_experiment(
            parent_oof_ids=["oof_x", "oof_y"],
            weights=[0.5, 0.5],
            mode="linear",
            project_id="prj_x",
        )
    assert ei.value.code == "oof_lineage_unverified"
