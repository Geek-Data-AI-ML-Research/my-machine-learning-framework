"""Worker entrypoint stub — fair-share claim loop + outbox consumer hook."""

from __future__ import annotations

import json

from mymlfw.worker.fair_share import FairShareConfig, FairShareQueue


def run_once(queue: FairShareQueue | None = None) -> dict:
    """Single fair-share claim tick (daemon/compose wiring later)."""
    q = queue or FairShareQueue(FairShareConfig())
    job = q.claim_next()
    return {
        "claimed": job is not None,
        "job": job,
        "pending": q.pending_count(),
        "note": "Dispatch by runner kind + outbox consumer land with later C tracks.",
    }


def main() -> None:
    print(json.dumps(run_once()))


if __name__ == "__main__":
    main()
