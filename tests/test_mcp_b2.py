"""Phase B2: mission leases, hashed PATs, thin MCP tools (Mongo optional / mocked)."""

from __future__ import annotations

import pytest

pymongo = pytest.importorskip("pymongo")
pydantic = pytest.importorskip("pydantic")


@pytest.fixture
def brain():
    from mymlfw.saas.brain_store import CampaignBrainStore

    store = CampaignBrainStore()
    store.ensure_demo_campaign(org_id="org_01HTESTWORKSPACE0000000000", org_slug="demo")
    return store


@pytest.fixture
def pats():
    from mymlfw.saas.pats import PatStore

    return PatStore()


@pytest.fixture
def missions(brain):
    from mymlfw.saas.missions import MissionService

    return MissionService(brain=brain, project_db_factory=None)


@pytest.mark.asyncio
async def test_pat_hashed_at_rest_not_plaintext(pats):
    created = pats.create(
        workspace_id="org_01HTESTWORKSPACE0000000000",
        scopes=["mcp:worker"],
    )
    assert created.token.startswith(created.token_prefix)
    assert created.token != created.token_prefix
    row = pats.export_audit_row(created.token_id)
    assert row is not None
    assert "token" not in row or row.get("token") is None
    assert row["token_hash_len"] == 32  # sha256 digest bytes
    assert pats.verify(created.token) is not None
    assert pats.verify("mlp_bogus.secret") is None


@pytest.mark.asyncio
async def test_claim_complete_fencing_token_stale_409(brain, missions, pats):
    from mymlfw.mcp import tools as mcp_tools

    org = "org_01HTESTWORKSPACE0000000000"
    summary = brain.ensure_demo_campaign(org_id=org, org_slug="demo")
    project_id = summary.id
    minted = pats.create(workspace_id=org, project_id=project_id)

    claimed = await mcp_tools.tool_get_next_mission(
        project_id=project_id,
        missions=missions,
        pats=pats,
        pat=minted.token,
        idempotency_key="claim-1",
    )
    assert claimed["mission"] is not None
    mission = claimed["mission"]
    token = mission["lease_fencing_token"]
    mission_id = mission["mission_id"]
    assert token >= 1

    progress = await mcp_tools.tool_report_mission_progress(
        project_id=project_id,
        mission_id=mission_id,
        lease_fencing_token=token,
        missions=missions,
        pats=pats,
        pat=minted.token,
        note="halfway",
        percent=50.0,
        idempotency_key="prog-1",
    )
    assert progress.get("error_code") is None
    assert progress["lease_fencing_token"] == token

    stale = await mcp_tools.tool_complete_mission(
        project_id=project_id,
        mission_id=mission_id,
        lease_fencing_token=token + 99,
        outcome="succeeded",
        missions=missions,
        pats=pats,
        pat=minted.token,
        fold_scores=[0.1, 0.2],
        idempotency_key="done-bad",
    )
    assert stale["error_code"] == "stale_lease"

    done = await mcp_tools.tool_complete_mission(
        project_id=project_id,
        mission_id=mission_id,
        lease_fencing_token=token,
        outcome="succeeded",
        missions=missions,
        pats=pats,
        pat=minted.token,
        fold_scores=[0.31, 0.32, 0.29],
        idempotency_key="done-ok",
    )
    assert done["status"] == "succeeded"
    assert done["lease_fencing_token"] == token

    # Idempotent replay
    replay = await mcp_tools.tool_complete_mission(
        project_id=project_id,
        mission_id=mission_id,
        lease_fencing_token=token,
        outcome="succeeded",
        missions=missions,
        pats=pats,
        pat=minted.token,
        idempotency_key="done-ok",
    )
    assert replay.get("replayed") is True


