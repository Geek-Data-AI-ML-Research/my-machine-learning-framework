"""Section 2: typed chunks and retrieval rank."""

from __future__ import annotations

import pandas as pd

from mymlfw.rag.index import (
    chunks_for_path,
    contest_dirs,
    ledger_chunks,
    markdown_chunks,
    recipe_chunks,
    retrieve,
    skipped_file,
)
from mymlfw.rag.store import Store


def test_ledger_markdown_and_recipe_stay_atomic(tmp_path):
    ledger = (
        "date,experiment_id,baseline_id,variable,change_count,cv_mean,cv_std,cv_delta,"
        "expected_band_low,expected_band_high,public_score,cv_lb_gap,artifact_sha256,verdict,note\n"
        "2026-01-01,exp_019,base,lora_r=64,1,0.88,,-0.041,0,1,0.79,,,confirmed-large-gap,overfit fold\n"
        "2026-01-02,exp_020,base,pending_var,1,,,,,,,,,pending,still running\n"
    )
    rows = ledger_chunks(ledger, "CASMI", "CASMI/ledger/experiments.csv")
    assert len(rows) == 1
    assert "confirmed-large-gap" in rows[0]["meta_text"]
    assert "lora_r=64" in rows[0]["meta_text"]
    playbook = "# Playbook\n\n## LLM Authorship\n\n### Calibration\n\nFit T out of fold.\n"
    sections = markdown_chunks(playbook, "recipes/GRANDMASTER_PLAYBOOK.md")
    assert any("Playbook" in section["meta_text"] and "Calibration" in section["meta_text"] for section in sections)
    recipe = "id: closed-set-llm-id\ntags: [text]\nsummary: card\nknown_traps:\n- experiment_id: exp_019\n  variable: lora_r=64\n  note: leaked fold\n"
    traps = [chunk for chunk in recipe_chunks(recipe, "recipes/closed-set-llm-id.yaml") if chunk["chunk_type"] == "trap"]
    assert len(traps) == 1
    assert "leaked fold" in traps[0]["body_text"]
    raw = tmp_path / "train.csv"
    raw.write_text("id,text\n1,secret row\n")
    weight = tmp_path / "weights.pt"
    weight.write_bytes(b"nope")
    assert skipped_file(raw) and skipped_file(weight)
    assert chunks_for_path(raw) == []


def test_linked_worktree_is_not_a_contest(tmp_path):
    parent = tmp_path / "projects"
    real = parent / "contest"
    linked = parent / "contest-advise-abc"
    real.mkdir(parents=True)
    linked.mkdir()
    (real / ".git").mkdir()
    (linked / ".git").write_text("gitdir: ../contest/.git\n")
    found = contest_dirs(parent)
    assert real in found
    assert linked not in found


def test_porter_and_char_overlap(tmp_path):
    store = Store(tmp_path / "memory.db")
    try:
        store.upsert_chunk(
            {
                "chunk_id": "cal",
                "source_path": "notes.md",
                "chunk_type": "field_note",
                "outcome_weight": 1.0,
                "meta_text": "calibration note",
                "body_text": "temperature calibration",
            }
        )
        store.upsert_chunk(
            {
                "chunk_id": "group",
                "source_path": "groups.md",
                "chunk_type": "field_note",
                "outcome_weight": 1.0,
                "meta_text": "cv",
                "body_text": "prefer group_kfold on prompt ids",
            }
        )
        cal = retrieve(store, "calibrating")
        assert any("calibration" in item["body_text"] or "calibration" in item["meta_text"] for item in cal["ranked"])
        grouped = retrieve(store, "GroupKFold")
        assert any(item["chunk_id"] == "group" for item in grouped["ranked"])
    finally:
        store.close()


