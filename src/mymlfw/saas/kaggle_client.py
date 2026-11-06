"""Live Kaggle Public API client (https://www.kaggle.com/docs/api).

Uses Bearer ``KAGGLE_API_TOKEN`` (KGAT_…) or legacy Basic username/key.
Calls go to ``https://www.kaggle.com/api/v1/…`` via httpx after SSRF host check.
"""

from __future__ import annotations

import csv
import io
import os
import zipfile
from pathlib import Path
from typing import Any

from mymlfw.saas.ssrf import SsrfError, assert_public_host

KAGGLE_API_HOST = "www.kaggle.com"
KAGGLE_API_BASE = f"https://{KAGGLE_API_HOST}/api/v1"


class KaggleClientError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_kaggle_token(
    *,
    sealed_plaintext: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Prefer project-sealed token, then env, then ``~/.kaggle/access_token``."""
    if sealed_plaintext and sealed_plaintext.strip():
        return sealed_plaintext.strip()
    environ = env if env is not None else dict(os.environ)
    for key in ("KAGGLE_API_TOKEN", "MYMLFW_KAGGLE_API_TOKEN"):
        raw = (environ.get(key) or "").strip()
        if raw:
            return raw
    path = Path.home() / ".kaggle" / "access_token"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    # Legacy kaggle.json {username,key} → not a bearer token; caller may Basic-auth.
    return ""


def resolve_kaggle_basic(
    *, env: dict[str, str] | None = None
) -> tuple[str, str] | None:
    environ = env if env is not None else dict(os.environ)
    user = (environ.get("KAGGLE_USERNAME") or "").strip()
    key = (environ.get("KAGGLE_KEY") or "").strip()
    if user and key:
        return user, key
    path = Path.home() / ".kaggle" / "kaggle.json"
    if path.is_file():
        import json

        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        u, k = str(doc.get("username") or "").strip(), str(doc.get("key") or "").strip()
        if u and k:
            return u, k
    return None


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "mymlfw-saas/0.1",
    }


def _client_kwargs(token: str) -> dict[str, Any]:
    assert_public_host(KAGGLE_API_HOST)
    headers = _auth_headers(token) if token else {}
    auth = None
    if not token:
        basic = resolve_kaggle_basic()
        if basic is None:
            raise KaggleClientError(
                "kaggle_credentials_required",
                "Set KAGGLE_API_TOKEN (or seal a project token) / KAGGLE_USERNAME+KAGGLE_KEY",
            )
        auth = basic
    return {"headers": headers, "auth": auth, "timeout": 60.0, "follow_redirects": True}


def fetch_competition(competition: str, *, token: str = "") -> dict[str, Any]:
    import httpx

    slug = competition.strip()
    kwargs = _client_kwargs(token)
    with httpx.Client(**{k: v for k, v in kwargs.items() if v is not None}) as client:
        res = client.get(
            f"{KAGGLE_API_BASE}/competitions/list",
            params={"search": slug},
        )
        if res.status_code >= 400:
            raise KaggleClientError(
                "kaggle_http_error",
                f"competitions/list {res.status_code}: {res.text[:200]}",
            )
        rows = res.json()
        if not isinstance(rows, list):
            rows = []
        for row in rows:
            ref = str(
                row.get("ref")
                or row.get("id")
                or (row.get("urlNullable") or "").rstrip("/").split("/")[-1]
                or ""
            )
            if ref == slug or slug in str(row.get("urlNullable") or ""):
                return dict(row)
        return dict(rows[0]) if rows else {"ref": slug}


def fetch_competition_files(competition: str, *, token: str = "") -> list[dict[str, Any]]:
    import httpx

    kwargs = _client_kwargs(token)
    with httpx.Client(**{k: v for k, v in kwargs.items() if v is not None}) as client:
        res = client.get(f"{KAGGLE_API_BASE}/competitions/data/list/{competition}")
        if res.status_code >= 400:
            raise KaggleClientError(
                "kaggle_http_error",
                f"data/list {res.status_code}: {res.text[:200]}",
            )
        body = res.json()
        files = body.get("files") if isinstance(body, dict) else body
        return list(files or [])


def fetch_leaderboard_rows(
    competition: str, *, token: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    """Download public LB zip/csv and return top rows."""
    import httpx

    kwargs = _client_kwargs(token)
    with httpx.Client(**{k: v for k, v in kwargs.items() if v is not None}) as client:
        res = client.get(
            f"{KAGGLE_API_BASE}/competitions/{competition}/leaderboard/download"
        )
        if res.status_code >= 400:
            raise KaggleClientError(
                "kaggle_http_error",
                f"leaderboard/download {res.status_code}: {res.text[:200]}",
            )
        raw = res.content
    text = ""
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            name = next((n for n in zf.namelist() if n.endswith(".csv")), None)
            if not name:
                return []
            # utf-8-sig strips a leading BOM that otherwise poisons the Rank column name.
            text = zf.read(name).decode("utf-8-sig", errors="replace")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for i, row in enumerate(reader):
        if i >= limit:
            break
        cleaned: dict[str, Any] = {}
        for k, v in row.items():
            key = str(k or "").lstrip("\ufeff").strip()
            cleaned[key] = v.strip() if isinstance(v, str) else v
        rows.append(cleaned)
    return rows


def fetch_kernels(
    competition: str,
    *,
    token: str = "",
    page_size: int = 20,
    mine: bool = False,
    sort_by: str = "voteCount",
) -> list[dict[str, Any]]:
    """List kernels for a competition. ``mine=True`` → Your Work (Code tab)."""
    import httpx

    kwargs = _client_kwargs(token)
    params: dict[str, Any] = {
        "competition": competition,
        "pageSize": page_size,
        "sortBy": "dateRun" if mine and sort_by == "voteCount" else sort_by,
    }
    if mine:
        params["mine"] = "true"
    with httpx.Client(**{k: v for k, v in kwargs.items() if v is not None}) as client:
        res = client.get(
            f"{KAGGLE_API_BASE}/kernels/list",
            params=params,
        )
        if res.status_code >= 400:
            raise KaggleClientError(
                "kaggle_http_error",
                f"kernels/list {res.status_code}: {res.text[:200]}",
            )
        body = res.json()
        return list(body if isinstance(body, list) else [])


def fetch_submissions(
    competition: str, *, token: str = "", page: int = 1
) -> list[dict[str, Any]]:
    """List own competition submissions (``GET …/competitions/submissions/list/{id}``)."""
    import httpx

    kwargs = _client_kwargs(token)
    with httpx.Client(**{k: v for k, v in kwargs.items() if v is not None}) as client:
        res = client.get(
            f"{KAGGLE_API_BASE}/competitions/submissions/list/{competition}",
            params={"page": max(1, int(page))},
        )
        if res.status_code >= 400:
            raise KaggleClientError(
                "kaggle_http_error",
                f"submissions/list {res.status_code}: {res.text[:200]}",
            )
        body = res.json()
        if isinstance(body, list):
            return list(body)
        if isinstance(body, dict):
            for key in ("submissions", "list", "items"):
                if isinstance(body.get(key), list):
                    return list(body[key])
        return []


def my_rank_from_leaderboard(
    rows: list[dict[str, Any]], *, team_or_user: str | None = None
) -> tuple[int | None, float | None]:
    """Best-effort parse of public LB CSV columns (Rank / TeamId / Score).

    Without ``team_or_user``, returns ``(None, None)`` — do not treat #1 as "ours".
    """
    if not rows:
        return None, None
    needle = (team_or_user or "").strip().lower()
    if not needle:
        return None, None
    for row in rows:
        rank_raw = row.get("Rank") or row.get("rank") or row.get("Position")
        score_raw = (
            row.get("Score")
            or row.get("score")
            or row.get("PublicScore")
            or row.get("SubmissionScore")
        )
        team = str(
            row.get("TeamName")
            or row.get("teamName")
            or row.get("TeamId")
            or row.get("UserName")
            or ""
        )
        if needle not in team.lower():
            continue
        try:
            rank = int(float(rank_raw)) if rank_raw not in (None, "") else None
        except (TypeError, ValueError):
            rank = None
        try:
            score = float(score_raw) if score_raw not in (None, "") else None
        except (TypeError, ValueError):
            score = None
        return rank, score
    return None, None


def download_competition_data(
    competition: str,
    dest_dir: str | Path,
    *,
    token: str = "",
    file_name: str | None = None,
) -> Path:
    """Download competition data zip (all) or one file into ``dest_dir``.

    Uses ``/competitions/data/download-all/{competition}`` or
    ``/competitions/data/download/{competition}/{fileName}``
    (https://www.kaggle.com/docs/api).
    """
    import httpx

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    kwargs = _client_kwargs(token)
    if file_name:
        url = f"{KAGGLE_API_BASE}/competitions/data/download/{competition}/{file_name}"
        out_name = Path(file_name).name
    else:
        url = f"{KAGGLE_API_BASE}/competitions/data/download-all/{competition}"
        out_name = f"{competition}.zip"
    with httpx.Client(**{k: v for k, v in kwargs.items() if v is not None}) as client:
        with client.stream("GET", url) as res:
            if res.status_code >= 400:
                # Drain briefly for error text.
                body = res.read()[:200]
                raise KaggleClientError(
                    "kaggle_http_error",
                    f"data/download {res.status_code}: {body!r}",
                )
            out_path = dest / out_name
            with out_path.open("wb") as fh:
                for chunk in res.iter_bytes():
                    fh.write(chunk)
    return out_path


__all__ = [
    "KAGGLE_API_BASE",
    "KaggleClientError",
    "SsrfError",
    "download_competition_data",
    "fetch_competition",
    "fetch_competition_files",
    "fetch_kernels",
    "fetch_leaderboard_rows",
    "fetch_submissions",
    "my_rank_from_leaderboard",
    "resolve_kaggle_basic",
    "resolve_kaggle_token",
]
