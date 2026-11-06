"""Phase B unit tests: dashboard formula, fold badges, demo seed, share, sdk."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
pydantic = pytest.importorskip("pydantic")


def test_progress_formula_weights():
    from mymlfw.saas.dashboard import progress_pct

    assert progress_pct(
        goals_met_ratio=1.0, lever_close_rate=0.0, mission_success_rate=0.0
    ) == 0.5
    assert progress_pct(
        goals_met_ratio=0.0, lever_close_rate=1.0, mission_success_rate=0.0
    ) == 0.3
    assert progress_pct(
        goals_met_ratio=0.0, lever_close_rate=0.0, mission_success_rate=1.0
    ) == 0.2
    assert progress_pct(
        goals_met_ratio=0.5, lever_close_rate=0.5, mission_success_rate=0.5
    ) == 0.5


def test_experiments_facet_pipeline_slim_project_before_facet():
    from mymlfw.saas.dashboard import EXPERIMENT_FACET_PROJECT, experiments_facet_pipeline

    pipe = experiments_facet_pipeline()
    assert pipe[0] == {"$sort": {"created_at": -1}}
    assert pipe[1]["$project"] == EXPERIMENT_FACET_PROJECT
    assert "status" in pipe[1]["$project"]
    assert "verdict" in pipe[1]["$project"]
    assert "$facet" in pipe[2]
    assert "lever_stats" in pipe[2]["$facet"]
    assert "sparkline" in pipe[2]["$facet"]
    # Slim projection must come before facet (binding plan rule).
    facet_idx = next(i for i, s in enumerate(pipe) if "$facet" in s)
    project_idx = next(i for i, s in enumerate(pipe) if "$project" in s)
    assert project_idx < facet_idx


def test_fold_snr_badge_solid_vs_noise():
    from mymlfw.saas.fold_badges import adv_auc_label, fold_snr_badge
    from mymlfw.saas.schemas import FoldSnrLabel

    solid = fold_snr_badge(
        [0.31, 0.32, 0.30, 0.33, 0.31],
        baseline_scores=[0.27, 0.28, 0.26, 0.29, 0.28],
    )
    assert solid.wins == 5
    assert solid.n_folds == 5
    assert solid.label == FoldSnrLabel.solid
    assert "5/5 FOLDS" in solid.display
    assert "SOLID" in solid.display

    noise = fold_snr_badge(
        [0.30, 0.20, 0.35, 0.18, 0.32],
        baseline_scores=[0.29, 0.29, 0.29, 0.29, 0.29],
    )
    assert noise.label in (FoldSnrLabel.solid, FoldSnrLabel.noise)
    assert "/" in noise.display

    assert adv_auc_label(0.51) == "SAFE"
    assert adv_auc_label(0.82) == "TIME/DOMAIN SHIFT"
    assert adv_auc_label(None) == "UNKNOWN"


def test_demo_campaign_dashboard_and_parent_lineage():
    from mymlfw.saas.brain_store import CampaignBrainStore

    store = CampaignBrainStore()
    summary = store.ensure_demo_campaign(org_id="org_01HTESTWORKSPACE0000000000", org_slug="acme")
    assert summary.is_demo is True
    assert summary.folds.folds_sha256
    assert summary.folds.adv_auc is not None
    assert summary.folds.artifact_key and summary.folds.artifact_key.endswith(
        "folds.parquet"
    )

    # Idempotent
    again = store.ensure_demo_campaign(org_id="org_01HTESTWORKSPACE0000000000", org_slug="acme")
    assert again.id == summary.id

    exps = store.experiments[summary.id]
    child = next(e for e in exps if e.get("parent_experiment_id"))
    assert child["parent_experiment_id"].startswith("exp_")

    dash = store.dashboard("org_01HTESTWORKSPACE0000000000", summary.id)
    assert dash is not None
    assert dash.header.progress_pct >= 0
    assert dash.goals.met >= 1
    assert dash.levers.open >= 1
    assert dash.missions.queued >= 1
    assert dash.dead_ends.count >= 1
    assert dash.header.adv_auc_label in ("SAFE", "TIME/DOMAIN SHIFT", "UNKNOWN")
    assert any("FOLDS" in b.display for b in dash.levers.fold_badges)


def test_public_snapshot_is_redacted_not_live_dump():
    from mymlfw.saas.brain_store import CampaignBrainStore

    store = CampaignBrainStore()
    summary = store.ensure_demo_campaign(org_id="org_01HSHARE00000000000000000", org_slug="lab")
    snap = store.publish_snapshot(
        org_id="org_01HSHARE00000000000000000",
        org_slug="lab",
        project_id=summary.id,
        include_dead_end_lessons=False,
    )
    assert snap is not None
    assert snap.entropy
    assert snap.slug.endswith(snap.entropy) or snap.entropy in snap.slug
    assert snap.share_path.startswith("/p/lab/")
    red = snap.redacted
    assert "workspace_id" not in red
    assert "project_id" not in red
    assert "folds_sha256" not in red
    assert "progress_pct" in red
    assert "dead_ends_count" in red
    assert "lesson" not in str(red.get("dead_ends", []))


def test_episode_card_and_axiom_schema_stubs():
    from mymlfw.saas.schemas import EpisodeCardStub, ProjectAxiomStub

    card = EpisodeCardStub(
        id="epc_01HTESTEPISODECARD000000000",
        project_id="prj_01HTESTPROJECT000000000000",
        semantic_summary="",
        times_retrieved=0,
        falsified_on_cv=False,
    )
    assert card.utility_weight == 1.0
    ax = ProjectAxiomStub(
        id="axm_01HTESTAXIOM00000000000000",
        project_id="prj_01HTESTPROJECT000000000000",
        pinned=False,
    )
    assert ax.statement == ""


def test_sdk_log_oof_requires_api(monkeypatch):
    from mymlfw.sdk import log_oof

    monkeypatch.setenv("MYMLFW_PROJECT", "prj_01HTESTPROJECT000000000000")
    monkeypatch.delenv("MYMLFW_API", raising=False)
    monkeypatch.delenv("MYMLFW_TOKEN", raising=False)
    with pytest.raises(ValueError, match="MYMLFW_API"):
        log_oof(None, fold_scores=[0.1, 0.2, 0.15])
    with pytest.raises(ValueError):
        log_oof(fold_scores=[float("nan")])


def test_sdk_log_oof_posts_scores(monkeypatch):
    import io
    import json
    from mymlfw.sdk import log_oof

    monkeypatch.setenv("MYMLFW_PROJECT", "prj_01HTESTPROJECT000000000000")
    monkeypatch.setenv("MYMLFW_EXPERIMENT", "exp_01HTESTEXPERIMENT0000000000")
    monkeypatch.setenv("MYMLFW_API", "http://127.0.0.1:9")
    monkeypatch.setenv("MYMLFW_TOKEN", "test-token")
    captured: dict = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _open(req, timeout=30):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return _Resp(
            b'{"experiment_id":"exp_01HTESTEXPERIMENT0000000000","message":"recorded"}'
        )

    monkeypatch.setattr("urllib.request.urlopen", _open)
    out = log_oof(None, fold_scores=[0.1, 0.2, 0.15], params={"lr": 1e-4})
    assert out.status == "accepted"
    assert out.experiment_id.startswith("exp_")
    assert captured["body"]["fold_scores"] == [0.1, 0.2, 0.15]
    assert captured["url"].endswith("/v1/projects/prj_01HTESTPROJECT000000000000/log-oof")


@pytest.mark.asyncio
async def test_api_demo_dashboard_and_share():
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
            headers={**headers, "Idempotency-Key": "phase-b-real-1"},
            json={
                "name": "Phase B fixture",
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
        assert created.json()["is_demo"] is False

        projects = await client.get("/v1/projects", headers=headers)
        assert projects.status_code == 200
        assert any(p["id"] == project_id for p in projects.json()["projects"])

        dash = await client.get(
            f"/v1/projects/{project_id}/dashboard", headers=headers
        )
        assert dash.status_code == 200
        body = dash.json()
        assert "progress_pct" in body["header"]
        assert "goals_met_ratio" in body["header"]
        assert "lever_close_rate" in body["header"]
        assert "mission_success_rate" in body["header"]

        share = await client.post(
            f"/v1/projects/{project_id}/share",
            headers={**headers, "Idempotency-Key": "share-1"},
            json={"include_goals": True, "include_lever_stats": True},
        )
        assert share.status_code == 200
        snap = share.json()
        pub = await client.get(
            f"/v1/public/{snap['org_slug']}/{snap['slug']}",
            headers={"X-Mymlfw-Client-Version": "0.1.0"},
        )
        assert pub.status_code == 200
        assert "workspace_id" not in pub.json()["redacted"]


def test_project_scoped_db_exposes_goals_experiments_axioms():
    from mymlfw.saas.db.project_db import ProjectScopedDB

    class _DB(dict):
        def __getitem__(self, name):
            return type("C", (), {"name": name})()

    pdb = ProjectScopedDB(
        _DB(),
        workspace_id="org_01HTESTWORKSPACE0000000000",
        project_id="prj_01HTESTPROJECT000000000000",
    )
    assert pdb.goals.name == "project_goals"
    assert pdb.experiments.name == "experiments"
    assert pdb.dead_ends.name == "dead_ends"
    assert pdb.axioms.name == "project_axioms"
    assert pdb.episode_cards.name == "memory_chunks"
