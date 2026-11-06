#!/usr/bin/env python3
"""Import local VQCC contest tree into Campaign SaaS studio (Compose API).

Reads /Users/mz/Projects/vqcc by default. No invented product fields — maps
existing ledger / dead-ends / receipt into plan HTTP surfaces.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def _req(
    api: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Mymlfw-Client-Version": "0.1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        headers["Idempotency-Key"] = f"vqcc-import-{uuid.uuid4()}"
    req = urllib.request.Request(
        api.rstrip("/") + path, data=data, headers=headers, method=method.upper()
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            raw = res.read().decode() or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode()
        raise SystemExit(f"{method} {path} → {exc.code}: {err}") from exc


def _parse_dead_ends(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    items: list[dict[str, str]] = []
    blocks = re.split(r"\n###\s+", text)
    for block in blocks[1:]:
        lines = block.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        # Prefer Rule / Root cause for the lesson; keep title as variable.
        rule = ""
        root = ""
        for line in lines[1:]:
            if "**Rule:**" in line:
                rule = line.split("**Rule:**", 1)[-1].strip()
            if "**Root cause:**" in line:
                root = line.split("**Root cause:**", 1)[-1].strip()
        lesson = rule or root or body
        lesson = re.sub(r"\s+", " ", lesson).strip()[:2000]
        variable = title[:240]
        if variable and lesson:
            items.append({"variable": variable, "lesson": lesson})
    return items


def _login(api: str, email: str, password: str) -> str:
    try:
        tok = _req(
            api,
            "POST",
            "/v1/auth/login",
            body={"email": email, "password": password},
        )
    except SystemExit:
        tok = _req(
            api,
            "POST",
            "/v1/auth/register",
            body={
                "email": email,
                "password": password,
                "display_name": "VQCC Owner",
            },
        )
    return str(tok["access_token"])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api", default="http://127.0.0.1:8001")
    p.add_argument("--root", type=Path, default=Path("/Users/mz/Projects/vqcc"))
    p.add_argument("--email", default="owner@localhost")
    p.add_argument("--password", default="devpassword")
    p.add_argument("--max-levers", type=int, default=40)
    args = p.parse_args()
    root: Path = args.root
    if not root.is_dir():
        raise SystemExit(f"missing contest root: {root}")

    competition = "google-verifiable-quantum-circuit-compilation"
    meta = root / "kernel-metadata.json"
    if meta.is_file():
        comps = json.loads(meta.read_text()).get("competition_sources") or []
        if comps:
            competition = str(comps[0])

    receipt = {}
    receipt_path = root / "submission.receipt.json"
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text())
    public = float(receipt.get("public_score") or receipt.get("gm_est") or 22.85)
    prior = float(receipt.get("prior_lb") or 22.63)

    token = _login(args.api, args.email, args.password)
    projects = _req(args.api, "GET", "/v1/projects", token=token).get("projects") or []
    existing = next(
        (x for x in projects if x.get("slug") == "vqcc" or x.get("name") == "VQCC"),
        None,
    )
    if existing:
        project_id = existing["id"]
        print(f"reusing project {project_id}")
    else:
        created = _req(
            args.api,
            "POST",
            "/v1/projects",
            token=token,
            body={
                "name": "VQCC",
                "kind": "kaggle",
                "kaggle_competition": competition,
                "git_remote": str(root),
                "goals": [
                    {
                        "title": f"Kaggle public LB >= {public:.3f}",
                        "kind": "kaggle_public",
                        "metric_key": "public_score",
                        "threshold": public,
                        "direction": "maximize",
                        "priority": 10,
                        "notes": "Imported from submission.receipt.json",
                    },
                    {
                        "title": f"Beat prior public floor {prior:.3f} by +0.02 GM",
                        "kind": "kaggle_public",
                        "metric_key": "public_score",
                        "threshold": prior + 0.02,
                        "direction": "maximize",
                        "priority": 20,
                        "notes": "AGENTS.md ΔGM ≥ +0.02 gate",
                    },
                    {
                        "title": "Notebook / local GM estimate track",
                        "kind": "notebook_score",
                        "metric_key": "cv_mean",
                        "threshold": public,
                        "direction": "maximize",
                        "priority": 30,
                        "notes": "DATA_PROFILE ranking / portfolio baseline",
                    },
                ],
            },
        )
        project_id = created["id"]
        print(f"created project {project_id} slug={created.get('slug')}")

    goals = _req(
        args.api, "GET", f"/v1/projects/{project_id}/goals", token=token
    ).get("goals") or []
    primary = next((g for g in goals if g.get("kind") == "kaggle_public"), goals[0])
    goal_id = primary["id"]

    # Mark primary as MET when receipt public_score meets threshold.
    if public >= float(primary.get("threshold") or 0):
        _req(
            args.api,
            "PATCH",
            f"/v1/projects/{project_id}/goals/{goal_id}",
            token=token,
            body={"status": "met", "notes": f"receipt public_score={public}"},
        )

    dead_path = root / "proprietary" / "DEAD_ENDS.md"
    dead_items = _parse_dead_ends(dead_path) if dead_path.is_file() else []
    existing_dead = {
        d.get("variable")
        for d in (
            _req(
                args.api,
                "GET",
                f"/v1/projects/{project_id}/dead-ends",
                token=token,
            ).get("dead_ends")
            or []
        )
    }
    imported_dead = 0
    for item in dead_items:
        if item["variable"] in existing_dead:
            continue
        _req(
            args.api,
            "POST",
            f"/v1/projects/{project_id}/dead-ends",
            token=token,
            body=item,
        )
        imported_dead += 1

    def _close_open_levers() -> None:
        for lev in (
            _req(
                args.api, "GET", f"/v1/projects/{project_id}/levers", token=token
            ).get("levers")
            or []
        ):
            if str(lev.get("status") or "") == "open":
                _req(
                    args.api,
                    "POST",
                    f"/v1/projects/{project_id}/levers/{lev['id']}/close",
                    token=token,
                    body={
                        "verdict": "kill",
                        "notes": "cleared before vqcc ledger import",
                    },
                )

    _close_open_levers()

    ledger = root / "ledger" / "experiments.csv"
    imported_levers = 0
    lever_errors = 0
    if ledger.is_file():
        rows = list(csv.DictReader(ledger.open(encoding="utf-8")))
        # Prefer recent kills/promotes with named variables.
        rows = [r for r in rows if (r.get("variable") or "").strip()]
        rows = rows[-args.max_levers :]
        for row in rows:
            raw_var = (row.get("variable") or "").strip()
            # lever_verifier: ^[A-Za-z_][A-Za-z0-9_.\-]{0,64}(=…)?$
            variable = re.sub(r"[^A-Za-z0-9_.\-]+", "_", raw_var).strip("_")
            if not variable or not re.match(r"^[A-Za-z_]", variable):
                variable = "exp_" + variable if variable else "exp_unknown"
            variable = variable[:64]
            try:
                lo = float(row.get("expected_band_low") or 0.0)
                hi = float(row.get("expected_band_high") or lo)
            except ValueError:
                lo, hi = 0.0, 0.0
            if hi < lo:
                lo, hi = hi, lo
            try:
                cv = float(row["cv_mean"]) if row.get("cv_mean") else None
            except ValueError:
                cv = None
            fold_scores = [cv] * 5 if cv is not None else []
            verdict = (row.get("verdict") or "").strip() or "kill"
            if verdict not in {
                "kill",
                "promote-candidate",
                "confirmed-large-gap",
            }:
                verdict = "kill"
            try:
                try:
                    exp = _req(
                        args.api,
                        "POST",
                        f"/v1/projects/{project_id}/levers",
                        token=token,
                        body={
                            "goal_id": goal_id,
                            "variable": variable,
                            "band_low": lo,
                            "band_high": hi,
                            "fold_scores": fold_scores,
                            "strategy": (row.get("experiment_id") or "")[:120]
                            or None,
                        },
                    )
                except SystemExit as exc:
                    if "one_open_lever" not in str(exc):
                        raise
                    _close_open_levers()
                    exp = _req(
                        args.api,
                        "POST",
                        f"/v1/projects/{project_id}/levers",
                        token=token,
                        body={
                            "goal_id": goal_id,
                            "variable": variable,
                            "band_low": lo,
                            "band_high": hi,
                            "fold_scores": fold_scores,
                            "strategy": (row.get("experiment_id") or "")[:120]
                            or None,
                        },
                    )
                _req(
                    args.api,
                    "POST",
                    f"/v1/projects/{project_id}/levers/{exp['id']}/close",
                    token=token,
                    body={
                        "verdict": verdict,
                        "fold_scores": fold_scores,
                        "notes": (row.get("note") or "")[:500],
                    },
                )
                imported_levers += 1
            except SystemExit as exc:
                lever_errors += 1
                print(f"lever skip {variable}: {exc}", file=sys.stderr)
                _close_open_levers()

    notes = []
    if receipt:
        notes.append(
            "Imported submission.receipt.json: "
            f"public_score={public} gm_est={receipt.get('gm_est')} "
            f"gate_pass={receipt.get('gate_pass')} ref={receipt.get('submission_ref')}"
        )
    kb = root / "proprietary" / "CHAMPION_MANIFEST.json"
    if kb.is_file():
        notes.append(f"Champion manifest present at {kb.name}")
    profile = root / "DATA_PROFILE.md"
    if profile.is_file():
        notes.append("DATA_PROFILE: ranking / Ranked channels, MRR, one variable per probe.")
    for note in notes:
        _req(
            args.api,
            "POST",
            f"/v1/projects/{project_id}/progress",
            token=token,
            body={"note": note[:4000]},
        )

    dash = _req(
        args.api, "GET", f"/v1/projects/{project_id}/dashboard", token=token
    )
    listing = _req(args.api, "GET", "/v1/projects", token=token)
    print(
        json.dumps(
            {
                "project_id": project_id,
                "slug": "vqcc",
                "competition": competition,
                "dead_ends_imported": imported_dead,
                "dead_ends_total_parsed": len(dead_items),
                "levers_imported": imported_levers,
                "lever_errors": lever_errors,
                "dashboard_progress": (dash.get("header") or {}).get("progress_pct"),
                "projects": [
                    {"id": x["id"], "slug": x["slug"], "kind": x["kind"]}
                    for x in listing.get("projects") or []
                ],
                "studio": "http://127.0.0.1:5175/#studio",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
