"""Project roadmap strategies — plan then record results."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_roadmap_strategy_lifecycle():
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
        }

        created = await client.post(
            "/v1/projects",
            headers={**headers, "Idempotency-Key": "roadmap-proj-1"},
            json={
                "name": "Roadmap Demo",
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

        empty = await client.get(
            f"/v1/projects/{project_id}/roadmap", headers=headers
        )
        assert empty.status_code == 200
        assert empty.json()["strategies"] == []

        minted = await client.post(
            f"/v1/projects/{project_id}/roadmap",
            headers={**headers, "Idempotency-Key": "roadmap-ok"},
            json={
                "title": "Logistic public stack",
                "plan": "Blend top public OOFs with logistic regression",
                "priority": 10,
            },
        )
        assert minted.status_code == 200, minted.text
        body = minted.json()
        assert body["status"] == "planned"
        assert body["id"].startswith("rds_")
        strategy_id = body["id"]

        started = await client.patch(
            f"/v1/projects/{project_id}/roadmap/{strategy_id}",
            headers={**headers, "Idempotency-Key": "roadmap-start"},
            json={"status": "in_progress"},
        )
        assert started.status_code == 200
        assert started.json()["status"] == "in_progress"

        done = await client.patch(
            f"/v1/projects/{project_id}/roadmap/{strategy_id}",
            headers={**headers, "Idempotency-Key": "roadmap-done"},
            json={
                "status": "executed",
                "result": "public 0.95143",
                "result_metric": 0.95143,
            },
        )
        assert done.status_code == 200
        finished = done.json()
        assert finished["status"] == "executed"
        assert finished["result"] == "public 0.95143"
        assert finished["result_metric"] == pytest.approx(0.95143)
        assert finished["executed_at"] is not None

        listed = await client.get(
            f"/v1/projects/{project_id}/roadmap", headers=headers
        )
        assert len(listed.json()["strategies"]) == 1

        deleted = await client.delete(
            f"/v1/projects/{project_id}/roadmap/{strategy_id}",
            headers={**headers, "Idempotency-Key": "roadmap-del"},
        )
        assert deleted.status_code == 200
        after = await client.get(
            f"/v1/projects/{project_id}/roadmap", headers=headers
        )
        assert after.json()["strategies"] == []
