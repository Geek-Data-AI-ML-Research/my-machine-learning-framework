"""Preflight reads the ledger and side documents. It does not import blend."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mymlfw.campaign.ledger import load_ledger, set_artifact_sha
from mymlfw.errors import MymlfwError
from mymlfw.submit.checks import check_scale_report


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path) -> dict:
    return json.loads(Path(path).read_text())


def preflight(
    *,
    ledger,
    experiment_id: str,
    artifact,
    gate,
    leak,
    runtime,
    kernel,
    scale_report=None,
    require_scale_report: bool = False,
    min_rows_per_sec: float | None = None,
    previous_hashes=None,
    extra_checks=None,
) -> dict:
    rows = load_ledger(ledger)
    row = next((item for item in rows if item["experiment_id"] == experiment_id), None)
    if row is None:
        raise MymlfwError("UNKNOWN_EXPERIMENT", "Register the probe before preflight.", experiment_id=experiment_id)
    if row["verdict"] in {"kill", "confirmed-large-gap"}:
        raise MymlfwError(
            "PROBE_CLOSED",
            "This probe is already killed or a confirmed CV-LB gap. Register a new variable.",
            verdict=row["verdict"],
            note=row["note"],
        )
    if row["change_count"] != "1":
        raise MymlfwError("SECOND_VARIABLE", "change_count must be 1.", note=row["note"])
    if not row["baseline_id"] or not row["variable"]:
        raise MymlfwError("MISSING_BASELINE", "baseline_id and variable are required.", note=row["note"])
    if row["expected_band_low"] == "" or row["expected_band_high"] == "":
        raise MymlfwError("MISSING_BAND", "Pre-register both band edges.", note=row["note"])
    digest = _sha256(artifact)
    pin_hash = row["artifact_sha256"] == ""
    if row["artifact_sha256"] and row["artifact_sha256"] != digest:
        raise MymlfwError(
            "HASH_MISMATCH",
            "The ledger artifact hash does not match the file.",
            expected=row["artifact_sha256"],
            got=digest,
        )
    for label, path in (("gate", gate), ("leak", leak), ("runtime", runtime)):
        document = _load_json(path)
        recorded = str(document.get("artifact_sha256", ""))
        if recorded != digest:
            raise MymlfwError(
                "HASH_MISMATCH",
                f"{label} artifact hash does not match the submission.",
                file=label,
                expected=digest,
                got=recorded,
            )
    kernel_doc = _load_json(kernel) if not isinstance(kernel, dict) else kernel
    internet = kernel_doc.get("enable_internet", True)
    if str(internet).lower() != "false":
        raise MymlfwError(
            "INTERNET_ENABLED",
            "Set enable_internet to false in kernel-metadata.json.",
            enable_internet=internet,
        )
    if previous_hashes is not None:
        text = Path(previous_hashes).read_text()
        if digest in text:
            raise MymlfwError(
                "DUPLICATE_HASH",
                "This artifact matches a hash that was already scored or killed.",
                sha256=digest,
            )
    if scale_report is None and require_scale_report:
        raise MymlfwError(
            "SCALE_REPORT_REQUIRED",
            "Run python -m mymlfw simulate-test and pass --scale-report.",
        )
    if scale_report is not None:
        report = _load_json(scale_report) if not isinstance(scale_report, dict) else scale_report
        check_scale_report(report, min_rows_per_sec=min_rows_per_sec)
    for check in extra_checks or []:
        check()
    if pin_hash:
        set_artifact_sha(ledger, experiment_id, digest)
    return {"ok": True, "sha256": digest}
