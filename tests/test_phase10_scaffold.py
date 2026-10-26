import json
import os
import subprocess
import sys

import pytest
import yaml

from mymlfw.campaign import COLUMNS, register_probe, save_ledger, set_verdict, update_cv
from mymlfw.errors import MymlfwError
from mymlfw.paths import repo_root
from mymlfw.scaffold import (
    archive_contest,
    default_contrib_dir,
    ensure_token_budget,
    field_notes_path,
    list_recipes,
    new_contest,
    promote_plugin,
    remember,
    sync_llms_index,
)


def test_new_contest_scaffold(tmp_path):
    root = new_contest("demo", tmp_path)
    header = (root / "ledger" / "experiments.csv").read_text().splitlines()[0].split(",")
    assert header == COLUMNS
    assert "cv_delta" in header
    metadata = json.loads((root / "kernel" / "kernel-metadata.json").read_text())
    assert metadata["enable_internet"] is False
    tokens = (root / "llms.txt").read_text().split()
    assert len(tokens) <= 1500
    assert "DO NOT write custom GroupKFold loops" in (root / "llms.txt").read_text()
    readme = (root / "custom_plugins" / "README.md").read_text()
    assert "test_<name>.py" in readme
    assert "CPU-only" in readme
    assert "No network" in readme
    assert "PredictorProtocol" in (root / "engine.py").read_text()
    assert "self.run(" in (root / "engine.py").read_text()
    assert "mymlfw cloud launch" in (root / "cloud" / "launch.sh").read_text()
    assert "shutdown" not in (root / "cloud" / "launch.sh").read_text()
    cell2 = (root / "kernel" / "src" / "cell2_run.py").read_text()
    assert "subprocess" in cell2
    assert "argsort" in cell2
    loaded = yaml.safe_load((root / "configs" / "train.yaml").read_text())
    assert loaded["peft_type"] == "lora"
    script = root / "bin" / "preflight_submit.sh"
    assert "--require-scale-report" in script.read_text()
    completed = subprocess.run(
        ["sh", str(script), "--ledger", "missing.csv", "--experiment-id", "x",
         "--artifact", "missing.bin", "--gate", "g.json", "--leak", "l.json",
         "--runtime", "r.json", "--kernel", "k.json"],
        check=False, capture_output=True, text=True,
        env={**os.environ, "PYTHON": sys.executable},
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stderr)
    assert payload["error_code"]
    assert payload["suggested_fix"]


