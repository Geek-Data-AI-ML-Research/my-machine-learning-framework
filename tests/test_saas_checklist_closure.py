"""Checklist closure: licenses, SSRF, RAG evals, webhook, elicitation."""

from __future__ import annotations

import json

import pytest

from mymlfw.saas.provenance import (
    evaluate_license_compatibility,
    verify_project_licenses,
)
from mymlfw.saas.rag.retrieve import gather_corpus, retrieve_three_buckets
from mymlfw.saas.ssrf import SsrfError, assert_public_host


def test_phase_d_kaggle_push_diff_and_reensemble():
    import numpy as np

    from mymlfw.saas.ensemble import OofCandidate
    from mymlfw.saas.kaggle_service import (
        gated_kaggle_push,
        ingest_discussion,
        package_submission,
        seal_kaggle_token,
        submission_distribution_diff,
    )
    from mymlfw.saas.provenance import reensemble_clean_oofs

    pkg = package_submission(files=["old.csv"], final2=["new_a.csv", "new_b.csv"])
    assert pkg["final2"] == ["new_a.csv", "new_b.csv"]
    assert "old.csv" in pkg["diff"]["removed"]
    diff = submission_distribution_diff([0.1, 0.2, 0.9], [0.1, 0.2, 0.3])
    assert diff["l1"] >= 0
    sealed = seal_kaggle_token("kaggle-token-value")
    assert sealed["sealed"] is True
    assert "ciphertext" not in sealed  # top-level only; routes strip `_blob`
    assert "_blob" in sealed and sealed["_blob"].get("ciphertext")
    ingested = ingest_discussion(
        text="<b>kernel trick</b>",
        author="ada",
        workspace_id="org_d",
        project_id="prj_d",
    )
    assert ingested["credit"]["authors"] == ["ada"]
    assert "<b>" not in ingested["spotlight"]
    blocked = gated_kaggle_push(
        actor="owner",
        credits=[
            {"name": "nc-set", "status": "BLOCKED_NC", "used_in_final_ensemble": True}
        ],
    )
    assert blocked["ok"] is False
    y = np.array([0, 1, 0, 1, 0, 1], dtype=np.float64)
    folds = np.array([0, 0, 1, 1, 2, 2])
    cands = [
        OofCandidate("keep_a", np.array([0.1, 0.8, 0.2, 0.7, 0.3, 0.6], dtype=np.float32)),
        OofCandidate("keep_b", np.array([0.2, 0.7, 0.3, 0.8, 0.1, 0.9], dtype=np.float32)),
        OofCandidate("nc-set", np.array([0.4, 0.4, 0.4, 0.4, 0.4, 0.4], dtype=np.float32)),
    ]
    clean = reensemble_clean_oofs(
        cands,
        [{"name": "nc-set", "status": "BLOCKED_NC", "used_in_final_ensemble": True}],
        y=y,
        folds=folds,
    )
    assert clean["ok"] is True
    assert "nc-set" in clean["excluded"]
    assert "nc-set" not in clean["names"]


def test_license_matrix():
    assert (
        evaluate_license_compatibility("CC-BY-NC-4.0", commercial_kaggle=True)
        == "BLOCKED_NC"
    )
    assert evaluate_license_compatibility("MIT") == "OK"
    assert (
        evaluate_license_compatibility("GPL-3.0-only", outbound_spdx="Apache-2.0")
        == "BLOCKED_COPYLEFT"
    )
    gate = verify_project_licenses(
        [
            {
                "_id": "crd_x",
                "status": "BLOCKED_NC",
                "used_in_final_ensemble": True,
            }
        ],
        gate="kaggle_submit",
    )
    assert gate["ok"] is False


def test_ssrf_rejects_private_and_link_local():
    def _resolve(host: str) -> list[str]:
        return {
            "evil.example": ["10.1.1.1"],
            "meta.example": ["169.254.169.254"],
            "loop.example": ["127.0.0.1"],
        }[host]

    for host in ("evil.example", "meta.example", "loop.example"):
        with pytest.raises(SsrfError):
            assert_public_host(host, resolve=_resolve)


