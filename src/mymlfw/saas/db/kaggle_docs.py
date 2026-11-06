"""BSON-safe shapes for Kaggle intel / data / credits on projects.

Timestamps → aware UTC ``datetime`` (not ISO strings).
Metric fields → finite floats or omitted.
Envelope ciphertext/nonce → ``bytes`` binData.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any, Mapping

from mymlfw.saas.schemas import CreditKind, LicenseStatus

MappingLike = Mapping[str, Any]

_BOM = "\ufeff"
_ISO_Z = re.compile(r"Z$")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def parse_utc(value: Any) -> datetime | None:
    """Coerce ISO strings / datetimes to tz-aware UTC; else None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(_ISO_Z.sub("+00:00", raw))
        except ValueError:
            # Kaggle LB style: "2026-11-01 21:05:13"
            try:
                dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    return None


def finite_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def finite_int(value: Any) -> int | None:
    f = finite_float(value)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError, OverflowError):
        return None


def _clean_key(key: str) -> str:
    return str(key or "").lstrip(_BOM).strip()


def normalize_leaderboard_row(row: MappingLike) -> dict[str, Any]:
    cleaned = {_clean_key(k): v for k, v in dict(row).items()}
    rank = finite_int(
        cleaned.get("Rank") or cleaned.get("rank") or cleaned.get("Position")
    )
    score = finite_float(
        cleaned.get("Score")
        or cleaned.get("score")
        or cleaned.get("PublicScore")
        or cleaned.get("SubmissionScore")
    )
    team = str(
        cleaned.get("TeamName")
        or cleaned.get("teamName")
        or cleaned.get("TeamId")
        or cleaned.get("UserName")
        or ""
    ).strip()
    out: dict[str, Any] = {
        "rank": rank,
        "score": score,
        "team_name": team or None,
        "team_id": cleaned.get("TeamId") or cleaned.get("teamId"),
        "submission_count": finite_int(cleaned.get("SubmissionCount")),
        "last_submission_at": parse_utc(cleaned.get("LastSubmissionDate")),
    }
    return {k: v for k, v in out.items() if v is not None}


def normalize_file_row(row: MappingLike) -> dict[str, Any]:
    name = row.get("name") or row.get("nameNullable")
    out: dict[str, Any] = {
        "name": str(name).strip() if name else None,
        "total_bytes": finite_int(row.get("totalBytes") or row.get("total_bytes")),
        "created_at": parse_utc(row.get("creationDate") or row.get("created_at")),
    }
    return {k: v for k, v in out.items() if v is not None}


def normalize_kernel_row(row: MappingLike) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ref": row.get("ref"),
        "title": row.get("title"),
        "author": row.get("author"),
        "last_run_at": parse_utc(row.get("lastRunTime") or row.get("last_run_at")),
        "is_private": row.get("isPrivate")
        if isinstance(row.get("isPrivate"), bool)
        else row.get("is_private")
        if isinstance(row.get("is_private"), bool)
        else None,
        "total_votes": finite_int(row.get("totalVotes") or row.get("total_votes")),
        "total_comments": finite_int(
            row.get("totalComments") or row.get("total_comments")
        ),
        "score": finite_float(
            row.get("score")
            or row.get("publicScore")
            or row.get("public_score")
            or row.get("bestPublicScore")
        ),
    }
    return {k: v for k, v in out.items() if v is not None}


