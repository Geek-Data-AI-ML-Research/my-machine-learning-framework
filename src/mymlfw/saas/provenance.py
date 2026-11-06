"""License ledger: harvest, compatibility matrix, gates, exports."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterable

from mymlfw.saas.ids import new_credit_id

# Local top-500 stand-in: known permissive + copyleft names (sync path, no network).
TOP_SPDX: dict[str, str] = {
    "numpy": "BSD-3-Clause",
    "pandas": "BSD-3-Clause",
    "scikit-learn": "BSD-3-Clause",
    "scipy": "BSD-3-Clause",
    "lightgbm": "MIT",
    "xgboost": "Apache-2.0",
    "torch": "BSD-3-Clause",
    "transformers": "Apache-2.0",
    "sklearn": "BSD-3-Clause",
}

PERMISSIVE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense"}
COPYLEFT = {"GPL-2.0-only", "GPL-3.0-only", "AGPL-3.0-only", "LGPL-3.0-only"}
NC = {"CC-BY-NC-4.0", "CC-BY-NC-SA-4.0"}
ATTRIBUTION = {"CC-BY-4.0", "CC-BY-SA-4.0"}

_IMPORT_RE = re.compile(r"^(?:import|from)\s+([A-Za-z0-9_\.]+)")


@dataclass
class CreditAsset:
    id: str
    workspace_id: str
    project_id: str
    name: str
    spdx: str
    source: str
    used_in_final_ensemble: bool = False
    authors: list[str] = field(default_factory=list)
    status: str = "OK"
    schema_version: int = 1
    deleted_at: str | None = None

    def to_doc(self) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        return {
            "_id": self.id,
            "id": self.id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "schema_version": self.schema_version,
            "name": self.name,
            "spdx": self.spdx,
            "source": self.source,
            "used_in_final_ensemble": self.used_in_final_ensemble,
            "authors": list(self.authors),
            "status": self.status,
            "created_at": now,
            "updated_at": now,
            "deleted_at": self.deleted_at,
        }


@dataclass
class ProjectLicensePolicy:
    outbound_spdx: str = "MIT"
    enforce_kaggle_commercial_winner_rule: bool = True


def harvest_identifiers_from_source(source: str) -> list[str]:
    names: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        for line in source.splitlines():
            m = _IMPORT_RE.match(line.strip())
            if m:
                names.append(m.group(1).split(".")[0])
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module.split(".")[0])
    return sorted(set(names))


def resolve_spdx(name: str, *, online: dict[str, str] | None = None) -> str:
    key = name.lower()
    if key in TOP_SPDX:
        return TOP_SPDX[key]
    if online and key in online:
        return online[key]
    return "UNVERIFIED_LICENSE"


def evaluate_license_compatibility(
    asset_spdx: str,
    *,
    outbound_spdx: str = "MIT",
    commercial_kaggle: bool = True,
    attributed: bool = True,
) -> str:
    """Return OK | WARN | BLOCKED_NC | BLOCKED_COPYLEFT | MISSING_ATTRIBUTION | UNVERIFIED."""
    spdx = (asset_spdx or "").strip()
    if spdx in {"", "UNVERIFIED_LICENSE"}:
        return "UNVERIFIED"
    if commercial_kaggle and spdx in NC:
        return "BLOCKED_NC"
    if spdx in COPYLEFT and outbound_spdx in PERMISSIVE | {"Proprietary"}:
        return "BLOCKED_COPYLEFT"
    if spdx in ATTRIBUTION and not attributed:
        return "MISSING_ATTRIBUTION"
    if spdx in PERMISSIVE | ATTRIBUTION:
        return "OK"
    return "WARN"


def sync_harvest_on_complete(
    *,
    workspace_id: str,
    project_id: str,
    source: str,
    policy: ProjectLicensePolicy | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fast local SPDX map. Unknowns become UNVERIFIED outbox jobs (caller enqueues)."""
    policy = policy or ProjectLicensePolicy()
    credits: list[dict[str, Any]] = []
    outbox: list[dict[str, Any]] = []
    for name in harvest_identifiers_from_source(source):
        spdx = resolve_spdx(name)
        status = evaluate_license_compatibility(
            spdx,
            outbound_spdx=policy.outbound_spdx,
            commercial_kaggle=policy.enforce_kaggle_commercial_winner_rule,
        )
        asset = CreditAsset(
            id=new_credit_id(),
            workspace_id=workspace_id,
            project_id=project_id,
            name=name,
            spdx=spdx,
            source="ast_harvest",
            status=status,
        )
        credits.append(asset.to_doc())
        if spdx == "UNVERIFIED_LICENSE":
            outbox.append(
                {
                    "event_type": "license.resolve",
                    "payload": {"name": name, "project_id": project_id},
                }
            )
    return credits, outbox


