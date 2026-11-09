"""DS playbook catalogs — CLI + Studio shared source."""

from __future__ import annotations

import json
import subprocess
import sys

from mymlfw.playbook import (
    build_seed_roadmap,
    modality_strategies,
    paradigm_shifts,
    playbook_catalog,
)


def test_tabular_strategies_include_gpt2_paradigm():
    rows = modality_strategies("tabular")
    ids = [r["id"] for r in rows]
    assert "tab_trees" in ids
    assert "tab_gpt2" in ids
    assert rows[0]["tier"] == "default"


def test_shifts_filter_by_venue_and_modality():
    kaggle_tab = paradigm_shifts(modality="tabular", kind="kaggle")
    ids = {s["id"] for s in kaggle_tab}
    assert "synth_gpt_tabular" in ids
    assert "kaggle_bps" in ids
    assert "commercial_stop" not in ids
    assert "label_delay" not in ids

    commercial_text = paradigm_shifts(modality="text", kind="standalone")
    cids = {s["id"] for s in commercial_text}
    assert "text_dominates" in cids
    assert "commercial_stop" in cids
    assert "synth_gpt_tabular" not in cids


def test_catalog_payload_shape():
    cat = playbook_catalog(modality="vision", kind="kaggle")
    assert cat["modality"] == "vision"
    assert "strategies_by_modality" in cat
    assert "vision" in cat["strategies_by_modality"]
    assert any(s["id"] == "vision_detection" for s in cat["paradigm_shifts"])


def test_seed_roadmap_includes_selected_shift():
    items = build_seed_roadmap(
        modality="tabular",
        kind="kaggle",
        baseline="lightgbm",
        validation="skf5",
        shifts=["synth_gpt_tabular"],
    )
    titles = [i["title"] for i in items]
    assert titles[0].startswith("Stage 1")
    assert any("GPT-2" in t for t in titles)


def test_cli_playbook_strategies_json():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mymlfw",
            "playbook",
            "strategies",
            "--modality",
            "text",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["modality"] == "text"
    assert any(s["id"] == "txt_deberta" for s in payload["strategies"])
