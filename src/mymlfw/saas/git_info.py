"""Parse git remotes and refresh public hosting stats (GitHub allowlisted)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

_GITHUB_HTTPS = re.compile(
    r"^https?://(?P<host>github\.com)/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
_GITHUB_SSH = re.compile(
    r"^git@(?P<host>github\.com):(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    re.IGNORECASE,
)
_GENERIC_HTTPS = re.compile(
    r"^https?://(?P<host>[^/]+)/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
_GENERIC_SSH = re.compile(
    r"^git@(?P<host>[^:]+):(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    re.IGNORECASE,
)

_BLOCKED_HOST_FRAGMENTS = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.",
    "10.",
    "192.168.",
    "metadata.google",
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_remote(raw: str) -> str:
    cleaned = (raw or "").strip()
    if not cleaned:
        raise ValueError("git_remote_required")
    if len(cleaned) > 500:
        raise ValueError("git_remote_too_long")
    lower = cleaned.lower()
    if lower.startswith("file:"):
        raise ValueError("git_remote_blocked_host")
    if any(frag in lower for frag in ("localhost", "127.0.0.1", "0.0.0.0", "::1")):
        raise ValueError("git_remote_blocked_host")
    if not (
        cleaned.startswith("https://")
        or cleaned.startswith("http://")
        or cleaned.startswith("git@")
        or cleaned.startswith("ssh://")
    ):
        raise ValueError("git_remote_unsupported_scheme")
    return cleaned


def parse_remote(remote: str) -> dict[str, Any]:
    """Return host/owner/name/provider/html_url from a remote URL."""
    remote = normalize_remote(remote)
    for pattern in (_GITHUB_HTTPS, _GITHUB_SSH, _GENERIC_HTTPS, _GENERIC_SSH):
        match = pattern.match(remote)
        if not match:
            continue
        host = match.group("host").lower()
        owner = match.group("owner")
        name = match.group("repo").removesuffix(".git")
        if any(frag in host for frag in _BLOCKED_HOST_FRAGMENTS):
            raise ValueError("git_remote_blocked_host")
        provider = "github" if host == "github.com" else "other"
        html_url = (
            f"https://{host}/{owner}/{name}"
            if not remote.startswith("http")
            else remote.removesuffix(".git").rstrip("/")
        )
        if provider == "github":
            html_url = f"https://github.com/{owner}/{name}"
        return {
            "remote": remote,
            "host": host,
            "owner": owner,
            "name": name,
            "provider": provider,
            "html_url": html_url,
            "full_name": f"{owner}/{name}",
        }
    raise ValueError("git_remote_unparseable")


def _github_api_get(path: str, *, timeout_s: float = 8.0) -> dict[str, Any]:
    """GET api.github.com only — no arbitrary user hosts (SSRF)."""
    url = f"https://api.github.com{path}"
    parsed = urlparse(url)
    if parsed.hostname != "api.github.com":
        raise ValueError("git_fetch_host_blocked")
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mymlfw-studio",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 — host pinned
        return json.loads(resp.read().decode("utf-8"))


def fetch_github_stats(owner: str, name: str) -> dict[str, Any]:
    data = _github_api_get(f"/repos/{owner}/{name}")
    license_info = data.get("license") or {}
    return {
        "description": str(data.get("description") or ""),
        "default_branch": str(data.get("default_branch") or "main"),
        "language": str(data.get("language") or "") or None,
        "license_spdx": (license_info.get("spdx_id") if isinstance(license_info, dict) else None),
        "stars": int(data.get("stargazers_count") or 0),
        "forks": int(data.get("forks_count") or 0),
        "open_issues": int(data.get("open_issues_count") or 0),
        "watchers": int(data.get("subscribers_count") or data.get("watchers_count") or 0),
        "size_kb": int(data.get("size") or 0),
        "pushed_at": data.get("pushed_at"),
        "created_at_remote": data.get("created_at"),
        "private": bool(data.get("private")),
        "archived": bool(data.get("archived")),
        "topics": list(data.get("topics") or []),
        "html_url": str(data.get("html_url") or f"https://github.com/{owner}/{name}"),
    }


def build_git_info(
    remote: str,
    *,
    live: bool = True,
) -> dict[str, Any]:
    """Parse remote and optionally refresh public GitHub stats."""
    parsed = parse_remote(remote)
    info: dict[str, Any] = {
        **parsed,
        "description": "",
        "default_branch": None,
        "language": None,
        "license_spdx": None,
        "stars": None,
        "forks": None,
        "open_issues": None,
        "watchers": None,
        "size_kb": None,
        "pushed_at": None,
        "created_at_remote": None,
        "private": None,
        "archived": None,
        "topics": [],
        "refreshed_at": None,
        "refresh_error": None,
        "linked_at": _utcnow(),
    }
    if live and parsed.get("provider") == "github":
        try:
            stats = fetch_github_stats(parsed["owner"], parsed["name"])
            info.update(stats)
            info["refreshed_at"] = _utcnow()
            info["refresh_error"] = None
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            info["refresh_error"] = str(getattr(exc, "reason", None) or exc)
            info["refreshed_at"] = _utcnow()
    elif live:
        info["refresh_error"] = "stats_unsupported_host"
        info["refreshed_at"] = _utcnow()
    return info
