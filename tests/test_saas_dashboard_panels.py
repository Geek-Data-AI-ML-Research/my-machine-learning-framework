"""Dashboard Overview panels: plan-named empty-typed fields must be present."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

PLAN_PANELS = (
    "goals",
    "scores",
    "levers",
    "ensemble",
    "compute",
    "paradigms",
    "strategies",
    "research",
    "missions",
    "dead_ends",
    "daily_progress",
    "kaggle",
    "git",
    "brain",
)


def test_compute_dashboard_exposes_plan_panels():
    from mymlfw.saas.dashboard import compute_dashboard

    dash = compute_dashboard(
        project_id="prj_01HTESTDASHBOARD00000000000",
        goals=[],
        experiments=[],
        missions=[],
        dead_ends=[],
    )
    payload = dash.model_dump()
    for name in PLAN_PANELS:
        assert name in payload, f"missing panel {name}"
    assert payload["scores"]["last_scores"] == []
    assert payload["ensemble"]["blend_weights"] == []
    assert payload["daily_progress"]["streak_days"] == 0
    assert payload["kaggle"]["linked"] is False
    assert payload["git"]["linked"] is False
    assert payload["brain"]["episode_count"] == 0
    assert "primary_latest" in payload["header"]
    assert "primary_gap" in payload["header"]
    assert "days_active" in payload["header"]


@pytest.mark.asyncio
async def test_api_dashboard_includes_empty_typed_panels():
    from httpx import ASGITransport, AsyncClient

    from mymlfw.api.app import create_app
    from mymlfw.api.auth import seed_dev_personas
    from mymlfw.api.settings import Settings

    seed_dev_personas()
    app = create_app(Settings(env="dev", mongo_uri="", redis_url=""))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/v1/auth/login",
            json={"email": "owner@localhost", "password": "devpassword"},
            headers={"X-Mymlfw-Client-Version": "0.2.0"},
        )
        assert login.status_code == 200
        headers = {
            "Authorization": f"Bearer {login.json()['access_token']}",
            "X-Mymlfw-Client-Version": "0.2.0",
            "Idempotency-Key": "dash-panels-1",
        }
        created = await client.post(
            "/v1/projects",
            headers=headers,
            json={
                "name": "Panel fixture",
                "kind": "standalone",
                "goals": [
                    {
                        "title": "CV floor",
                        "kind": "notebook_score",
                        "metric_key": "cv_mean",
                        "threshold": 0.30,
                        "direction": "maximize",
                    }
                ],
            },
        )
        assert created.status_code == 200, created.text
        project_id = created.json()["id"]
        dash = await client.get(
            f"/v1/projects/{project_id}/dashboard", headers=headers
        )
        assert dash.status_code == 200, dash.text
        body = dash.json()
        for name in PLAN_PANELS:
            assert name in body
        members = await client.get(
            f"/v1/projects/{project_id}/members", headers=headers
        )
        assert members.status_code == 200, members.text
        assert "members" in members.json()