def test_recipes_match_ranking_only():
    cards = list_recipes("ranking")
    assert [card["id"] for card in cards] == ["ranking"]
    completed = subprocess.run(
        [sys.executable, "-m", "mymlfw", "recipes", "--match", "ranking"],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0
    assert "ranking:" in completed.stdout
    assert "closed-set-llm-id" not in completed.stdout


def test_archive_sorts_wins_and_records_traps(tmp_path):
    ledger = tmp_path / "experiments.csv"
    register_probe(ledger, experiment_id="base", baseline_id="origin", variable="root",
                   expected_band_low=0.0, expected_band_high=1.0, note="root")
    update_cv(ledger, "base", 0.30)
    register_probe(ledger, experiment_id="small", baseline_id="base", variable="lora_r=32",
                   expected_band_low=0.3, expected_band_high=0.4, note="small win")
    update_cv(ledger, "small", 0.31)
    register_probe(ledger, experiment_id="large", baseline_id="base", variable="lora_r=8",
                   expected_band_low=0.3, expected_band_high=0.5, note="large win")
    update_cv(ledger, "large", 0.50)
    register_probe(ledger, experiment_id="dead", baseline_id="base", variable="lora_r=64",
                   expected_band_low=0.1, expected_band_high=0.2, note="killed run")
    register_probe(ledger, experiment_id="gap", baseline_id="base", variable="bad_prior",
                   expected_band_low=0.1, expected_band_high=0.2, note="gap run")
    update_cv(ledger, "gap", 0.10)
    set_verdict(ledger, "small", "promote-candidate")
    set_verdict(ledger, "large", "promote-candidate")
    set_verdict(ledger, "dead", "kill")
    set_verdict(ledger, "gap", "confirmed-large-gap")
    playbook = tmp_path / "GRANDMASTER_PLAYBOOK.md"
    archive_contest(ledger, playbook)
    text = playbook.read_text()
    wins = text.split("## proven_wins", 1)[1].split("## known_traps", 1)[0]
    traps = text.split("## known_traps", 1)[1]
    assert wins.index("lora_r=8") < wins.index("lora_r=32")
    assert "lora_r=64" not in wins
    assert "killed run" not in wins
    assert "lora_r=64" in traps
    assert "killed run" in traps
    assert traps.index("bad_prior") < traps.index("lora_r=64")


def test_archive_refuses_site_packages(tmp_path):
    ledger = tmp_path / "experiments.csv"
    save_ledger(ledger, [])
    blocked = tmp_path / "site-packages" / "GRANDMASTER_PLAYBOOK.md"
    try:
        archive_contest(ledger, blocked)
    except MymlfwError as exc:
        assert exc.error_code == "SITE_PACKAGES"
    else:
        raise AssertionError("site-packages write was allowed")


def test_archive_recipe_keeps_card_fields(tmp_path):
    card = {
        "id": "ranking",
        "tags": ["ranking", "mrr"],
        "summary": "Ranked channels, MRR, one variable per probe.",
        "signatures": {"target_type": "ranking", "has_group_col": False, "has_text_col": False},
    }
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    (recipes / "ranking.yaml").write_text(yaml.safe_dump(card, sort_keys=False))
    ledger = tmp_path / "experiments.csv"
    register_probe(ledger, experiment_id="base", baseline_id="origin", variable="root",
                   expected_band_low=0.0, expected_band_high=1.0, note="root")
    update_cv(ledger, "base", 0.30)
    register_probe(ledger, experiment_id="large", baseline_id="base", variable="lora_r=8",
                   expected_band_low=0.3, expected_band_high=0.5, note="large win")
    update_cv(ledger, "large", 0.50)
    register_probe(ledger, experiment_id="dead", baseline_id="base", variable="lora_r=64",
                   expected_band_low=0.1, expected_band_high=0.2, note="killed run")
    set_verdict(ledger, "large", "promote-candidate")
    set_verdict(ledger, "dead", "kill")
    archive_contest(ledger, tmp_path / "play.md", recipe="ranking", recipes_dir=recipes)
    loaded = yaml.safe_load((recipes / "ranking.yaml").read_text())
    assert loaded["id"] == "ranking"
    assert loaded["tags"] == ["ranking", "mrr"]
    assert loaded["summary"] == card["summary"]
    assert loaded["signatures"]["target_type"] == "ranking"
    assert loaded["proven_wins"][0]["variable"] == "lora_r=8"
    assert loaded["known_traps"][0]["variable"] == "lora_r=64"
    assert loaded["known_traps"][0]["note"] == "killed run"
    update_cv(ledger, "large", 0.60)
    archive_contest(ledger, tmp_path / "play.md", recipe="ranking", recipes_dir=recipes)
    refreshed = yaml.safe_load((recipes / "ranking.yaml").read_text())
    assert refreshed["proven_wins"][0]["cv_delta"] == pytest.approx(0.30)
    assert refreshed["id"] == "ranking"


def test_recipes_show_prints_the_card():
    completed = subprocess.run(
        [sys.executable, "-m", "mymlfw", "recipes", "--show", "ranking"],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0
    assert "summary:" in completed.stdout
    assert "signatures:" in completed.stdout
    assert "target_type: ranking" in completed.stdout


def test_remember_dedupes_on_a_temp_notes_file(tmp_path):
    import sqlite3

    notes = tmp_path / "memory.db"
    rule = "Use grad_checkpointing and batch_size=2 when max_len > 1536 on T4"
    first = remember("deberta,vram,kaggle-t4", rule, "exp_014", notes=notes)
    assert first["status"] == "remembered"
    again = subprocess.run(
        [
            sys.executable, "-m", "mymlfw", "remember",
            "--tag", "kaggle-t4, deberta, vram",
            "--rule", rule,
            "--evidence", "exp_099",
            "--notes", str(notes),
        ],
        check=False, capture_output=True, text=True,
    )
    assert again.returncode == 0
    assert again.stdout.strip() == "duplicate"
    loaded = sqlite3.connect(notes).execute("SELECT tags, evidence FROM field_notes").fetchall()
    assert len(loaded) == 1
    assert loaded[0][0] == "deberta,kaggle-t4,vram"
    assert loaded[0][1] == "exp_014"
    assert field_notes_path() == repo_root() / "recipes" / "memory.db"


def test_list_recipes_searches_an_explicit_notes_path(tmp_path):
    notes = tmp_path / "memory.db"
    rule = "Use grad_checkpointing and batch_size=2 when max_len > 1536 on T4"
    remember("deberta,vram,kaggle-t4", rule, "exp_014", notes=notes)
    found = list_recipes("deberta", notes_path=notes)
    assert any(card["id"] == "field-note" and "grad_checkpointing" in card["summary"] for card in found)
    ranking = list_recipes("ranking", notes_path=notes)
    assert [card["id"] for card in ranking] == ["ranking"]


def test_promote_plugin_rejects_lora_import(tmp_path):
    plugin = tmp_path / "bad_lora.py"
    plugin.write_text("import mymlfw.train.lora\n\ndef trick():\n    return 1\n")
    (tmp_path / "test_bad_lora.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    dest = tmp_path / "contrib"
    tests_dest = tmp_path / "tests-out"
    completed = subprocess.run(
        [
            sys.executable, "-m", "mymlfw", "promote-plugin", str(plugin),
            "--category", "blend",
            "--dest", str(dest),
            "--tests-dest", str(tests_dest),
        ],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode != 0
    payload = json.loads(completed.stderr)
    assert payload["error_code"] == "PLUGIN_IMPORT_FORBIDDEN"
    assert payload["suggested_fix"]
    assert not (dest / "bad_lora.py").exists()
    assert not (tests_dest / "test_contrib_bad_lora.py").exists()


def test_promote_plugin_rejects_importlib_and_exec(tmp_path):
    plugin = tmp_path / "dyn_load.py"
    plugin.write_text(
        "import importlib\n\ndef trick():\n"
        "    return importlib.import_module('mymlfw.train.lora')\n"
    )
    (tmp_path / "test_dyn_load.py").write_text("def test_ok():\n    assert True\n")
    dest = tmp_path / "contrib"
    with pytest.raises(MymlfwError) as error:
        promote_plugin(plugin, "contrib", dest=dest, tests_dest=tmp_path / "tests-out")
    assert error.value.error_code == "PLUGIN_IMPORT_FORBIDDEN"
    assert not (dest / "dyn_load.py").exists()
    clean = tmp_path / "clean_exec.py"
    clean.write_text("def trick():\n    return 1\n")
    (tmp_path / "test_clean_exec.py").write_text("def test_ok():\n    exec('import os')\n")
    with pytest.raises(MymlfwError) as exec_error:
        promote_plugin(clean, "contrib", dest=dest, tests_dest=tmp_path / "tests-exec")
    assert exec_error.value.error_code == "PLUGIN_IMPORT_FORBIDDEN"


def test_promote_plugin_copies_a_passing_plugin(tmp_path):
    plugin = tmp_path / "my_trick.py"
    plugin.write_text('"""Scale a score.\n"""\n\ndef scale(value):\n    return value * 2\n')
    (tmp_path / "test_my_trick.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
        "from my_trick import scale\n\n"
        "def test_scale():\n"
        "    assert scale(2) == 4\n"
        "    assert 1 + 1 == 2\n"
    )
    dest = tmp_path / "contrib"
    tests_dest = tmp_path / "tests-out"
    copied = promote_plugin(plugin, "blend", dest=dest, tests_dest=tests_dest)
    assert copied == dest / "my_trick.py"
    assert copied.read_text().startswith('"""Scale a score.')
    assert (tests_dest / "test_contrib_my_trick.py").is_file()
    assert not (repo_root() / "src" / "mymlfw" / "contrib" / "my_trick.py").exists()


def test_promote_plugin_default_dest_is_package_contrib():
    assert default_contrib_dir() == repo_root() / "src" / "mymlfw" / "contrib"
    init = default_contrib_dir() / "__init__.py"
    assert init.is_file()
    assert "mymlfw.train.lora" not in init.read_text()


def test_token_budget_rejects_1501_tokens(tmp_path):
    with pytest.raises(MymlfwError) as exc:
        ensure_token_budget(" ".join(["tok"] * 1501))
    assert exc.value.error_code == "LLMSTXT_TOO_LONG"
    ensure_token_budget(" ".join(["tok"] * 1500))
    path = tmp_path / "llms.txt"
    original = " ".join(["tok"] * 1490) + "\n"
    path.write_text(original)
    with pytest.raises(MymlfwError) as overflow:
        sync_llms_index(path)
    assert overflow.value.error_code == "LLMSTXT_TOO_LONG"
    assert path.read_text() == original


def test_packaged_resources_match_the_checkout_and_install_fallback(monkeypatch):
    from mymlfw.paths import packaged_root

    packaged = packaged_root()
    root = repo_root()
    assert packaged is not None
    assert (packaged / "llms.txt").read_text() == (root / "llms.txt").read_text()
    for path in sorted((root / "recipes").glob("*.yaml")):
        assert (packaged / "recipes" / path.name).read_text() == path.read_text()
    monkeypatch.setattr("mymlfw.paths.checkout_root", lambda: None)
    assert repo_root() == packaged
    assert "remember" in (repo_root() / "llms.txt").read_text()
    assert "promote-plugin" in (repo_root() / "llms.txt").read_text()
    assert "sync-docs" in (repo_root() / "llms.txt").read_text()


def test_docs_map_links_resolve():
    import re
    from pathlib import Path

    root = repo_root()
    pages = [root / "README.md", root / "AGENTS.md", *sorted((root / "docs").rglob("*.md"))]
    link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    assert pages
    for page in pages:
        for target in link.findall(page.read_text()):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            relative = target.split("#", 1)[0]
            if not relative:
                continue
            assert (page.parent / relative).resolve().is_file(), f"{page} -> {target}"
    assert "docs/index.md" in (root / "README.md").read_text()
    assert "docs docs/index.md" in (root / "llms.txt").read_text()


def test_sync_docs_exits_zero():
    completed = subprocess.run(
        [sys.executable, "-m", "mymlfw", "sync-docs"],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0
    text = (repo_root() / "llms.txt").read_text()
    assert "DO NOT write custom GroupKFold loops" in text
    assert "<!-- mymlfw-index -->" in text
    assert len(text.split()) <= 1500
