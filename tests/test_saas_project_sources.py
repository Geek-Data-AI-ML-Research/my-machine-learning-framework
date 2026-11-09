"""Project sources CRUD (title / url / description)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_project_sources_crud():
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
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Mymlfw-Client-Version": "0.2.0",
        }

        created = await client.post(
            "/v1/projects",
            headers={**headers, "Idempotency-Key": "src-proj-1"},
            json={
                "name": "Sources Demo",
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
            f"/v1/projects/{project_id}/sources", headers=headers
        )
        assert empty.status_code == 200
        assert empty.json()["sources"] == []

        bad = await client.post(
            f"/v1/projects/{project_id}/sources",
            headers={**headers, "Idempotency-Key": "src-bad"},
            json={"title": "Nope", "url": "ftp://example.com/x", "description": ""},
        )
        assert bad.status_code == 422

        minted = await client.post(
            f"/v1/projects/{project_id}/sources",
            headers={**headers, "Idempotency-Key": "src-ok"},
            json={
                "title": "Paper",
                "url": "https://arxiv.org/abs/1234.5678",
                "description": "Baseline ideas",
            },
        )
        assert minted.status_code == 200, minted.text
        body = minted.json()
        assert body["title"] == "Paper"
        assert body["url"].startswith("https://")
        source_id = body["id"]
        assert source_id.startswith("src_")

        listed = await client.get(
            f"/v1/projects/{project_id}/sources", headers=headers
        )
        assert listed.status_code == 200
        assert len(listed.json()["sources"]) == 1

        patched = await client.patch(
            f"/v1/projects/{project_id}/sources/{source_id}",
            headers={**headers, "Idempotency-Key": "src-patch"},
            json={"description": "Updated note"},
        )
        assert patched.status_code == 200
        assert patched.json()["description"] == "Updated note"

        deleted = await client.delete(
            f"/v1/projects/{project_id}/sources/{source_id}",
            headers={**headers, "Idempotency-Key": "src-del"},
        )
        assert deleted.status_code == 200
        after = await client.get(
            f"/v1/projects/{project_id}/sources", headers=headers
        )
        assert after.json()["sources"] == []