@pytest.mark.asyncio
async def test_dashboard_list_projects_and_brain_stub(brain, missions, pats):
    from mymlfw.mcp import tools as mcp_tools

    org = "org_01HTESTWORKSPACE0000000000"
    summary = brain.ensure_demo_campaign(org_id=org, org_slug="demo")
    minted = pats.create(workspace_id=org)

    listing = await mcp_tools.tool_list_projects(
        missions=missions, pats=pats, pat=minted.token
    )
    assert any(p["id"] == summary.id for p in listing["projects"])

    dash = await mcp_tools.tool_get_project_dashboard(
        project_id=summary.id,
        missions=missions,
        pats=pats,
        pat=minted.token,
    )
    assert dash["project_id"] == summary.id
    assert "header" in dash
    assert dash["missions"]["queued"] >= 0

    brain_q = await mcp_tools.tool_query_project_brain(
        project_id=summary.id,
        missions=missions,
        pats=pats,
        pat=minted.token,
    )
    assert brain_q["status"] == "not_ready"
    assert brain_q["results"] == []


@pytest.mark.asyncio
async def test_project_scoped_db_claim_complete_with_mock_collection():
    """Unit-level fencing without a live Mongo (mock find_one_and_update)."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock

    from mymlfw.saas.db.errors import StaleLeaseError
    from mymlfw.saas.db.project_db import ProjectScopedDB

    now = datetime.now(UTC)
    mission_doc = {
        "_id": "msn_01HTESTMISSION00000000000000",
        "workspace_id": "org_01HTESTWORKSPACE0000000000",
        "project_id": "prj_01HTESTPROJECT000000000000",
        "status": "leased",
        "attempt_count": 2,
        "lease_owner": "pat:tok_x",
        "lease_expires_at": now,
        "title": "split_setup",
        "mission_type": "custom",
        "brief_md": "",
        "deleted_at": None,
    }

    missions_coll = MagicMock()
    claimed = {
        **mission_doc,
        "attempt_count": 1,
        "status": "leased",
        "title": "split_setup",
    }
    missions_coll.find_one_and_update = AsyncMock(side_effect=[claimed, None, mission_doc])
    missions_coll.find_one = AsyncMock(return_value=mission_doc)

    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=missions_coll)
    # complete_mission_transactional needs client.start_session
    session = MagicMock()
    session.bind = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=None),
        )
    )

    async def _with_txn(cb):
        return await cb(session)

    session.with_transaction = AsyncMock(side_effect=_with_txn)
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    client = MagicMock()
    client.start_session = MagicMock(return_value=session_cm)
    db.client = client

    # enqueue_outbox_event writes outbox_events
    outbox = MagicMock()
    outbox.insert_one = AsyncMock()

    def _getitem(name):
        if name == "missions":
            return missions_coll
        if name == "outbox_events":
            return outbox
        return MagicMock()

    db.__getitem__.side_effect = _getitem

    pdb = ProjectScopedDB(
        db,
        workspace_id="org_01HTESTWORKSPACE0000000000",
        project_id="prj_01HTESTPROJECT000000000000",
    )
    claim = await pdb.claim_next_mission(lease_owner="pat:tok_x")
    assert claim is not None
    assert claim.attempt_count == 1

    # Stale complete: find_one_and_update returns None, find_one returns doc
    missions_coll.find_one_and_update = AsyncMock(return_value=None)
    missions_coll.find_one = AsyncMock(return_value=mission_doc)
    with pytest.raises(StaleLeaseError):
        await pdb.complete_mission_transactional(
            mission_id=mission_doc["_id"],
            attempt_count=99,
            outcome="succeeded",
        )


def test_mcp_package_has_no_mongo_markers():
    """Mirror CI anti-drift for mcp/."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from check_saas_anti_drift import check_mcp_no_mongo  # type: ignore

    errors = check_mcp_no_mongo()
    assert errors == [], errors
    assert (root / "src/mymlfw/mcp/server.py").exists()


def test_build_mcp_server_registers_b2_tools():
    pytest.importorskip("mcp")
    from mymlfw.mcp.server import build_mcp_server
    from mymlfw.saas.brain_store import CampaignBrainStore
    from mymlfw.saas.missions import MissionService
    from mymlfw.saas.pats import PatStore

    brain = CampaignBrainStore()
    missions = MissionService(brain=brain)
    pats = PatStore()
    server = build_mcp_server(missions=missions, pats=pats)
    # Tool registry is populated at decoration time.
    tool_names = {t.name for t in server._tool_manager.list_tools()}
    for required in (
        "get_next_mission",
        "complete_mission",
        "get_project_dashboard",
        "list_projects",
        "report_mission_progress",
        "query_project_brain",
    ):
        assert required in tool_names
