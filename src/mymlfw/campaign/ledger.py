"""Ledger columns and the one-variable probe guard."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

from mymlfw.errors import MymlfwError

COLUMNS = [
    "date",
    "experiment_id",
    "baseline_id",
    "variable",
    "change_count",
    "cv_mean",
    "cv_std",
    "cv_delta",
    "expected_band_low",
    "expected_band_high",
    "public_score",
    "cv_lb_gap",
    "artifact_sha256",
    "verdict",
    "note",
]

COMPLETED = {"kill", "promote-candidate", "confirmed-large-gap"}


def _fmt(value) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.10g}"


def probe_key(variable: str, low, high) -> str:
    """Identity of a probe. Bands use the same text the ledger stores."""
    payload = {
        "expected_band_high": _fmt(high),
        "expected_band_low": _fmt(low),
        "variable": str(variable),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _blank() -> dict:
    return {column: "" for column in COLUMNS}


def load_ledger(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            row = _blank()
            for column in COLUMNS:
                row[column] = "" if raw.get(column) is None else str(raw.get(column, ""))
            rows.append(row)
        return rows


def save_ledger(path: Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})


def _row_key(row: dict) -> str:
    return probe_key(row["variable"], row["expected_band_low"], row["expected_band_high"])


def _num(value: str):
    if value is None or value == "":
        return None
    return float(value)


def register_probe(
    path,
    *,
    experiment_id: str,
    baseline_id: str,
    variable: str,
    change_count: int = 1,
    expected_band_low: float,
    expected_band_high: float,
    note: str = "",
    when: str | None = None,
) -> dict:
    if not baseline_id:
        raise MymlfwError(
            "MISSING_BASELINE",
            "Pass baseline_id of the row this probe changes.",
            note="baseline_id is required",
        )
    if not variable:
        raise MymlfwError(
            "MISSING_VARIABLE",
            "Name the single variable this probe changes.",
            note="variable is required",
        )
    if int(change_count) != 1:
        raise MymlfwError(
            "SECOND_VARIABLE",
            "A probe changes exactly one variable.",
            note="change_count must be 1",
            change_count=int(change_count),
        )
    if expected_band_low is None or expected_band_high is None:
        raise MymlfwError(
            "MISSING_BAND",
            "Pre-register expected_band_low and expected_band_high.",
            note="bands are required before a submit",
        )
    path = Path(path)
    rows = load_ledger(path)
    key = probe_key(variable, expected_band_low, expected_band_high)
    for row in rows:
        if row["experiment_id"] == experiment_id and _row_key(row) != key:
            raise MymlfwError(
                "DUPLICATE_EXPERIMENT",
                "Choose a new experiment_id. This id already belongs to another probe.",
                experiment_id=experiment_id,
                variable=row["variable"],
                note=row["note"],
            )
    for row in rows:
        if _row_key(row) != key:
            continue
        if row["verdict"] == "pending" and row["experiment_id"] == experiment_id:
            return row
        raise MymlfwError(
            "DUPLICATE_PROBE",
            "Change the variable string to retry. Completed and in-flight probes are blocked.",
            note=row["note"],
            verdict=row["verdict"],
            experiment_id=row["experiment_id"],
        )
    row = _blank()
    row.update(
        {
            "date": when or date.today().isoformat(),
            "experiment_id": experiment_id,
            "baseline_id": baseline_id,
            "variable": variable,
            "change_count": "1",
            "expected_band_low": _fmt(expected_band_low),
            "expected_band_high": _fmt(expected_band_high),
            "verdict": "pending",
            "note": note,
        }
    )
    rows.append(row)
    save_ledger(path, rows)
    return row


def _recompute_delta(rows: list[dict], row: dict) -> None:
    own = _num(row["cv_mean"])
    baseline = next((item for item in rows if item["experiment_id"] == row["baseline_id"]), None)
    base = _num(baseline["cv_mean"]) if baseline else None
    if own is None or base is None:
        row["cv_delta"] = ""
        return
    row["cv_delta"] = _fmt(own - base)


def update_cv(path, experiment_id: str, cv_mean: float, cv_std: float | None = None) -> dict:
    path = Path(path)
    rows = load_ledger(path)
    row = _require(rows, experiment_id)
    row["cv_mean"] = _fmt(cv_mean)
    if cv_std is not None:
        row["cv_std"] = _fmt(cv_std)
    _recompute_delta(rows, row)
    for other in rows:
        if other["baseline_id"] == experiment_id and other["cv_mean"] != "":
            _recompute_delta(rows, other)
    save_ledger(path, rows)
    return row


def suggest_verdict(row: dict) -> str:
    public = _num(row.get("public_score", ""))
    low = _num(row.get("expected_band_low", ""))
    high = _num(row.get("expected_band_high", ""))
    if public is None or low is None or high is None:
        return row.get("verdict") or "pending"
    if public < low or public > high:
        return "confirmed-large-gap"
    return row.get("verdict") or "pending"


def record_public_score(path, experiment_id: str, public_score: float) -> dict:
    path = Path(path)
    rows = load_ledger(path)
    row = _require(rows, experiment_id)
    row["public_score"] = _fmt(public_score)
    cv_mean = _num(row["cv_mean"])
    if cv_mean is not None:
        row["cv_lb_gap"] = _fmt(abs(cv_mean - float(public_score)))
    suggestion = suggest_verdict(row)
    if suggestion == "confirmed-large-gap":
        row["verdict"] = suggestion
    save_ledger(path, rows)
    row["suggested_verdict"] = suggestion
    return row


def set_verdict(path, experiment_id: str, verdict: str, note: str | None = None) -> dict:
    if verdict not in COMPLETED | {"pending"}:
        raise MymlfwError(
            "BAD_VERDICT",
            "Use pending, kill, promote-candidate, or confirmed-large-gap.",
            verdict=verdict,
        )
    path = Path(path)
    rows = load_ledger(path)
    row = _require(rows, experiment_id)
    row["verdict"] = verdict
    if note is not None:
        row["note"] = note
    save_ledger(path, rows)
    return row


def set_artifact_sha(path, experiment_id: str, digest: str) -> dict:
    path = Path(path)
    rows = load_ledger(path)
    row = _require(rows, experiment_id)
    row["artifact_sha256"] = digest
    save_ledger(path, rows)
    return row


def _require(rows: list[dict], experiment_id: str) -> dict:
    for row in rows:
        if row["experiment_id"] == experiment_id:
            return row
    raise MymlfwError(
        "UNKNOWN_EXPERIMENT",
        "Register the probe before updating it.",
        experiment_id=experiment_id,
    )
