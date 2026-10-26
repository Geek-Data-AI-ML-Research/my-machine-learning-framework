import json

import pytest

from mymlfw.campaign import load_ledger, set_verdict
from mymlfw.cloud import JobSpec, render_launch
from mymlfw.errors import MymlfwError


def _spec(experiment_id="job"):
    return JobSpec(
        project="demo",
        role="primary",
        gpu="T4",
        command="python train.py",
        idle_kill_minutes=30,
        max_runtime_minutes=120,
        experiment_id=experiment_id,
        baseline_id="base",
        variable="lora_r=16",
        expected_band_low=0.1,
        expected_band_high=0.2,
        note="cloud",
    )


def test_missing_approval_is_json():
    with pytest.raises(MymlfwError) as error:
        render_launch(_spec(), "/tmp/unused.csv", env={})
    assert error.value.error_code == "CLOUD_APPROVAL_MISSING"


def test_launch_script_has_tags_and_no_secrets(tmp_path):
    ledger = tmp_path / "experiments.csv"
    script = render_launch(_spec(), ledger, env={"CLOUD_APPROVAL": "yes"})
    assert "project=demo" in script
    assert "env=kaggle" in script
    assert "shutdown -h +120" in script
    assert "AKIA" not in script
    assert "i-" not in script
    again = render_launch(_spec(), ledger, env={"CLOUD_APPROVAL": "yes"})
    assert "shutdown -h +120" in again
    rows = load_ledger(ledger)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "pending"


def test_cloud_launch_cli_writes_the_rendered_script(tmp_path):
    import os
    import subprocess
    import sys

    ledger = tmp_path / "experiments.csv"
    out = tmp_path / "rendered.sh"
    completed = subprocess.run(
        [
            sys.executable, "-m", "mymlfw", "cloud", "launch",
            "--project", "demo", "--role", "primary", "--gpu", "T4",
            "--command", "python train.py",
            "--idle-kill", "30", "--max-runtime", "120",
            "--ledger", str(ledger),
            "--experiment-id", "job", "--baseline-id", "base",
            "--variable", "lora_r=16", "--band-low", "0.1", "--band-high", "0.2",
            "--out", str(out),
        ],
        check=False, capture_output=True, text=True,
        env={**os.environ, "CLOUD_APPROVAL": "yes"},
    )
    assert completed.returncode == 0, completed.stderr
    script = out.read_text()
    assert "project=demo" in script
    assert "env=kaggle" in script
    assert "shutdown -h +120" in script
    assert "AKIA" not in script
    assert "i-" not in script
    assert len(load_ledger(ledger)) == 1


def test_launch_rejects_a_newline_before_it_writes_the_ledger(tmp_path):
    spec = _spec()
    spec.project = "demo\ntouch owned"
    with pytest.raises(MymlfwError) as error:
        render_launch(spec, tmp_path / "experiments.csv", env={"CLOUD_APPROVAL": "yes"})
    assert error.value.error_code == "BAD_SHELL_FIELD"
    assert not (tmp_path / "experiments.csv").exists()


def test_killed_probe_blocks_rendering(tmp_path):
    ledger = tmp_path / "experiments.csv"
    render_launch(_spec("dead"), ledger, env={"CLOUD_APPROVAL": "yes"})
    set_verdict(ledger, "dead", "kill", note="do not rerun")
    with pytest.raises(MymlfwError) as error:
        render_launch(_spec("other"), ledger, env={"CLOUD_APPROVAL": "yes"})
    assert error.value.error_code == "DUPLICATE_PROBE"
    assert json.dumps(error.value.to_dict())
