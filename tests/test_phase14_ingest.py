"""Section 4: ingest and search."""

from __future__ import annotations

import json
from pathlib import Path

from mymlfw.paths import repo_root
from mymlfw.rag.ingest import ingest, search
from mymlfw.rag.store import Store
from mymlfw.scaffold import token_count


LOSS = '''
class FocalCosineLoss:
    """handles extreme class imbalance"""

    def __init__(self, gamma=2.0):
        self.gamma = gamma

    def forward(self, logits, target):
        return logits
'''


def test_repo_extracts_focal_loss_and_skips_raw_tables(tmp_path):
    root = tmp_path / "contest"
    root.mkdir()
    (root / "loss.py").write_text(LOSS)
    (root / "train.csv").write_text("id,label\n1,a\n" * 100)
    (root / "weights.pt").write_bytes(b"not a weight")
    (root / "broken.py").write_text("def nope(:\n")
    notebook = {
        "cells": [
            {"cell_type": "markdown", "source": "# Calibration\nfit T"},
            {"cell_type": "code", "source": "def score_blend(a):\n    '''blend oof'''\n    return a\n"},
            {"cell_type": "code", "outputs": [{"data": {"image/png": "A" * 1_000_000}}], "source": "x = 1\n"},
        ]
    }
    (root / "notes.ipynb").write_text(json.dumps(notebook))
    db = tmp_path / "memory.db"
    summary = ingest(root, mode="repo", db=db)
    assert summary["files_skipped"] == 1
    assert summary["status"] == "ok"
    hits = search("FocalCosineLoss", db=db)
    assert hits
    assert hits[0]["name"] == "FocalCosineLoss"
    assert "loss.py" in hits[0]["source_path"]
    assert hits[0]["line_start"] == 2
    store = Store(db)
    try:
        bodies = " ".join(chunk["body_text"] for chunk in store.chunks())
    finally:
        store.close()
    assert "secret" not in bodies
    assert "id,label" not in bodies
    assert "A" * 100 not in bodies
    assert "Calibration" in bodies


def test_unchanged_hash_is_a_noop_and_edits_replace_chunks(tmp_path):
    root = tmp_path / "contest"
    root.mkdir()
    source = root / "loss.py"
    source.write_text(LOSS)
    db = tmp_path / "memory.db"
    first = ingest(root, mode="repo", db=db)
    assert first["files_updated"] == 1
    second = ingest(root, mode="repo", db=db)
    assert second["files_updated"] == 0
    source.write_text(LOSS.replace("gamma=2.0", "gamma=3.0"))
    third = ingest(root, mode="repo", db=db)
    assert third["files_updated"] == 1
    hits = search("FocalCosineLoss", db=db)
    assert len(hits) == 1
    assert "gamma=3.0" in hits[0]["snippet"]
    source.unlink()
    ingest(root, mode="repo", db=db)
    assert search("FocalCosineLoss", db=db) == []


def test_docs_mode_skips_python(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "loss.py").write_text(LOSS)
    (root / "note.md").write_text("# Playbook\n\nCalibration holds the fold.\n")
    db = tmp_path / "memory.db"
    summary = ingest(root, mode="docs", db=db)
    assert summary["files_seen"] == 1
    assert search("FocalCosineLoss", chunk_type="code_pattern", db=db) == []
    assert search("Calibration", chunk_type="doc", db=db)


def test_config_records_hyperparameters(tmp_path):
    root = tmp_path / "contest"
    (root / "ledger").mkdir(parents=True)
    (root / "train.yaml").write_text("lr: 0.01\nlora_r: 8\nwarmup_ratio: 0.1\n")
    (root / "ledger" / "experiments.csv").write_text(
        "date,experiment_id,baseline_id,variable,change_count,cv_mean,cv_std,cv_delta,"
        "expected_band_low,expected_band_high,public_score,cv_lb_gap,artifact_sha256,verdict,note\n"
        "2026-01-01,exp_1,base,lora_r=8,1,0.91,,0.01,0,1,,,,promote-candidate,held\n"
    )
    (root / "README.md").write_text("# Contest card\n\nBody.\n")
    db = tmp_path / "memory.db"
    ingest(root, mode="docs", db=db)
    store = Store(db)
    try:
        text = " ".join(chunk["meta_text"] for chunk in store.chunks())
    finally:
        store.close()
    assert "lr" in text and "lora_r" in text and "warmup_ratio" in text
    assert "0.91" in text
    assert "Contest card" in text


def test_llms_lists_ingest_and_search():
    text = (repo_root() / "llms.txt").read_text()
    packaged = (Path(__file__).resolve().parents[1] / "src" / "mymlfw" / "resources" / "llms.txt").read_text()
    assert "python -m mymlfw ingest" in text
    assert "python -m mymlfw search" in text
    assert token_count(text) <= 1500
    assert text == packaged or "python -m mymlfw ingest" in text
