import json
import subprocess
import sys
import warnings

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import balanced_accuracy_score

from mymlfw.campaign import (
    load_ledger,
    profile_dir,
    record_public_score,
    register_probe,
    update_cv,
)
from mymlfw.errors import DuplicateCandidateError, MymlfwError
from mymlfw.metrics import balanced_accuracy, mrr_at_k
from mymlfw.paths import find_data_dir


def _register(path, **overrides):
    payload = dict(
        experiment_id="child",
        baseline_id="base",
        variable="lora_r=16",
        change_count=1,
        expected_band_low=0.30,
        expected_band_high=0.36,
        note="one lever",
    )
    payload.update(overrides)
    return register_probe(path, **payload)


def test_second_variable_and_missing_baseline_are_json(tmp_path):
    ledger = tmp_path / "experiments.csv"
    second = subprocess.run(
        [
            sys.executable, "-m", "mymlfw", "probe", "register",
            "--ledger", str(ledger),
            "--experiment-id", "a",
            "--baseline-id", "base",
            "--variable", "lora_r=16",
            "--change-count", "2",
            "--band-low", "0.1",
            "--band-high", "0.2",
        ],
        check=False, capture_output=True, text=True,
    )
    missing = subprocess.run(
        [
            sys.executable, "-m", "mymlfw", "probe", "register",
            "--ledger", str(ledger),
            "--experiment-id", "a",
            "--variable", "lora_r=16",
            "--band-low", "0.1",
            "--band-high", "0.2",
        ],
        check=False, capture_output=True, text=True,
    )
    for completed, code in ((second, "SECOND_VARIABLE"), (missing, "MISSING_BASELINE")):
        assert completed.returncode == 1
        payload = json.loads(completed.stderr)
        assert payload["error_code"] == code
        assert payload["note"]


def test_pending_resume_and_completed_block(tmp_path):
    ledger = tmp_path / "experiments.csv"
    first = _register(ledger, experiment_id="A")
    again = _register(ledger, experiment_id="A")
    assert again["experiment_id"] == first["experiment_id"]
    assert len(load_ledger(ledger)) == 1
    with pytest.raises(MymlfwError) as blocked:
        _register(ledger, experiment_id="B")
    assert blocked.value.error_code == "DUPLICATE_PROBE"
    from mymlfw.campaign import set_verdict

    set_verdict(ledger, "A", "kill", note="lora_r=16 already died")
    with pytest.raises(MymlfwError) as killed:
        _register(ledger, experiment_id="A")
    assert killed.value.error_code == "DUPLICATE_PROBE"
    assert "died" in killed.value.fields["note"]


def test_cv_delta_and_large_gap(tmp_path):
    ledger = tmp_path / "experiments.csv"
    _register(ledger, experiment_id="base", baseline_id="origin", variable="root", expected_band_low=0.2, expected_band_high=0.5)
    update_cv(ledger, "base", 0.35)
    _register(ledger, experiment_id="child", baseline_id="base")
    row = update_cv(ledger, "child", 0.40)
    assert row["public_score"] == ""
    assert float(row["cv_delta"]) == pytest.approx(0.05)
    scored = record_public_score(ledger, "child", 0.20)
    assert float(scored["cv_lb_gap"]) == pytest.approx(0.20)
    assert scored["suggested_verdict"] == "confirmed-large-gap"
    assert scored["verdict"] == "confirmed-large-gap"


def test_probe_identity_survives_rounding_and_ids_stay_unique(tmp_path):
    ledger = tmp_path / "experiments.csv"
    register_probe(
        ledger, experiment_id="A", baseline_id="base", variable="v",
        expected_band_low=0.1 + 0.2, expected_band_high=0.4, note="once",
    )
    register_probe(
        ledger, experiment_id="A", baseline_id="base", variable="v",
        expected_band_low=0.1 + 0.2, expected_band_high=0.4, note="once",
    )
    assert len(load_ledger(ledger)) == 1
    with pytest.raises(MymlfwError) as error:
        register_probe(
            ledger, experiment_id="A", baseline_id="base", variable="other",
            expected_band_low=0.1, expected_band_high=0.2, note="other",
        )
    assert error.value.error_code == "DUPLICATE_EXPERIMENT"


def test_mrr_rejects_duplicate_candidates_and_a_short_truth_list():
    with pytest.raises(DuplicateCandidateError):
        mrr_at_k(["cand_A", "cand_A", "cand_B"], "cand_B")
    with pytest.raises(MymlfwError) as error:
        mrr_at_k([["a"], ["b"], ["c"]], ["a", "b"])
    assert error.value.error_code == "MRR_LENGTH"


