import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from mymlfw.campaign import register_probe, set_verdict
from mymlfw.errors import MymlfwError
from mymlfw.train.grpo import advantages
from mymlfw.train.lora import lora_dry_run, validate_peft_config


def _bands():
    return dict(expected_band_low=0.1, expected_band_high=0.2, baseline_id="base", variable="lora_r=16")


def test_constant_rewards_have_zero_advantage_and_singleton_group_raises():
    values = advantages([1.5, 1.5, 1.5, 1.5])
    assert values.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert not np.isnan(values).any()
    with pytest.raises(ValueError):
        advantages([1.5])


def test_peft_config_requires_targets_and_warns_on_alpha():
    with pytest.raises(MymlfwError) as error:
        validate_peft_config({"peft_type": "lora", "rank": 8, "lora_alpha": 16, "target_modules": []})
    assert error.value.error_code == "MISSING_TARGETS"
    checked = validate_peft_config({"peft_type": "dora", "rank": 8, "lora_alpha": 4, "target_modules": ["q_proj"]})
    assert checked["warnings"]


def test_dry_run_resumes_pending_and_blocks_a_kill(tmp_path):
    ledger = tmp_path / "experiments.csv"
    train = tmp_path / "train.csv"
    pd.DataFrame({"text": ["a", "b"], "label": ["cat", "dog"]}).to_csv(train, index=False)
    register_probe(ledger, experiment_id="run", note="open", change_count=1, **_bands())
    report = lora_dry_run(
        train, ledger, experiment_id="run", note="open", soft_targets="oof.npz", kl_alpha=0.5, **_bands(),
    )
    assert report["model_loaded"] is False
    assert report["kl_alpha"] == 0.5
    set_verdict(ledger, "run", "kill", note="already killed")
    with pytest.raises(MymlfwError) as error:
        lora_dry_run(train, ledger, experiment_id="run", note="again", **_bands())
    assert error.value.error_code == "DUPLICATE_PROBE"


def test_dry_run_validates_peft_config_before_registering(tmp_path):
    ledger = tmp_path / "experiments.csv"
    train = tmp_path / "train.csv"
    pd.DataFrame({"text": ["a"], "label": ["cat"]}).to_csv(train, index=False)
    bad = tmp_path / "bad.yaml"
    bad.write_text("peft_type: lora\nrank: 8\ntarget_modules: []\n")
    with pytest.raises(MymlfwError) as error:
        lora_dry_run(train, ledger, experiment_id="run", note="open", config=bad, **_bands())
    assert error.value.error_code == "MISSING_TARGETS"
    assert not ledger.exists()
    good = tmp_path / "good.yaml"
    good.write_text("peft_type: lora\nrank: 8\nlora_alpha: 4\ntarget_modules:\n  - q_proj\n")
    report = lora_dry_run(train, ledger, experiment_id="run", note="open", config=good, **_bands())
    assert report["peft"]["warnings"]
    assert report["model_loaded"] is False


def test_grpo_cli_uses_the_reward(tmp_path):
    groups = tmp_path / "groups.json"
    groups.write_text(json.dumps([
        {"exec": 1, "syntax": 1, "heuristic": 0, "penalty": 0},
        {"exec": 0, "syntax": 0, "heuristic": 0, "penalty": 0},
    ]))
    completed = subprocess.run(
        [sys.executable, "-m", "mymlfw", "train", "grpo", "--groups", str(groups)],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["rewards"] == [2.0, 0.0]
    assert payload["advantages"][0] > 0


def test_dry_run_does_not_register_when_columns_are_missing(tmp_path):
    ledger = tmp_path / "experiments.csv"
    train = tmp_path / "train.csv"
    pd.DataFrame({"text": ["a"]}).to_csv(train, index=False)
    with pytest.raises(MymlfwError) as error:
        lora_dry_run(train, ledger, experiment_id="run", note="open", **_bands())
    assert error.value.error_code == "BAD_COLUMNS"
    assert not ledger.exists()


def test_dry_run_cli_records_kl_alpha(tmp_path):
    ledger = tmp_path / "experiments.csv"
    train = tmp_path / "train.csv"
    out = tmp_path / "out"
    pd.DataFrame({"text": ["a"], "label": ["cat"]}).to_csv(train, index=False)
    completed = subprocess.run(
        [
            sys.executable, "-m", "mymlfw", "train", "lora", "--dry-run",
            "--train", str(train), "--ledger", str(ledger),
            "--experiment-id", "run", "--baseline-id", "base",
            "--variable", "lora_r=16", "--band-low", "0.1", "--band-high", "0.2",
            "--soft-targets", "oof.npz", "--kl-alpha", "0.5", "--out", str(out),
        ],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads((out / "dry_run.json").read_text())
    assert report["kl_alpha"] == 0.5
    assert report["model_loaded"] is False


def test_smoke_backward_skips_without_torch():
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    pytest.importorskip("peft")
    from mymlfw.train.lora import smoke_backward

    result = smoke_backward()
    assert np.isfinite(result["loss"])


def test_soup_averages_two_adapters(tmp_path):
    safetensors = pytest.importorskip("safetensors.numpy")
    from mymlfw.train.soup import soup_adapters

    left = tmp_path / "a.safetensors"
    right = tmp_path / "b.safetensors"
    safetensors.save_file({"w": np.array([0.0, 2.0], dtype=np.float32)}, str(left))
    safetensors.save_file({"w": np.array([2.0, 4.0], dtype=np.float32)}, str(right))
    out = soup_adapters([left, right], [0.5, 0.5], tmp_path / "soup")
    blended = safetensors.load_file(str(out))
    assert blended["w"].tolist() == pytest.approx([1.0, 3.0])
    other = tmp_path / "c.safetensors"
    safetensors.save_file({"v": np.array([1.0], dtype=np.float32)}, str(other))
    with pytest.raises(MymlfwError) as error:
        soup_adapters([left, other], [0.5, 0.5], tmp_path / "bad")
    assert error.value.error_code == "SOUP_KEY_MISMATCH"