def test_traps_outrank_distractors_and_duplicates_collapse(tmp_path):
    store = Store(tmp_path / "memory.db")
    try:
        for index in range(15):
            store.upsert_chunk(
                {
                    "chunk_id": f"noise-{index}",
                    "source_path": f"noise-{index}.md",
                    "chunk_type": "doc",
                    "outcome_weight": 1.0,
                    "meta_text": "cloud chemistry boilerplate",
                    "body_text": f"unrelated cloud launch note {index}",
                }
            )
        store.upsert_chunk(
            {
                "chunk_id": "trap-alpha",
                "source_path": "ledger",
                "chunk_type": "trap",
                "outcome_weight": 1.25,
                "meta_text": "[VERDICT: kill] [VAR: alpha_leak]",
                "body_text": "TARGET_TRAP_ALPHA specific leakage",
            }
        )
        store.upsert_chunk(
            {
                "chunk_id": "trap-beta",
                "source_path": "ledger",
                "chunk_type": "trap",
                "outcome_weight": 1.25,
                "meta_text": "[VERDICT: confirmed-large-gap] [VAR: beta_leak]",
                "body_text": "TARGET_TRAP_BETA specific leakage",
            }
        )
        store.upsert_chunk(
            {
                "chunk_id": "episode:1",
                "source_path": "episodes",
                "chunk_type": "episode",
                "outcome_weight": 1.25,
                "meta_text": "[OUTCOME: failed]",
                "body_text": "failed episode about something else",
            }
        )
        result = retrieve(store, "TARGET_TRAP_ALPHA TARGET_TRAP_BETA specific leakage")
        negative_ids = [item["chunk_id"] for item in result["negative"]]
        assert "trap-alpha" in negative_ids[:3]
        assert "trap-beta" in negative_ids[:3]
        ranks = []
        for target in ("trap-alpha", "trap-beta"):
            rank = negative_ids.index(target) + 1
            ranks.append(1.0 / rank if rank <= 3 else 0.0)
        assert sum(ranks) / 2 >= 0.5
        for index in range(5):
            store.upsert_chunk(
                {
                    "chunk_id": f"same-{index}",
                    "source_path": f"same-{index}",
                    "chunk_type": "trap",
                    "outcome_weight": 1.25,
                    "meta_text": "[VERDICT: kill] [VAR: lr]",
                    "body_text": "lr=1e-3 failed",
                }
            )
        collapsed = retrieve(store, "lr=1e-3 failed")
        same = [item["chunk_id"] for item in collapsed["negative"] if item["chunk_id"].startswith("same-")]
        assert len(same) == 1
    finally:
        store.close()


def test_expansion_and_superseded_weight(tmp_path):
    store = Store(tmp_path / "memory.db")
    try:
        store.upsert_chunk(
            {
                "chunk_id": "gk",
                "source_path": "notes",
                "chunk_type": "field_note",
                "outcome_weight": 1.0,
                "meta_text": "cv",
                "body_text": "GroupKFold stops prompt leakage",
            }
        )
        store.upsert_chunk(
            {
                "chunk_id": "len",
                "source_path": "notes",
                "chunk_type": "field_note",
                "outcome_weight": 1.0,
                "meta_text": "seq",
                "body_text": "length_sort keeps the batch under the cap",
            }
        )
        grouped = pd.DataFrame({"id": ["a", "b", "c", "d"], "group": ["g", "g", "h", "h"], "label": ["x", "y", "x", "y"]})
        found = retrieve(store, "next experiment", train=grouped)
        assert "GroupKFold" in found["query"]
        assert any(item["chunk_id"] == "gk" for item in found["ranked"])
        long_text = "word " + ("x" * 2000)
        long_frame = pd.DataFrame({"id": ["a", "b"], "text": [long_text, long_text]})
        long_found = retrieve(store, "next experiment", train=long_frame)
        assert "length_sort" in long_found["query"]
        assert any(item["chunk_id"] == "len" for item in long_found["ranked"])
        store.upsert_chunk(
            {
                "chunk_id": "active",
                "source_path": "a",
                "chunk_type": "field_note",
                "outcome_weight": 1.0,
                "meta_text": "same idea",
                "body_text": "shared calibration phrase",
            }
        )
        store.upsert_chunk(
            {
                "chunk_id": "old",
                "source_path": "b",
                "chunk_type": "field_note",
                "outcome_weight": 0.2,
                "meta_text": "same idea",
                "body_text": "shared calibration phrase",
            }
        )
        ranked = [item["chunk_id"] for item in retrieve(store, "shared calibration phrase")["ranked"]]
        assert ranked.index("active") < ranked.index("old")
    finally:
        store.close()
