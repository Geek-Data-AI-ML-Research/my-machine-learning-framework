"""MCP gap reports — agent suggests missing tools."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_report_mcp_gap_tool_and_api_list():
    from mymlfw.saas.db.mcp_gap_data import reset_memory_gaps_for_tests
    from mymlfw.saas.pats import PatStore
    from mymlfw.mcp import tools as mcp_tools

    reset_memory_gaps_for_tests()
    pats = PatStore()
    minted = pats.create(workspace_id="org_01HTESTORG000000000000000")
    headers = {"Authorization": f"Bearer {minted.token}"}

    created = await mcp_tools.tool_report_mcp_gap(
        title="Need kaggle_refresh",
        needed_capability="MCP tool to refresh Kaggle LB / submissions",
        pats=pats,
        headers=headers,
        idempotency_key="gap-1",
        context="After submit, Studio Overview still stale",
        workaround="Told human to click Sync in Studio",
        severity="annoying",
        suggested_tool_name="refresh_kaggle_intel",
        suggested_args_schema='{"project_id": "prj_…", "live": true}',
    )
    assert created.get("id", "").startswith("gap_"), created
    assert created["title"] == "Need kaggle_refresh"

    listed = await mcp_tools.tool_list_mcp_gaps(pats=pats, headers=headers)
    assert len(listed["gaps"]) == 1
    assert listed["gaps"][0]["suggested_tool_name"] == "refresh_kaggle_intel"

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
        token = login.json()["access_token"]
        headers_api = {
            "Authorization": f"Bearer {token}",
            "X-Mymlfw-Client-Version": "0.1.0",
            "Idempotency-Key": "gap-api-1",
        }
        posted = await client.post(
            "/v1/orgs/current/mcp-gaps",
            headers=headers_api,
            json={
                "title": "Need dead_end MCP write",
                "needed_capability": "record_dead_end via MCP",
                "severity": "blocker",
                "suggested_tool_name": "record_dead_end",
            },
        )
        assert posted.status_code == 200, posted.text
        listed_api = await client.get(
            "/v1/orgs/current/mcp-gaps",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Mymlfw-Client-Version": "0.1.0",
            },
        )
        assert listed_api.status_code == 200
        assert any(
            g["suggested_tool_name"] == "record_dead_end"
            for g in listed_api.json()["gaps"]
        )