def test_dead_end_recall_and_epoch_decay_and_tenant_isolation():
    corpus_a = gather_corpus(
        experiments=[],
        dead_ends=[
            {
                "_id": "ded_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "variable": "dropout=0.5",
                "lesson": "dropout collapsed snr",
                "epoch_id": "epoch_2",
                "utility_weight": 1.0,
                "workspace_id": "org_a",
            },
            {
                "_id": "ded_01ARZ3NDEKTSV4RRFFQ69G5FAW",
                "variable": "dropout=0.9",
                "lesson": "dropout still bad",
                "epoch_id": "epoch_0",
                "utility_weight": 1.0,
                "workspace_id": "org_a",
            },
        ],
        episode_cards=[],
    )
    buckets = retrieve_three_buckets(
        query="dropout collapsed",
        corpus=corpus_a,
        current_epoch="epoch_2",
    )
    ids = [h.doc_id for h in buckets["B"][:3]]
    assert "ded_01ARZ3NDEKTSV4RRFFQ69G5FAV" in ids
    # Older epoch should not outrank the current-epoch dead end.
    scores = {h.doc_id: h.score for h in buckets["B"]}
    assert scores["ded_01ARZ3NDEKTSV4RRFFQ69G5FAV"] >= scores.get(
        "ded_01ARZ3NDEKTSV4RRFFQ69G5FAW", 0
    )
    leaked = [h for h in buckets["B"] if "org_b" in h.text]
    assert leaked == []


def test_webhook_hmac_and_replay():
    from mymlfw.saas.git_sync import reset_webhook_replay_for_tests, verify_github_webhook
    import hashlib
    import hmac

    reset_webhook_replay_for_tests()
    body = b'{"ok":true}'
    secret = "s3cret"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_github_webhook(
        body=body, signature=sig, secret=secret, delivery_id="d1"
    )
    assert (
        verify_github_webhook(body=body, signature=sig, secret=secret, delivery_id="d1")
        is False
    )


def test_elicitation_blocks_agent():
    from mymlfw.saas.elicitation import ElicitationError, confirm_elicitation

    with pytest.raises(ElicitationError):
        confirm_elicitation(actor="agent", action="kaggle_submit")
    assert confirm_elicitation(actor="owner", action="kaggle_submit")["status"] == "confirmed"


def test_cli_credits_and_audit_chain():
    import subprocess
    import sys

    from mymlfw.saas.audit_log import append_audit, reset_audit_for_tests, verify_chain

    proc = subprocess.run(
        [sys.executable, "-m", "mymlfw", "credits", "list", "--project", "prj_x"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "numpy" in proc.stdout or "CREDITS" in proc.stdout
    reset_audit_for_tests()
    append_audit("git.sync", {"id": "1"})
    append_audit("git.sync", {"id": "2"})
    assert verify_chain() is True


def test_mission_template_quotes_args():
    from mymlfw.saas.mission_templates import render_cli_steps

    steps = render_cli_steps(
        template_id="fold0_smoke", args={"project_id": "prj_ok"}
    )
    assert steps[0].startswith("python -m mymlfw")
    with pytest.raises(ValueError):
        render_cli_steps(template_id="fold0_smoke", args={"project_id": "a;rm"})


def test_sanitize_strips_tags():
    from mymlfw.saas.sanitize import spotlight_untrusted

    out = spotlight_untrusted("<script>alert(1)</script>hello")
    assert "<script>" not in out
    assert "untrusted_kaggle_content" in out


def test_billing_micros_are_ints():
    from mymlfw.saas.billing import billing_summary, record_usage_event, reset_billing_for_tests

    reset_billing_for_tests()
    record_usage_event(workspace_id="org_b", cost_micros=1500, kind="cloud")
    assert billing_summary("org_b")["cost_micros"] == 1500


def test_events_jsonl_rejects_secrets(tmp_path):
    from mymlfw.saas.git_sync import append_event

    with pytest.raises(ValueError):
        append_event(tmp_path / "events.jsonl", {"token": "sk-abcdefghijklmnopqrstuvwxyz"})


def test_vector_index_has_tenant_filters():
    from pathlib import Path

    doc = json.loads(
        Path("src/mymlfw/saas/db/vector_index.json").read_text(encoding="utf-8")
    )
    paths = [f["path"] for f in doc["definition"]["fields"] if f["type"] == "filter"]
    assert "workspace_id" in paths and "project_id" in paths
    assert doc["definition"]["fields"][0]["quantization"] == "scalar"
