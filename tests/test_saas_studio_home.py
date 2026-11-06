"""Studio home + missing plan HTTP surfaces (TDD)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")


@pytest.fixture
async def studio_client():
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
            headers={"X-Mymlfw-Client-Version": "0.1.0"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Mymlfw-Client-Version": "0.1.0",
            "Idempotency-Key": "studio-test-1",
        }
        yield client, headers


@pytest.mark.asyncio
async def test_settings_reads_me_org(studio_client):
    client, headers = studio_client
    res = await client.get("/v1/settings", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user"]["email"] == "owner@localhost"
    assert body["org"]["entitlements"]["max_private_projects"] >= 1
    assert "feature_flags" in body["org"]


@pytest.mark.asyncio
async def test_project_create_archive_invite(studio_client):
    client, headers = studio_client
    create = await client.post(
        "/v1/projects",
        headers={**headers, "Idempotency-Key": "create-1"},
        json={
            "name": "Wizard Campaign",
            "kind": "standalone",
            "goals": [
                {
                    "title": "Notebook CV >= 0.30",
                    "kind": "notebook_score",
                    "metric_key": "cv_mean",
                    "threshold": 0.30,
                    "direction": "maximize",
                }
            ],
        },
    )
    assert create.status_code == 200, create.text
    project = create.json()
    assert project["id"].startswith("prj_")
    assert project["slug"] == "wizard-campaign"
    assert project["kind"] == "standalone"
    project_id = project["id"]

    listed = await client.get("/v1/projects", headers=headers)
    assert any(p["id"] == project_id for p in listed.json()["projects"])

    invite = await client.post(
        f"/v1/projects/{project_id}/invite",
        headers={**headers, "Idempotency-Key": "invite-1"},
        json={"email": "member@localhost", "role": "member"},
    )
    assert invite.status_code == 200, invite.text
    assert invite.json()["email"] == "member@localhost"
    assert invite.json()["role"] == "member"
    assert invite.json()["status"] in {"invited", "active"}

    archive = await client.post(
        f"/v1/projects/{project_id}/archive",
        headers={**headers, "Idempotency-Key": "archive-1"},
        json={},
    )
    assert archive.status_code == 200, archive.text
    assert archive.json()["deleted_at"] is not None

    listed2 = await client.get("/v1/projects", headers=headers)
    assert all(p["id"] != project_id for p in listed2.json()["projects"])


async def _create_project(client, headers, *, name: str = "Real contest") -> str:
    created = await client.post(
        "/v1/projects",
        headers={**headers, "Idempotency-Key": f"create-{name}"},
        json={
            "name": name,
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
    return created.json()["id"]


@pytest.mark.asyncio
async def test_goals_progress_dead_ends_levers_missions(studio_client):
    client, headers = studio_client
    project_id = await _create_project(client, headers)

    goals = await client.get(f"/v1/projects/{project_id}/goals", headers=headers)
    assert goals.status_code == 200, goals.text
    assert len(goals.json()["goals"]) >= 1
    goal_id = goals.json()["goals"][0]["id"]

    created_goal = await client.post(
        f"/v1/projects/{project_id}/goals",
        headers={**headers, "Idempotency-Key": "goal-1"},
        json={
            "title": "Extra CV floor",
            "kind": "notebook_score",
            "metric_key": "cv_mean",
            "threshold": 0.25,
            "direction": "maximize",
        },
    )
    assert created_goal.status_code == 200, created_goal.text
    new_goal_id = created_goal.json()["id"]

    patched = await client.patch(
        f"/v1/projects/{project_id}/goals/{new_goal_id}",
        headers={**headers, "Idempotency-Key": "goal-patch-1"},
        json={"status": "met", "best_value": 0.26},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "met"

    progress_add = await client.post(
        f"/v1/projects/{project_id}/progress",
        headers={**headers, "Idempotency-Key": "prog-1"},
        json={"note": "Tried baseline folds; SNR looks solid."},
    )
    assert progress_add.status_code == 200, progress_add.text
    assert progress_add.json()["note"].startswith("Tried baseline")

    progress_list = await client.get(
        f"/v1/projects/{project_id}/progress", headers=headers
    )
    assert progress_list.status_code == 200
    assert len(progress_list.json()["notes"]) >= 1

    dead_add = await client.post(
        f"/v1/projects/{project_id}/dead-ends",
        headers={**headers, "Idempotency-Key": "ded-1"},
        json={
            "variable": "lr=1e-1",
            "lesson": "Learning rate too high; folds diverged.",
        },
    )
    assert dead_add.status_code == 200, dead_add.text

    dead_list = await client.get(
        f"/v1/projects/{project_id}/dead-ends", headers=headers
    )
    assert dead_list.status_code == 200
    assert any(d["variable"] == "lr=1e-1" for d in dead_list.json()["dead_ends"])

    levers = await client.get(f"/v1/projects/{project_id}/levers", headers=headers)
    assert levers.status_code == 200
    open_before = sum(1 for L in levers.json()["levers"] if L["status"] == "open")

    opened = await client.post(
        f"/v1/projects/{project_id}/levers",
        headers={**headers, "Idempotency-Key": "lever-open-1"},
        json={
            "goal_id": goal_id,
            "variable": "lora_r=32",
            "band_low": 0.0,
            "band_high": 0.05,
        },
    )
    # Demo already has one open lever — second open must 409 (one-open rule).
    if open_before >= 1:
        assert opened.status_code == 409, opened.text
        # Close the existing open lever first.
        open_id = next(
            L["id"] for L in levers.json()["levers"] if L["status"] == "open"
        )
        closed = await client.post(
            f"/v1/projects/{project_id}/levers/{open_id}/close",
            headers={**headers, "Idempotency-Key": "lever-close-1"},
            json={"verdict": "promote", "fold_scores": [0.3, 0.31, 0.29, 0.3, 0.3]},
        )
        assert closed.status_code == 200, closed.text
        opened = await client.post(
            f"/v1/projects/{project_id}/levers",
            headers={**headers, "Idempotency-Key": "lever-open-2"},
            json={
                "goal_id": goal_id,
                "variable": "lora_r=32",
                "band_low": 0.0,
                "band_high": 0.05,
            },
        )
    assert opened.status_code == 200, opened.text
    lever_id = opened.json()["id"]
    assert opened.json()["status"] == "open"

    closed2 = await client.post(
        f"/v1/projects/{project_id}/levers/{lever_id}/close",
        headers={**headers, "Idempotency-Key": "lever-close-2"},
        json={"verdict": "kill", "notes": "no lift"},
    )
    assert closed2.status_code == 200, closed2.text
    assert closed2.json()["status"] == "closed"

    missions = await client.get(
        f"/v1/projects/{project_id}/missions", headers=headers
    )
    assert missions.status_code == 200
    assert len(missions.json()["missions"]) >= 1
    assert "title" in missions.json()["missions"][0]
    assert "status" in missions.json()["missions"][0]
