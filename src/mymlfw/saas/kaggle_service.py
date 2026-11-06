"""Kaggle intel, package, rate limit, verify-public-notebook sandbox gate."""

from __future__ import annotations

import ast
import time
from collections import defaultdict
from typing import Any

from mymlfw.saas.ids import new_credit_id, new_mission_id
from mymlfw.saas.sanitize import spotlight_untrusted

_HITS: dict[str, list[float]] = defaultdict(list)
_FAILS: dict[str, int] = defaultdict(int)


def reset_kaggle_limits_for_tests() -> None:
    _HITS.clear()
    _FAILS.clear()


def rate_limit(client_ip: str, *, per_minute: int = 30) -> None:
    from mymlfw.saas.redis_control import kaggle_rate_limit_redis

    if _FAILS[client_ip] >= 5:
        raise RuntimeError("kaggle_circuit_open")
    allowed = kaggle_rate_limit_redis(client_ip, per_minute=per_minute)
    if allowed is False:
        _FAILS[client_ip] += 1
        raise RuntimeError("kaggle_rate_limited")
    if allowed is True:
        return
    now = time.time()
    hits = [t for t in _HITS[client_ip] if now - t < 60]
    if len(hits) >= per_minute:
        _FAILS[client_ip] += 1
        raise RuntimeError("kaggle_rate_limited")
    hits.append(now)
    _HITS[client_ip] = hits


_INTEL_CACHE: dict[str, dict[str, Any]] = {}


