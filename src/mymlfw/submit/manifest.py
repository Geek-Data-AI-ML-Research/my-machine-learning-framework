"""Plain JSON manifest. This module does not import the blend package."""

from __future__ import annotations

import json
from pathlib import Path


def write_manifest(path, weights, pool: str, artifact_sha256: str, **extra) -> dict:
    document = {
        "artifact_sha256": artifact_sha256,
        "pool": pool,
        "weights": [float(weight) for weight in weights],
    }
    document.update(extra)
    Path(path).write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
    return document
