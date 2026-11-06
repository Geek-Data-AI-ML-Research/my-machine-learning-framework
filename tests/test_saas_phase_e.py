"""Phase E: citation firewall, 3-bucket retrieve, advise, utility bandit."""

from __future__ import annotations

import pytest

pydantic = pytest.importorskip("pydantic")


def test_citation_firewall_strips_hallucinated_ulids():
    from mymlfw.saas.rag.citation_firewall import enforce_citation_firewall

    real = "ded_01HTESTDEADEND0000000000000"
    fake = "ded_01HFAKEDEADEND0000000000000"
    # Use syntactically valid Crockford — firewall matches prefix+26 chars.
    real = "ded_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    fake = "ded_01ARZ3NDEKTSV4RRFFQ69G5FAW"
    docs = {
        real: {
            "doc_type": "dead_end",
            "status": "active_block",
            "lesson": "keep dropout low",
        }
    }
    brief = f"Avoid {fake} and heed {real} for the next probe."
    fw = enforce_citation_firewall(
        brief_md=brief,
        proposed_missions=[
            {
                "title": "fold0 smoke",
                "goal_id": None,
                "rationale_md": f"Cite {real} and ignore {fake}",
                "cited_ids": [real, fake],
            }
        ],
        fetch_docs=lambda ids: {i: docs[i] for i in ids if i in docs},
    )
    assert fake not in fw.brief_md or "UNVERIFIED-ID-STRIPPED" in fw.brief_md
    assert real in fw.verified_ids
    assert fake in fw.stripped_ids
    assert fw.grounding_score == 0.5
    assert "DB-VERIFIED" in fw.brief_md
    assert fw.proposed_missions[0]["cited_ids"] == [real]


def test_rrf_and_three_bucket_retrieve():
    from mymlfw.saas.rag.retrieve import gather_corpus, retrieve_three_buckets

    corpus = gather_corpus(
        experiments=[
            {
                "_id": "exp_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "variable": "lr=3e-4",
                "cv_mean": 0.31,
                "cv_delta": 0.02,
                "verdict": "promote",
                "epoch_id": "epoch_0",
                "utility_weight": 1.0,
            }
        ],
        dead_ends=[
            {
                "_id": "ded_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "variable": "dropout=0.5",
                "lesson": "High dropout collapsed fold SNR",
                "epoch_id": "epoch_0",
                "utility_weight": 1.2,
                "snr_weight": 1.2,
            }
        ],
        episode_cards=[],
        axioms=[
            {
                "_id": "axm_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "statement": "Prefer fold0_smoke after dead ends",
                "pinned": True,
                "epoch_id": "epoch_0",
            }
        ],
    )
    buckets = retrieve_three_buckets(
        query="dropout SNR fold",
        corpus=corpus,
        current_epoch="epoch_0",
        scope="all",
        max_tokens=512,
    )
    assert "A" in buckets and "B" in buckets and "C" in buckets
    assert any(h.doc_type == "dead_end" for h in buckets["B"]) or buckets["B"] == []


def test_utility_bandit_promote_and_kill():
    from mymlfw.saas.rag.utility import update_cited_memory_utility

    docs = [
        {"_id": "ded_01ARZ3NDEKTSV4RRFFQ69G5FAV", "utility_weight": 1.0, "times_cited": 0},
        {"_id": "epc_01ARZ3NDEKTSV4RRFFQ69G5FAV", "utility_weight": 1.0, "times_cited": 0},
    ]
    update_cited_memory_utility(
        docs, cited_ids=["ded_01ARZ3NDEKTSV4RRFFQ69G5FAV"], outcome="succeeded"
    )
    assert docs[0]["utility_weight"] == pytest.approx(1.10)
    update_cited_memory_utility(
        docs, cited_ids=["epc_01ARZ3NDEKTSV4RRFFQ69G5FAV"], outcome="failed"
    )
    assert docs[1]["utility_weight"] == pytest.approx(0.80)
    assert docs[1]["falsified_on_cv"] is True


def test_advise_runs_citation_firewall(brain_store_demo):
    from mymlfw.saas.advise import advise_project

    store, org_id, project_id = brain_store_demo
    out = advise_project(
        store, workspace_id=org_id, project_id=project_id, task="next dropout probe"
    )
    assert out.brief_md
    assert "verified_ids" in out.citation_firewall
    assert out.grounding_score >= 0.0
    assert out.proposed_missions