def refresh_intel_cache(
    *,
    competition: str,
    discussions: list[dict[str, Any]] | None = None,
    kernels: list[dict[str, Any]] | None = None,
    my_kernels: list[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
    files: list[dict[str, Any]] | None = None,
    submissions: list[dict[str, Any]] | None = None,
    leaderboard: list[dict[str, Any]] | None = None,
    rank: int | None = None,
    public_score: float | None = None,
    final2_refs: list[Any] | None = None,
    refreshed_by: str = "worker",
) -> dict[str, Any]:
    """Write intel cache (worker or live Kaggle sync)."""
    from datetime import UTC, datetime

    panel = {
        "competition": competition,
        "discussions": list(discussions or []),
        "kernels": list(kernels or []),
        "my_kernels": list(my_kernels or [])[:50],
        "meta": dict(meta or {}),
        "files": list(files or []),
        "submissions": list(submissions or [])[:100],
        "leaderboard": list(leaderboard or [])[:50],
        "rank": rank,
        "public_score": public_score,
        "final2_refs": list(final2_refs or [])[:2],
        # BSON Date at rest — project_data.intel_doc_for_mongo coerces if needed.
        "last_sync": datetime.now(UTC),
        "refreshed_by": refreshed_by,
    }
    _INTEL_CACHE[competition] = panel
    return panel


def intel_panel(*, competition: str, cached: dict[str, Any] | None = None) -> dict[str, Any]:
    from mymlfw.saas.db.kaggle_docs import leaderboard_display_rows

    if cached is not None:
        panel = dict(cached)
    else:
        panel = dict(
            _INTEL_CACHE.get(competition)
            or {
                "competition": competition,
                "discussions": [],
                "kernels": [],
                "my_kernels": [],
                "meta": {},
                "files": [],
                "submissions": [],
                "leaderboard": [],
                "rank": None,
                "public_score": None,
                "final2_refs": [],
                "last_sync": None,
                "refreshed_by": None,
            }
        )
    panel["leaderboard_view"] = leaderboard_display_rows(
        list(panel.get("leaderboard") or []),
        my_rank=panel.get("rank") if isinstance(panel.get("rank"), int) else None,
        my_score=panel.get("public_score")
        if isinstance(panel.get("public_score"), (int, float))
        else None,
        top_n=10,
    )
    return panel


def _best_submission_score(submissions: list[dict[str, Any]]) -> float | None:
    from mymlfw.saas.db.kaggle_docs import finite_float

    scores: list[float] = []
    for row in submissions:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").lower()
        if status and status not in {"complete", "completed", "finished", "done"}:
            continue
        val = finite_float(
            row.get("publicScore")
            or row.get("publicScoreNullable")
            or row.get("public_score")
        )
        if val is not None:
            scores.append(val)
    return max(scores) if scores else None


def sync_competition_from_kaggle(
    *,
    competition: str,
    token: str = "",
    team_hint: str | None = None,
    final2_refs: list[Any] | None = None,
) -> dict[str, Any]:
    """Live pull from Kaggle Public API → intel cache (Phase D refresh)."""
    from mymlfw.saas.kaggle_client import (
        fetch_competition,
        fetch_competition_files,
        fetch_kernels,
        fetch_leaderboard_rows,
        fetch_submissions,
        my_rank_from_leaderboard,
        resolve_kaggle_token,
    )

    bearer = token.strip() or resolve_kaggle_token()
    meta = fetch_competition(competition, token=bearer)
    files = fetch_competition_files(competition, token=bearer)
    kernels = fetch_kernels(competition, token=bearer, page_size=25)
    my_kernels = fetch_kernels(competition, token=bearer, page_size=50, mine=True)
    try:
        submissions = fetch_submissions(competition, token=bearer)
    except Exception:
        submissions = []
    leaderboard = fetch_leaderboard_rows(competition, token=bearer, limit=50)
    rank, score = my_rank_from_leaderboard(leaderboard, team_or_user=team_hint)
    user_rank = meta.get("userRankNullable")
    if rank is None and user_rank is not None:
        try:
            rank = int(user_rank)
        except (TypeError, ValueError):
            pass
    if score is None:
        score = _best_submission_score(submissions)
    return refresh_intel_cache(
        competition=competition,
        discussions=[],
        kernels=[
            {
                "ref": k.get("ref"),
                "title": k.get("title"),
                "author": k.get("author"),
                "lastRunTime": k.get("lastRunTime"),
                "isPrivate": k.get("isPrivate"),
                "totalVotes": k.get("totalVotes"),
                "totalComments": k.get("totalComments"),
            }
            for k in kernels
        ],
        my_kernels=[
            {
                "ref": k.get("ref"),
                "title": k.get("title"),
                "author": k.get("author"),
                "lastRunTime": k.get("lastRunTime"),
                "isPrivate": k.get("isPrivate"),
                "totalVotes": k.get("totalVotes"),
                "totalComments": k.get("totalComments"),
                "score": k.get("score") or k.get("bestPublicScore"),
            }
            for k in my_kernels
        ],
        meta={
            "title": meta.get("titleNullable") or meta.get("title"),
            "url": meta.get("urlNullable") or meta.get("url"),
            "reward": meta.get("rewardNullable") or meta.get("reward"),
            "deadline": meta.get("deadlineNullable") or meta.get("deadline"),
            "category": meta.get("categoryNullable") or meta.get("category"),
            "userRank": user_rank,
            "maxTeamSize": meta.get("maxTeamSizeNullable") or meta.get("maxTeamSize"),
        },
        files=[
            {
                "name": f.get("name") or f.get("nameNullable"),
                "totalBytes": f.get("totalBytes"),
                "creationDate": f.get("creationDate"),
            }
            for f in files
        ],
        submissions=submissions,
        leaderboard=leaderboard,
        rank=rank,
        public_score=score,
        final2_refs=list(final2_refs or [])[:2],
        refreshed_by="kaggle_api",
    )


def import_competition_data(
    *,
    competition: str,
    workspace_id: str,
    project_id: str,
    token: str = "",
    download: bool = True,
    dest_dir: str | None = None,
    file_name: str | None = None,
) -> dict[str, Any]:
    """List (and optionally download) competition files; register external credit.

    Download lands under ``MYMLFW_KAGGLE_DATA_DIR/{project_id}/`` (Compose volume).
    Full zip stays on disk for runners — API does not mark MinIO ``ready`` here.
    """
    import os
    from datetime import UTC, datetime
    from pathlib import Path

    from mymlfw.saas.ids import new_credit_id
    from mymlfw.saas.kaggle_client import (
        download_competition_data,
        fetch_competition_files,
        resolve_kaggle_token,
    )

    bearer = token.strip() or resolve_kaggle_token()
    files = fetch_competition_files(competition, token=bearer)
    file_rows = [
        {
            "name": f.get("name") or f.get("nameNullable"),
            "totalBytes": f.get("totalBytes"),
            "creationDate": f.get("creationDate"),
        }
        for f in files
    ]
    root = Path(
        dest_dir
        or os.environ.get("MYMLFW_KAGGLE_DATA_DIR", "/data/kaggle")
    ) / project_id
    downloaded: dict[str, Any] | None = None
    if download:
        path = download_competition_data(
            competition, root, token=bearer, file_name=file_name
        )
        downloaded = {
            "path": str(path),
            "bytes": path.stat().st_size if path.is_file() else 0,
            "file_name": path.name,
        }
    from mymlfw.saas.schemas import CreditKind, LicenseStatus

    credit = {
        "_id": new_credit_id(),
        "kind": CreditKind.kaggle_dataset.value,
        "identifier": f"kaggle://competitions/{competition}",
        "identifier_key": f"kaggle_dataset:kaggle://competitions/{competition}",
        "name": f"kaggle:{competition}",
        "source_url": f"https://www.kaggle.com/competitions/{competition}/data",
        "spdx_id": None,
        "license_status": LicenseStatus.unverified.value,
        "license_reason": "",
        "attribution_required": False,
        "authors": [],
        "used_in_final_ensemble": False,
        "linked_oof_ids": [],
        "linked_candidate_names": [],
        "harvest_source": "agent",
        "schema_version": 1,
    }
    inventory = {
        "competition": competition,
        "files": file_rows,
        "downloaded": downloaded,
        "imported_at": datetime.now(UTC),
        "credit_id": credit["_id"],
    }
    return {"inventory": inventory, "credit": credit}


def submission_distribution_diff(
    left: list[float],
    right: list[float],
    *,
    bins: int = 10,
) -> dict[str, Any]:
    """Histogram delta between two submission score columns."""
    def _hist(values: list[float]) -> list[int]:
        if not values:
            return [0] * bins
        lo, hi = min(values), max(values)
        span = hi - lo or 1.0
        counts = [0] * bins
        for v in values:
            idx = min(bins - 1, int((v - lo) / span * bins))
            counts[idx] += 1
        return counts

    a, b = _hist(left), _hist(right)
    return {
        "left_n": len(left),
        "right_n": len(right),
        "hist_left": a,
        "hist_right": b,
        "l1": sum(abs(x - y) for x, y in zip(a, b, strict=True)),
    }


def package_submission(*, files: list[str], final2: list[str]) -> dict[str, Any]:
    selected = list(final2[:2])
    return {
        "files": files,
        "final2": selected,
        "diff": {
            "added": [f for f in selected if f not in files],
            "removed": [f for f in files if f not in selected],
        },
    }


def seal_kaggle_token(token: str) -> dict[str, Any]:
    """Envelope-seal a Kaggle token. Returns public meta only (no ciphertext)."""
    from mymlfw.saas.secrets.envelope import seal_secret

    blob = seal_secret(token)
    return {
        "sealed": True,
        **blob.public_meta(),
        # Internal-only fields for Mongo persistence (never return to clients).
        "_blob": {
            "ciphertext": blob.ciphertext,
            "nonce": blob.nonce,
            "kek_version": blob.kek_version,
            "cipher_alg": blob.cipher_alg,
        },
    }


def open_sealed_kaggle_token(blob: dict[str, Any]) -> str:
    from mymlfw.saas.secrets.envelope import EnvelopeBlob, open_secret

    opened = open_secret(
        EnvelopeBlob(
            ciphertext=bytes(blob["ciphertext"]),
            nonce=bytes(blob.get("nonce") or b""),
            kek_version=int(blob.get("kek_version") or 1),
            cipher_alg=str(blob.get("cipher_alg") or "aes-256-gcm"),
        )
    )
    return opened.decode("utf-8")


def ingest_discussion(
    *,
    text: str,
    author: str,
    workspace_id: str,
    project_id: str,
) -> dict[str, Any]:
    """Sanitize discussion text and open a project_credits row for the author."""
    credit = {
        "_id": new_credit_id(),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "name": f"discussion:{author}",
        "authors": [author],
        "spdx": "UNVERIFIED_LICENSE",
        "source": "kaggle_discussion",
        "status": "UNVERIFIED",
        "used_in_final_ensemble": False,
        "schema_version": 1,
        "deleted_at": None,
    }
    return {"spotlight": spotlight_untrusted(text), "credit": credit}


def gated_kaggle_push(
    *,
    actor: str,
    credits: list[dict[str, Any]],
) -> dict[str, Any]:
    """Human elicitation + license gate. Never an overnight Autopilot submit."""
    from mymlfw.saas.elicitation import confirm_elicitation
    from mymlfw.saas.provenance import verify_project_licenses

    confirmed = confirm_elicitation(actor=actor, action="kaggle_submit")
    gate = verify_project_licenses(credits, gate="kaggle_submit")
    if not gate["ok"]:
        return {"ok": False, "confirmed": confirmed, **gate}
    return {"ok": True, "confirmed": confirmed, "blocked": []}


def notebook_ast_blocked(source: str) -> list[str]:
    reasons: list[str] = []
    if "! " in source or source.strip().startswith("!"):
        reasons.append("shell_magic")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return reasons or ["syntax"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "load" and isinstance(node.func.value, ast.Name):
                if node.func.value.id in {"pickle", "torch"}:
                    reasons.append(f"unsafe_load:{node.func.value.id}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pickle":
                    reasons.append("import_pickle")
    return reasons


def verify_public_notebook(
    *,
    source: str,
    workspace_id: str,
    project_id: str,
    author: str,
    dispatch: str = "sandbox",
) -> dict[str, Any]:
    if dispatch != "sandbox":
        raise RuntimeError("verify_public_notebook_local_ide_refused")
    blocked = notebook_ast_blocked(source)
    mission_id = new_mission_id()
    credit = {
        "_id": new_credit_id(),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "name": f"kernel:{author}",
        "authors": [author],
        "spdx": "UNVERIFIED_LICENSE",
        "source": "kaggle_kernel",
        "status": "UNVERIFIED",
        "used_in_final_ensemble": False,
        "schema_version": 1,
        "deleted_at": None,
    }
    return {
        "network": "none",
        "blocked": blocked,
        "mission_id": mission_id,
        "credit": credit,
        "spotlight": spotlight_untrusted(source[:500]),
    }