def verify_project_licenses(
    credits: Iterable[dict[str, Any]],
    *,
    gate: str,
) -> dict[str, Any]:
    """Hard gate for kaggle_submit / final promote / submission git export."""
    blocked = [
        c
        for c in credits
        if c.get("used_in_final_ensemble")
        and str(c.get("status") or "").startswith("BLOCKED")
    ]
    if blocked and gate in {"kaggle_submit", "final_promote", "git_export"}:
        return {
            "ok": False,
            "error_code": "disqualification_risk",
            "message": "[CRITICAL: DISQUALIFICATION RISK]",
            "blocked": [c.get("_id") or c.get("id") for c in blocked],
        }
    return {"ok": True, "blocked": []}


def render_provenance_ascii_board(credits: Iterable[dict[str, Any]]) -> str:
    lines = ["CREDITS", "name            spdx              status"]
    for c in credits:
        flag = " !" if str(c.get("status", "")).startswith("BLOCKED") else "  "
        lines.append(
            f"{flag}{str(c.get('name',''))[:14]:<14} {str(c.get('spdx',''))[:16]:<16} {c.get('status')}"
        )
    if any(str(c.get("status", "")).startswith("BLOCKED") and c.get("used_in_final_ensemble") for c in credits):
        lines.append("[CRITICAL: DISQUALIFICATION RISK]")
    return "\n".join(lines)


def export_credits_bundle(credits: Iterable[dict[str, Any]], *, title: str) -> dict[str, str]:
    rows = list(credits)
    credits_md = "# CREDITS\n\n" + "\n".join(
        f"- {c.get('name')} ({c.get('spdx')}) — {', '.join(c.get('authors') or ['unknown'])}"
        for c in rows
    )
    notice = "NOTICE\n\n" + "\n".join(f"{c.get('name')}: {c.get('spdx')}" for c in rows)
    cff = (
        f"cff-version: 1.2.0\ntitle: {title}\n"
        + "\n".join(f"# {c.get('name')} {c.get('spdx')}" for c in rows)
    )
    bib = "\n".join(
        f"@misc{{{c.get('name','asset')},\n  title={{{c.get('name')}}},\n  note={{{c.get('spdx')}}}\n}}"
        for c in rows
    )
    sbom = (
        '{"spdxVersion":"SPDX-2.3","name":"'
        + title
        + '","packages":['
        + ",".join(
            '{"name":"%s","licenseDeclared":"%s"}' % (c.get("name"), c.get("spdx"))
            for c in rows
        )
        + "]}"
    )
    return {
        "CREDITS.md": credits_md,
        "NOTICE.md": notice,
        "CITATION.cff": cff,
        "references.bib": bib,
        "sbom.spdx.json": sbom,
    }


def blocked_ensemble_names(credits: Iterable[dict[str, Any]]) -> set[str]:
    return {
        str(c.get("name"))
        for c in credits
        if str(c.get("status", "")).startswith("BLOCKED") and c.get("used_in_final_ensemble")
    }


def reensemble_excluding_blocked(
    candidates: list[dict[str, Any]],
    credits: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocked_names = blocked_ensemble_names(credits)
    return [row for row in candidates if str(row.get("name")) not in blocked_names]


def scan_credits_online(
    names: list[str],
    *,
    resolver: Any,
    workspace_id: str,
    project_id: str,
    per_minute: int = 6,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rate-limited SPDX lookup. Unknown stays UNVERIFIED and queues outbox."""
    import time

    credits: list[dict[str, Any]] = []
    outbox: list[dict[str, Any]] = []
    start = time.monotonic()
    for idx, name in enumerate(names):
        if idx >= per_minute:
            outbox.append({"event_type": "license.resolve", "payload": {"name": name, "deferred": True}})
            continue
        spdx = str(resolver(name) or "UNVERIFIED_LICENSE")
        status = evaluate_license_compatibility(spdx)
        asset = CreditAsset(
            id=new_credit_id(),
            workspace_id=workspace_id,
            project_id=project_id,
            name=name,
            spdx=spdx,
            source="online_scan",
            status=status,
        )
        credits.append(asset.to_doc())
        if spdx == "UNVERIFIED_LICENSE":
            outbox.append({"event_type": "license.resolve", "payload": {"name": name}})
    _ = start
    return credits, outbox


def reensemble_clean_oofs(
    candidates: list[Any],
    credits: Iterable[dict[str, Any]],
    *,
    y: Any,
    folds: Any,
) -> dict[str, Any]:
    """Drop BLOCKED ensemble assets and re-run nested-CV optimize_ensemble."""
    from mymlfw.saas.ensemble import optimize_ensemble

    blocked = blocked_ensemble_names(credits)
    kept = [c for c in candidates if getattr(c, "name", None) not in blocked]
    if len(kept) < 2:
        return {
            "ok": False,
            "error_code": "need_two_clean_models",
            "excluded": sorted(blocked),
        }
    result = optimize_ensemble(kept, y=y, folds=folds, mode="auto")
    return {
        "ok": True,
        "excluded": sorted(blocked),
        "names": [c.name for c in kept],
        "nested_cv_score": float(result.nested_cv_score),
        "mode": result.mode,
    }