def test_complete_mission_writes_episode_card(brain_store_demo):
    store, org_id, project_id = brain_store_demo
    claim = store.claim_next_mission(
        org_id, project_id, lease_owner="pat:tok_test", lease_seconds=600
    )
    assert claim is not None
    before = len(store.episode_cards.get(project_id, []))
    store.complete_mission(
        org_id,
        project_id,
        mission_id=claim.mission_id,
        attempt_count=claim.attempt_count,
        outcome="succeeded",
        fold_scores=[0.2, 0.21, 0.19],
        notes="ok",
    )
    assert len(store.episode_cards.get(project_id, [])) == before + 1


def test_llm_embed_packs_binary_vector():
    from mymlfw.saas.llm import embed_text, reset_llm_limits_for_tests

    reset_llm_limits_for_tests()
    emb = embed_text("hello project brain", org_id="org_t", project_id="prj_t")
    assert len(emb.values) == 64
    assert emb.packed is not None


def test_integrity_scrubs_secrets():
    from mymlfw.saas.rag.integrity import check_text_integrity, scrub_secrets

    dirty = "leak mongodb://user:pass@host/db and sk-abcdefghijklmnopqrstuv"
    assert check_text_integrity(dirty).ok is False
    clean = scrub_secrets(dirty)
    assert "mongodb://" not in clean
    assert "sk-abcdefghijklmnopqrstuv" not in clean


def test_query_expand_and_tier2_cold_start():
    from mymlfw.saas.rag.cold_start import (
        blend_tier2_into_corpus,
        dataset_fingerprint,
        tier2_weight,
    )
    from mymlfw.saas.rag.query_expand import expand_query

    q = expand_query(
        "improve CV",
        error_slices=[{"label": "rare category", "hint": "long sequence"}],
        goal_titles=["beat baseline"],
    )
    assert "rare category" in q
    assert "beat baseline" in q
    assert tier2_weight(experiment_count=0) == 1.0
    assert tier2_weight(experiment_count=12) == 0.0
    fp = dataset_fingerprint({"task_type": "tabular", "n_rows": 5000, "metric": "auc"})
    blended = blend_tier2_into_corpus(
        [], fingerprint=fp, experiment_count=2
    )
    assert len(blended) >= 1
    assert all(r.get("tier") == 2 for r in blended)


def test_contradiction_marks_reverification():
    from mymlfw.saas.rag.contradiction import mark_needs_reverification

    ends = [
        {
            "_id": "ded_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "variable": "dropout=0.5",
            "epoch_id": "epoch_0",
            "status": "active_block",
        }
    ]
    touched = mark_needs_reverification(
        ends,
        variable_family="dropout",
        new_epoch_id="epoch_1",
        context_shifted=False,
    )
    assert touched == ["ded_01ARZ3NDEKTSV4RRFFQ69G5FAV"]
    assert ends[0]["status"] == "needs_reverification"
    assert ends[0]["suggested_run_mode"] == "fold0_smoke"


def test_notebook_chunker_ast_tags():
    from mymlfw.saas.rag.notebook_chunker import chunk_notebook_dict

    units = chunk_notebook_dict(
        {
            "cells": [
                {"cell_type": "markdown", "source": "## Try lower dropout"},
                {
                    "cell_type": "code",
                    "source": "def train_fold(x):\n    return x\n",
                    "outputs": [],
                },
            ]
        }
    )
    assert len(units) == 1
    assert "def:train_fold" in units[0].ast_tags
    assert "dropout" in units[0].hypothesis_md.lower()


@pytest.fixture
def brain_store_demo():
    from mymlfw.saas.brain_store import CampaignBrainStore

    store = CampaignBrainStore()
    org = "org_01HPHASEETEST000000000000"
    summary = store.ensure_demo_campaign(org_id=org, org_slug="phase-e")
    return store, org, summary.id


@pytest.mark.asyncio
async def test_mcp_advise_and_brain_query():
    from mymlfw.mcp import tools as mcp_tools
    from mymlfw.saas.brain_store import BRAIN_STORE
    from mymlfw.saas.missions import MissionService
    from mymlfw.saas.pats import PatStore

    org = "org_01HPHASEEMCP0000000000000"
    summary = BRAIN_STORE.ensure_demo_campaign(org_id=org, org_slug="phase-e-mcp")
    project_id = summary.id
    missions = MissionService(brain=BRAIN_STORE)
    pats = PatStore()
    minted = pats.create(workspace_id=org, scopes=["mcp:worker"])
    brain = await mcp_tools.tool_query_project_brain(
        project_id=project_id,
        missions=missions,
        pats=pats,
        pat=minted.token,
        query="dropout",
    )
    assert brain["status"] in {"ready", "empty"}
    advised = await mcp_tools.tool_advise_project(
        project_id=project_id,
        pats=pats,
        pat=minted.token,
        task="improve CV carefully",
    )
    assert advised.get("error_code") is None
    assert "brief_md" in advised
    assert "citation_firewall" in advised
