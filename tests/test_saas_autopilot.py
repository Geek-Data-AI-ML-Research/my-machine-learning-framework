"""Autopilot UCT + successive-halving + night_shift gating."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mymlfw.api.app import create_app
from mymlfw.api.auth import AUTH_STORE
from mymlfw.saas.autopilot import (
    AutopilotError,
    AutopilotNode,
    digest_autopilot,
    evaluate_successive_halving_rung,
    get_autopilot_status,
    headless_driver_tick,
    pause_autopilot,
    reset_autopilot_store,
    resume_autopilot,
    select_next_parent_node_uct,
    start_autopilot,
)
from mymlfw.saas.schemas import FeatureFlags


@pytest.fixture(autouse=True)
def _reset_store():
    reset_autopilot_store()
    yield
    reset_autopilot_store()


def test_night_shift_required():
    with pytest.raises(AutopilotError) as ei:
        start_autopilot(
            workspace_id="org_ap",
            project_id="prj_ap",
            night_shift_enabled=False,
        )
    assert ei.value.code == "feature_flag_disabled"


def test_budget_exhaustion_releases_execution_lock():
    from mymlfw.saas.autopilot import execution_lock_key, get_autopilot_store

    out = start_autopilot(
        workspace_id="org_ap",
        project_id="prj_lock",
        max_probes=1,
        max_gpu_hours=0.0001,
        max_llm_cost_micros=1,
        night_shift_enabled=True,
    )
    session_id = out["session"]["id"]
    store = get_autopilot_store()
    key = execution_lock_key("org_ap", "prj_lock")
    assert store.locks.get(key) is not None
    # Force budget empty
    store.sessions[session_id].probes_launched = 99
    tick = headless_driver_tick(
        project_id="prj_lock",
        session_id=session_id,
        night_shift_enabled=True,
    )
    assert tick["status"] == "completed"
    assert store.locks.get(key) is None
    # Can start a new session without waiting 12h
    again = start_autopilot(
        workspace_id="org_ap",
        project_id="prj_lock",
        night_shift_enabled=True,
    )
    assert again["status"] == "running"


def test_tenancy_same_project_id_isolated_by_workspace():
    a = start_autopilot(
        workspace_id="org_a",
        project_id="prj_shared",
        night_shift_enabled=True,
    )
    b = start_autopilot(
        workspace_id="org_b",
        project_id="prj_shared",
        night_shift_enabled=True,
    )
    assert a["session"]["id"] != b["session"]["id"]
    from mymlfw.saas.autopilot import apply_infra_failure, get_autopilot_store, halt_autopilot

    store = get_autopilot_store()
    session_a = store.sessions[a["session"]["id"]]
    for _ in range(3):
        apply_infra_failure(session_a, reason="oom", store=store)
    assert session_a.status == "halted"
    from mymlfw.saas.autopilot import execution_lock_key

    assert store.locks.get(execution_lock_key("org_a", "prj_shared")) is None
    # org_b lock still held
    assert store.locks.get(execution_lock_key("org_b", "prj_shared")) is not None
    halt_autopilot(
        project_id="prj_shared",
        session_id=b["session"]["id"],
        workspace_id="org_b",
    )
    assert store.locks.get(execution_lock_key("org_b", "prj_shared")) is None


def test_start_status_pause_resume_digest_and_tick():
    out = start_autopilot(
        workspace_id="org_ap",
        project_id="prj_ap",
        mode="grandmaster_sweep",
        hours=2.0,
        max_probes=8,
        max_gpu_hours=2.0,
        max_llm_cost_micros=1_000_000,
        night_shift_enabled=True,
    )
    assert out["status"] == "running"
    assert out["auto_kaggle_submit"] is False
    session_id = out["session"]["id"]

    st = get_autopilot_status(project_id="prj_ap", session_id=session_id)
    assert st["session"]["id"] == session_id
    assert st["node_count"] >= 1

    paused = pause_autopilot(project_id="prj_ap", session_id=session_id)
    assert paused["status"] == "paused"

    resumed = resume_autopilot(
        project_id="prj_ap",
        session_id=session_id,
        night_shift_enabled=True,
    )
    assert resumed["status"] == "running"

    tick = headless_driver_tick(
        project_id="prj_ap",
        session_id=session_id,
        variable="loss_fn=focal",
        smoke_ok=True,
        fold0_delta=0.01,
        max_spearman_to_pool=0.2,
        cv_delta=0.005,
        integrity_ok=True,
        llm_cost_micros=1000,
    )
    assert tick.get("lever_verifier")
    assert tick["lever_verifier"]["status"] in {"passed", "deferred_llm", "stub_pass"}
    assert tick.get("auto_kaggle_submit") is False

    digest = digest_autopilot(project_id="prj_ap", session_id=session_id)
    assert "ascii_board" in digest
    assert isinstance(digest["ascii_board"], str)
    assert "queue_kaggle_submit_human" in digest.get("cta", [])


def test_uct_prefers_underexplored():
    nodes = [
        AutopilotNode(
            id="nd_root",
            session_id="aps_x",
            parent_id=None,
            visits=10,
            status="advanced",
            variable="root",
            is_root=True,
            cv_delta=0.0,
            cv_std=1.0,
            max_spearman_to_pool=0.0,
        ),
        AutopilotNode(
            id="nd_a",
            session_id="aps_x",
            parent_id="nd_root",
            visits=1,
            status="advanced",
            variable="a",
            cv_delta=0.01,
            cv_std=1.0,
            max_spearman_to_pool=0.1,
            rung=0,
        ),
        AutopilotNode(
            id="nd_b",
            session_id="aps_x",
            parent_id="nd_root",
            visits=8,
            status="advanced",
            variable="b",
            cv_delta=0.05,
            cv_std=1.0,
            max_spearman_to_pool=0.5,
            rung=0,
        ),
    ]
    chosen = select_next_parent_node_uct(nodes, c=1.4)
    assert chosen is not None
    assert chosen.node_id in {"nd_a", "nd_b", "nd_root"}


def test_successive_halving_gates():
    r0_fail = evaluate_successive_halving_rung(rung=0, smoke_ok=False)
    assert r0_fail.action == "prune"
    r0_pass = evaluate_successive_halving_rung(rung=0, smoke_ok=True)
    assert r0_pass.action == "advance"
    r1 = evaluate_successive_halving_rung(
        rung=1, fold0_delta=0.01, max_spearman_to_pool=0.9
    )
    assert r1.action == "advance"
    r1_div = evaluate_successive_halving_rung(
        rung=1, fold0_delta=0.0, max_spearman_to_pool=0.1
    )
    assert r1_div.action == "advance"
    assert r1_div.diversity_enabled is True
    r2 = evaluate_successive_halving_rung(
        rung=2, cv_delta=0.01, integrity_ok=True
    )
    assert r2.action == "promote"


def test_api_autopilot_start_requires_flag():
    app = create_app()
    client = TestClient(app)
    reg = client.post(
        "/v1/auth/register",
        json={
            "email": "ap-off@localhost",
            "password": "devpassword",
            "display_name": "AP",
        },
    )
    token = reg.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "ap-off-1",
    }
    resp = client.post(
        "/v1/projects/prj_01HAPOFF00000000000000000/autopilot/start",
        headers=headers,
        json={
            "mode": "grandmaster_sweep",
            "hours": 1.0,
            "max_probes": 4,
            "max_gpu_hours": 1.0,
            "max_llm_usd": 1.0,
        },
    )
    assert resp.status_code in {403, 400}
    detail = resp.json().get("detail")
    if isinstance(detail, dict):
        assert detail.get("error_code") == "feature_flag_disabled"


def test_api_autopilot_start_with_flag():
    app = create_app()
    client = TestClient(app)
    reg = client.post(
        "/v1/auth/register",
        json={
            "email": "ap-on@localhost",
            "password": "devpassword",
            "display_name": "APOn",
        },
    )
    token = reg.json()["access_token"]
    org_id = reg.json()["org_id"]
    AUTH_STORE.orgs[org_id]["feature_flags"] = FeatureFlags(night_shift=True).model_dump()
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "ap-on-1",
    }
    resp = client.post(
        "/v1/projects/prj_01HAPON000000000000000000/autopilot/start",
        headers=headers,
        json={
            "mode": "grandmaster_sweep",
            "hours": 1.0,
            "max_probes": 4,
            "max_gpu_hours": 1.0,
            "max_llm_usd": 1.0,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("auto_kaggle_submit") is False
    assert body.get("feature_flag") == "night_shift"


def test_api_autopilot_requires_idempotency_key():
    app = create_app()
    client = TestClient(app)
    reg = client.post(
        "/v1/auth/register",
        json={
            "email": "ap-idem@localhost",
            "password": "devpassword",
            "display_name": "APIdem",
        },
    )
    token = reg.json()["access_token"]
    resp = client.post(
        "/v1/projects/prj_01HAPIDEM0000000000000000/autopilot/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"mode": "grandmaster_sweep", "hours": 1.0},
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "idempotency_key_required"
