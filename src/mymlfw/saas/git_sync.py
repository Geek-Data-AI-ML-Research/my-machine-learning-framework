"""Git sync: GitHub App primary, events.jsonl, secret scan, webhook HMAC."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SECRET_PREFIXES = ("sk-", "ghp_", "github_pat_", "AKIA", "mongodb://", "mongodb+srv://")
_REPLAY: set[str] = set()


def reset_webhook_replay_for_tests() -> None:
    _REPLAY.clear()


def verify_github_webhook(*, body: bytes, signature: str, secret: str, delivery_id: str) -> bool:
    if not delivery_id or delivery_id in _REPLAY:
        return False
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    expected = "sha256=" + mac
    if not hmac.compare_digest(expected, signature or ""):
        return False
    _REPLAY.add(delivery_id)
    return True


def scan_secrets(text: str) -> list[str]:
    hits: list[str] = []
    for prefix in _SECRET_PREFIXES:
        if prefix in text:
            hits.append(prefix)
    return hits


def reject_unsafe_paths(paths: list[str]) -> list[str]:
    bad: list[str] = []
    for p in paths:
        if p.startswith("/") or ".." in Path(p).parts or p.endswith(".git/modules"):
            bad.append(p)
        if Path(p).name.startswith(".") and "submodule" in p:
            bad.append(p)
        if p.startswith("symlink:"):
            bad.append(p)
    return bad


def append_event(path: str | Path, event: dict[str, Any]) -> None:
    text = json.dumps(event, sort_keys=True, default=str)
    if scan_secrets(text):
        raise ValueError("secret_in_event")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")


def ulid_union_merge(local_lines: list[str], remote_lines: list[str]) -> list[str]:
    """Union events by id field; keep both sides; sort by id."""
    seen: dict[str, str] = {}
    for line in [*local_lines, *remote_lines]:
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = str(doc.get("id") or doc.get("_id") or line)
        seen[key] = json.dumps(doc, sort_keys=True)
    return [seen[k] for k in sorted(seen)]


def git_sync_plan(*, installation_id: str | None, pat_fallback: bool) -> dict[str, Any]:
    if installation_id:
        auth = "github_app"
    elif pat_fallback:
        auth = "pat_fallback"
    else:
        auth = "unconfigured"
    return {
        "auth": auth,
        "hooks_path": "/dev/null",
        "reject_submodules": True,
        "reject_symlinks": True,
        "events_file": "events.jsonl",
        "outbox_event": "git.sync",
    }


def mission_complete_git_job(*, project_id: str, mission_id: str) -> dict[str, Any]:
    return {
        "event_type": "git.sync",
        "payload": {
            "project_id": project_id,
            "mission_id": mission_id,
            "at": datetime.now(UTC).isoformat(),
        },
    }
