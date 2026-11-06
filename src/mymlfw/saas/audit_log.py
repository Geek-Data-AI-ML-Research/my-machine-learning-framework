"""Hash-chained audit log (process-local; Mongo collection name audit_logs)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

_CHAIN: list[dict[str, Any]] = []


def reset_audit_for_tests() -> None:
    _CHAIN.clear()


def append_audit(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    prev = _CHAIN[-1]["hash"] if _CHAIN else "0" * 64
    body = {
        "event": event,
        "payload": payload,
        "prev": prev,
        "at": datetime.now(UTC).isoformat(),
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    row = {**body, "hash": digest}
    _CHAIN.append(row)
    return row


def verify_chain() -> bool:
    prev = "0" * 64
    for row in _CHAIN:
        body = {k: row[k] for k in ("event", "payload", "prev", "at")}
        if body["prev"] != prev:
            return False
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        if digest != row["hash"]:
            return False
        prev = digest
    return True