def test_balanced_accuracy_keeps_a_missing_class_in_the_denominator():
    y_true = np.array([0, 1, 1])
    y_pred = np.array([0, 0, 1])
    classes = [0, 1, 2]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        got = balanced_accuracy(y_true, y_pred, classes)
    # Class 2 has no true rows. It still counts as recall 0, so the mean is 0.5.
    assert got == pytest.approx((1.0 + 0.5 + 0.0) / 3)
    assert not caught
    present_only = balanced_accuracy_score(y_true, y_pred)
    assert got != pytest.approx(present_only)


def test_profile_names_id_group_balance_and_schema(tmp_path):
    train = pd.DataFrame(
        {
            "id": [f"r{i}" for i in range(20)],
            "prompt_id": [f"g{i // 4}" for i in range(20)],
            "label": ["a"] * 16 + ["b"] * 4,
            "text": [f"word {i} " + ("x" * (i + 1)) for i in range(20)],
        }
    )
    test = pd.DataFrame({"id": ["t0"], "prompt_id": ["g0"], "text": ["z"], "extra": [1]})
    train.to_csv(tmp_path / "train.csv", index=False)
    test.to_csv(tmp_path / "test.csv", index=False)
    profile = profile_dir(tmp_path).read_text()
    for heading in ("## rows", "## columns", "## id_candidates", "## group_candidates", "## target_balance", "## text_length", "## schema_diff"):
        assert heading in profile
    assert "id" in profile.split("## id_candidates")[1].split("##")[0]
    assert "prompt_id (5)" in profile
    assert "max/min=" in profile
    assert "p50=" in profile
    assert "label" in profile.split("## schema_diff")[1]
    assert "extra" in profile.split("## schema_diff")[1]
    assert profile.index("## recommended") < profile.index("## rows")
    recommended = profile.split("## recommended", 1)[1].split("## rows", 1)[0]
    assert "closed-set-llm-id" not in recommended
    first = next(line for line in recommended.splitlines() if line.startswith("- "))
    assert first.startswith("- grouped-text:")


def test_profile_recommends_closed_set_for_many_classes(tmp_path):
    rows = 20
    train = pd.DataFrame(
        {
            "id": [f"r{i}" for i in range(rows)],
            "prompt_id": [f"g{i % 5}" for i in range(rows)],
            "label": [f"c{i % 10}" for i in range(rows)],
            "text": [f"word {i} " + ("x" * (i + 20)) for i in range(rows)],
        }
    )
    train.to_csv(tmp_path / "train.csv", index=False)
    profile = profile_dir(tmp_path).read_text()
    recommended = profile.split("## recommended", 1)[1].split("## rows", 1)[0]
    first = next(line for line in recommended.splitlines() if line.startswith("- "))
    assert first.startswith("- closed-set-llm-id:")


def test_profile_resolves_a_data_dir_when_the_folder_has_no_table(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    empty = tmp_path / "empty"
    empty.mkdir()
    pd.DataFrame({"id": ["a"], "text": ["hello there"], "label": ["a"]}).to_csv(data / "train.csv", index=False)

    def _resolve(local, required=("train.csv", "test.csv")):
        return data

    monkeypatch.setattr("mymlfw.paths.resolve_data_dir", _resolve)
    text = profile_dir(empty).read_text()
    assert "train=1" in text


def test_probe_update_cv_cli_writes_the_ledger(tmp_path):
    ledger = tmp_path / "experiments.csv"
    _register(ledger, experiment_id="base", baseline_id="origin", variable="root", expected_band_low=0.0, expected_band_high=1.0)
    _register(ledger, experiment_id="child")
    completed = subprocess.run(
        [
            sys.executable, "-m", "mymlfw", "probe", "update-cv",
            "--ledger", str(ledger), "--experiment-id", "base", "--cv-mean", "0.35",
        ],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    completed = subprocess.run(
        [
            sys.executable, "-m", "mymlfw", "probe", "update-cv",
            "--ledger", str(ledger), "--experiment-id", "child", "--cv-mean", "0.40",
        ],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert float(payload["cv_delta"]) == pytest.approx(0.05)


def test_profile_reads_a_parquet_training_table(tmp_path):
    frame = pd.DataFrame({
        "id": ["a", "b"],
        "text": ["hello there", "another note"],
        "label": ["a", "b"],
    })
    frame.to_parquet(tmp_path / "train.parquet")
    text = profile_dir(tmp_path).read_text()
    assert "train=2" in text
    assert "## recommended" in text


def test_find_data_dir_requires_expected_files(tmp_path):
    (tmp_path / "train.csv").write_text("id\n1\n")
    (tmp_path / "test.csv").write_text("id\n2\n")
    assert find_data_dir([tmp_path / "missing", tmp_path]) == tmp_path
    with pytest.raises(MymlfwError):
        find_data_dir([tmp_path / "missing"])