def leaderboard_display_rows(
    leaderboard: list[MappingLike] | None,
    *,
    my_rank: int | None,
    my_score: float | None,
    my_team: str | None = None,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Top ``top_n`` public LB rows; append own row when rank is outside that band."""
    cleaned: list[dict[str, Any]] = []
    for r in list(leaderboard or []):
        if not isinstance(r, dict):
            continue
        if any(k in r for k in ("rank", "score", "team_name")):
            cleaned.append(
                {
                    "rank": finite_int(r.get("rank")),
                    "score": finite_float(r.get("score")),
                    "team_name": r.get("team_name") or r.get("TeamName"),
                    "team_id": r.get("team_id") or r.get("TeamId"),
                }
            )
        else:
            cleaned.append(normalize_leaderboard_row(r))
    cleaned.sort(key=lambda row: (row.get("rank") is None, row.get("rank") or 10**9))
    top = cleaned[: max(0, int(top_n))]
    out: list[dict[str, Any]] = []
    for row in top:
        item = {k: v for k, v in row.items() if v is not None}
        item["is_me"] = bool(
            my_rank is not None and item.get("rank") is not None and item["rank"] == my_rank
        )
        out.append(item)
    if my_rank is not None and my_rank > top_n:
        you: dict[str, Any] = {
            "rank": my_rank,
            "is_me": True,
            "team_name": (my_team or "").strip() or "You",
        }
        if my_score is not None:
            you["score"] = my_score
        out.append(you)
    return out


def normalize_submission_row(row: MappingLike) -> dict[str, Any]:
    """Shape for ``projects.kaggle_intel.submissions`` (Kaggle submissions/list)."""
    ref = row.get("ref") or row.get("id")
    try:
        ref_out: int | str | None = int(ref) if ref is not None else None
    except (TypeError, ValueError):
        ref_out = str(ref) if ref is not None else None
    status = str(row.get("status") or "").strip().lower() or None
    err = row.get("errorDescription") or row.get("error_description") or ""
    out: dict[str, Any] = {
        "ref": ref_out,
        "file_name": row.get("fileName")
        or row.get("fileNameNullable")
        or row.get("file_name"),
        "description": row.get("description")
        or row.get("descriptionNullable")
        or row.get("description"),
        "public_score": finite_float(
            row.get("publicScore")
            or row.get("publicScoreNullable")
            or row.get("public_score")
        ),
        "private_score": finite_float(
            row.get("privateScore")
            or row.get("privateScoreNullable")
            or row.get("private_score")
        ),
        "status": status,
        "error_description": str(err).strip() or None,
        "submitted_at": parse_utc(row.get("date") or row.get("submitted_at")),
        "submitted_by": row.get("submittedBy")
        or row.get("submittedByNullable")
        or row.get("submitted_by"),
        "team_name": row.get("teamName")
        or row.get("teamNameNullable")
        or row.get("team_name"),
        "total_bytes": finite_int(
            row.get("totalBytes")
            or row.get("totalBytesNullable")
            or row.get("total_bytes")
        ),
    }
    return {k: v for k, v in out.items() if v is not None}


def intel_doc_for_mongo(panel: MappingLike) -> dict[str, Any]:
    """Shape written to ``projects.kaggle_intel``."""
    raw = dict(panel)
    last_sync = parse_utc(raw.get("last_sync")) or _utcnow()
    public_score = finite_float(raw.get("public_score"))
    rank = finite_int(raw.get("rank"))
    files = [normalize_file_row(f) for f in list(raw.get("files") or []) if isinstance(f, dict)]
    kernels = [
        normalize_kernel_row(k) for k in list(raw.get("kernels") or []) if isinstance(k, dict)
    ]
    my_kernels = [
        normalize_kernel_row(k)
        for k in list(raw.get("my_kernels") or [])[:50]
        if isinstance(k, dict)
    ]
    submissions = [
        normalize_submission_row(s)
        for s in list(raw.get("submissions") or [])[:100]
        if isinstance(s, dict)
    ]
    leaderboard = [
        normalize_leaderboard_row(r)
        for r in list(raw.get("leaderboard") or [])[:50]
        if isinstance(r, dict)
    ]
    meta_in = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    meta = {
        "title": meta_in.get("title"),
        "url": meta_in.get("url"),
        "reward": meta_in.get("reward"),
        "deadline": parse_utc(meta_in.get("deadline")) or meta_in.get("deadline"),
        "category": meta_in.get("category"),
        "user_rank": finite_int(meta_in.get("userRank") or meta_in.get("user_rank")),
        "max_team_size": finite_int(
            meta_in.get("maxTeamSize") or meta_in.get("max_team_size")
        ),
    }
    return {
        "competition": str(raw.get("competition") or ""),
        "discussions": list(raw.get("discussions") or [])[:50],
        "kernels": kernels[:25],
        "my_kernels": my_kernels,
        "meta": {k: v for k, v in meta.items() if v is not None},
        "files": files,
        "submissions": submissions,
        "leaderboard": leaderboard,
        "rank": rank,
        "public_score": public_score,
        "medal_pace": raw.get("medal_pace"),
        "final2_refs": [
            r
            for r in list(raw.get("final2_refs") or [])[:2]
            if r is not None and r != ""
        ],
        "last_sync": last_sync,
        "refreshed_by": raw.get("refreshed_by"),
        "schema_version": 1,
    }


def inventory_doc_for_mongo(inventory: MappingLike) -> dict[str, Any]:
    raw = dict(inventory)
    files = [
        normalize_file_row(f) for f in list(raw.get("files") or []) if isinstance(f, dict)
    ]
    downloaded = raw.get("downloaded")
    dl_out = None
    if isinstance(downloaded, dict):
        dl_out = {
            "path": downloaded.get("path"),
            "bytes": finite_int(downloaded.get("bytes")) or 0,
            "file_name": downloaded.get("file_name"),
        }
    return {
        "competition": str(raw.get("competition") or ""),
        "files": files,
        "downloaded": dl_out,
        "imported_at": parse_utc(raw.get("imported_at")) or _utcnow(),
        "credit_id": raw.get("credit_id"),
        "schema_version": 1,
    }


def credit_doc_for_mongo(credit: MappingLike, *, now: datetime | None = None) -> dict[str, Any]:
    """Align with ``CreditAssetDoc`` (+ tenant stamps applied by ScopedCollection)."""
    ts = now or _utcnow()
    raw = dict(credit)
    kind_raw = str(raw.get("kind") or CreditKind.kaggle_dataset.value)
    try:
        kind = CreditKind(kind_raw).value
    except ValueError:
        kind = CreditKind.kaggle_dataset.value
    status_raw = str(
        raw.get("license_status") or LicenseStatus.unverified.value
    )
    try:
        license_status = LicenseStatus(status_raw).value
    except ValueError:
        license_status = LicenseStatus.unverified.value
    return {
        "_id": raw["_id"],
        "kind": kind,
        "identifier": str(raw["identifier"]),
        "identifier_key": str(raw["identifier_key"]),
        "name": str(raw["name"]),
        "source_url": raw.get("source_url"),
        "spdx_id": raw.get("spdx_id"),
        "license_raw": raw.get("license_raw"),
        "license_status": license_status,
        "license_reason": str(raw.get("license_reason") or ""),
        "attribution_required": bool(raw.get("attribution_required") or False),
        "attribution_text": raw.get("attribution_text"),
        "authors": list(raw.get("authors") or []),
        "year": finite_int(raw.get("year")),
        "doi": raw.get("doi"),
        "arxiv_id": raw.get("arxiv_id"),
        "used_in_final_ensemble": bool(raw.get("used_in_final_ensemble") or False),
        "linked_oof_ids": list(raw.get("linked_oof_ids") or []),
        "linked_candidate_names": list(raw.get("linked_candidate_names") or []),
        "harvest_source": raw.get("harvest_source")
        if raw.get("harvest_source") in {"agent", "ast", "cli"}
        else "agent",
        "resolved_at": parse_utc(raw.get("resolved_at")),
        "schema_version": int(raw.get("schema_version") or 1),
        "created_at": parse_utc(raw.get("created_at")) or ts,
        "updated_at": ts,
        "deleted_at": None,
    }


def envelope_blob_for_mongo(blob: MappingLike) -> dict[str, Any]:
    """Persist envelope fields as binData bytes (never hex)."""
    ct = blob["ciphertext"]
    nonce = blob.get("nonce") or b""
    if isinstance(ct, str):
        raise TypeError("kaggle_token_ciphertext_must_be_bytes")
    if isinstance(nonce, str):
        raise TypeError("kaggle_token_nonce_must_be_bytes")
    return {
        "ciphertext": bytes(ct),
        "nonce": bytes(nonce),
        "kek_version": int(blob.get("kek_version") or 1),
        "cipher_alg": str(blob.get("cipher_alg") or "aes-256-gcm"),
    }
