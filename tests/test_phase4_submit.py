import hashlib
import json
import subprocess
import sys

import numpy as np
import pandas as pd

from mymlfw.campaign import load_ledger, register_probe, save_ledger, set_artifact_sha, set_verdict
from mymlfw.errors import MymlfwError
from mymlfw.sanitize import guard_row
from mymlfw.submit import check_id_label, check_ranked_topk, check_scale_report, preflight, zip_bundle


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ready(directory, internet=False):
    directory = directory if hasattr(directory, "mkdir") else directory
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / "submission.parquet"
    pd.DataFrame({"id": ["1"], "model": ["a"]}).to_parquet(artifact)
    digest = _sha(artifact)
    ledger = directory / "experiments.csv"
    register_probe(
        ledger,
        experiment_id="probe",
        baseline_id="base",
        variable="one",
        expected_band_low=0.1,
        expected_band_high=0.2,
        note="ready",
    )
    set_artifact_sha(ledger, "probe", digest)
    side = {"artifact_sha256": digest}
    for name in ("gate", "leak", "runtime"):
        (directory / f"{name}.json").write_text(json.dumps(side))
    kernel = {"enable_internet": internet, "enable_gpu": True}
    (directory / "kernel.json").write_text(json.dumps(kernel))
    return {
        "ledger": ledger,
        "experiment_id": "probe",
        "artifact": artifact,
        "gate": directory / "gate.json",
        "leak": directory / "leak.json",
        "runtime": directory / "runtime.json",
        "kernel": directory / "kernel.json",
    }


def test_preflight_rejects_internet_hash_mismatch_and_duplicates(tmp_path):
    online = _ready(tmp_path / "online", internet=True)
    pytest_raises_code(lambda: preflight(**online), "INTERNET_ENABLED")
    mismatched = _ready(tmp_path / "mismatch")
    gate = json.loads(mismatched["gate"].read_text())
    gate["artifact_sha256"] = "0" * 64
    mismatched["gate"].write_text(json.dumps(gate))
    pytest_raises_code(lambda: preflight(**mismatched), "HASH_MISMATCH")
    duplicated = _ready(tmp_path / "dup")
    previous = tmp_path / "dup" / "previous.txt"
    previous.write_text(_sha(duplicated["artifact"]))
    pytest_raises_code(lambda: preflight(**duplicated, previous_hashes=previous), "DUPLICATE_HASH")


def test_preflight_cli_emits_json(tmp_path):
    kwargs = _ready(tmp_path, internet=True)
    completed = subprocess.run(
        [sys.executable, "-m", "mymlfw", "preflight",
         "--ledger", str(kwargs["ledger"]),
         "--experiment-id", "probe",
         "--artifact", str(kwargs["artifact"]),
         "--gate", str(kwargs["gate"]),
         "--leak", str(kwargs["leak"]),
         "--runtime", str(kwargs["runtime"]),
         "--kernel", str(kwargs["kernel"])],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 1
    assert json.loads(completed.stderr)["error_code"] == "INTERNET_ENABLED"


def test_zip_is_reproducible_and_drops_secrets(tmp_path):
    source = tmp_path / "agent"
    source.mkdir()
    (source / "b.txt").write_text("b")
    (source / "a.txt").write_text("a")
    (source / ".env").write_text("SECRET")
    (source / "credentials.json").write_text("{}")
    (source / "Secret.txt").write_text("nope")
    (source / "id_rsa").write_text("key")
    first = zip_bundle(source, tmp_path / "one.zip")
    second = zip_bundle(source, tmp_path / "two.zip")
    assert first["sha256"] == second["sha256"]
    assert ".env" not in first["members"]
    assert "credentials.json" not in first["members"]
    assert "Secret.txt" not in first["members"]
    assert "id_rsa" not in first["members"]
    assert list(first["members"]) == ["a.txt", "b.txt"]


def test_guard_row_keeps_a_crashing_id(tmp_path):
    def predict(row):
        if row["id"] == "b":
            raise RuntimeError("boom")
        return np.array([0.0, -1.0])

    rows = [{"id": item} for item in ("a", "b", "c")]
    values, crashed = guard_row(["a", "b", "c"], ["x", "y"], rows, predict, tmp_path / "sanitized_rows.json")
    assert values.shape == (3, 2)
    assert crashed == ["b"]
    assert json.loads((tmp_path / "sanitized_rows.json").read_text())["ids"] == ["b"]


def test_guard_row_replaces_a_non_finite_prediction(tmp_path):
    def predict(row):
        if row["id"] == "b":
            return np.array([np.nan, 0.0])
        return np.array([0.0, -1.0])

    rows = [{"id": item} for item in ("a", "b")]
    values, crashed = guard_row(["a", "b"], ["x", "y"], rows, predict, tmp_path / "sanitized_rows.json")
    assert crashed == ["b"]
    assert np.allclose(values[1], np.log(0.5))


def test_preflight_pins_an_empty_hash_and_blocks_a_closed_probe(tmp_path):
    ready = _ready(tmp_path / "pin")
    rows = load_ledger(ready["ledger"])
    rows[0]["artifact_sha256"] = ""
    save_ledger(ready["ledger"], rows)
    result = preflight(**ready)
    assert result["ok"] is True
    assert load_ledger(ready["ledger"])[0]["artifact_sha256"] == result["sha256"]
    ready["artifact"].write_bytes(b"changed")
    pytest_raises_code(lambda: preflight(**ready), "HASH_MISMATCH")
    closed = _ready(tmp_path / "closed")
    set_verdict(closed["ledger"], "probe", "kill", note="stop")
    pytest_raises_code(lambda: preflight(**closed), "PROBE_CLOSED")


def test_scale_report_limits():
    pytest_raises_code(
        lambda: check_scale_report({"projected_seconds": 9 * 3600, "rows_per_sec": 10}),
        "SCALE_TOO_SLOW",
    )
    assert check_scale_report({"projected_seconds": 3600, "rows_per_sec": 10})["projected_seconds"] == 3600


def test_column_contracts():
    frame = pd.DataFrame({"id": ["1", "2"], "model": ["a", "b"]})
    check_id_label(frame, "model", ["a", "b"])
    ranked = pd.DataFrame({"id": ["1"], "candidates": ["a;b"]})
    check_ranked_topk(ranked, max_k=2)


def test_submit_import_does_not_load_blend():
    script = "import sys, mymlfw.submit; assert 'mymlfw.blend' not in sys.modules"
    subprocess.check_call([sys.executable, "-c", script])


def pytest_raises_code(fn, code):
    try:
        fn()
    except MymlfwError as exc:
        assert exc.error_code == code
        return
    raise AssertionError(f"{code} was not raised")
