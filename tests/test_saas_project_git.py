"""Project git link + parsed details."""

from __future__ import annotations

import pytest

from mymlfw.saas.git_info import build_git_info, normalize_remote, parse_remote


def test_parse_github_remotes():
    https = parse_remote("https://github.com/acme/fraud-stack.git")
    assert https["provider"] == "github"
    assert https["owner"] == "acme"
    assert https["name"] == "fraud-stack"
    assert https["html_url"] == "https://github.com/acme/fraud-stack"

    ssh = parse_remote("git@github.com:acme/fraud-stack.git")
    assert ssh["full_name"] == "acme/fraud-stack"

    with pytest.raises(ValueError, match="blocked"):
        normalize_remote("https://localhost/org/repo")


def test_build_git_info_offline():
    info = build_git_info("https://github.com/acme/demo", live=False)
    assert info["remote"].startswith("https://")
    assert info["stars"] is None
    assert info["provider"] == "github"


@pytest.mark.asyncio
async def test_project_git_link_api():
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
        token = login.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Mymlfw-Client-Version": "0.2.0",
        }
        created = await client.post(
            "/v1/projects",
            headers={**headers, "Idempotency-Key": "git-proj-1"},
            json={
                "name": "Git Demo",
                "kind": "standalone",
                "goals": [
                    {
                        "title": "CV floor",
                        "kind": "notebook_score",
                        "metric_key": "cv_mean",
                        "threshold": 0.3,
                        "direction": "maximize",
                    }
                ],
            },
        )
        project_id = created.json()["id"]

        empty = await client.get(f"/v1/projects/{project_id}/git", headers=headers)
        assert empty.status_code == 200
        assert empty.json()["linked"] is False

        linked = await client.put(
            f"/v1/projects/{project_id}/git",
            headers={**headers, "Idempotency-Key": "git-link-1"},
            json={
                "remote": "https://github.com/acme/fraud.git",
                "refresh": False,
            },
        )
        assert linked.status_code == 200, linked.text
        body = linked.json()
        assert body["linked"] is True
        assert body["git"]["full_name"] == "acme/fraud"
        assert body["git"]["provider"] == "github"

        cleared = await client.delete(
            f"/v1/projects/{project_id}/git",
            headers={**headers, "Idempotency-Key": "git-del-1"},
        )
        assert cleared.status_code == 200
        assert cleared.json()["linked"] is False
