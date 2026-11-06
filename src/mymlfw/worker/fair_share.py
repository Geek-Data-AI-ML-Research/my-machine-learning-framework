"""Fair-share job queue (per-org concurrency from entitlements).

Round-robin across orgs that have pending work so one tenant cannot starve
others. Runner ``auto`` picker prefers ready local, else cheapest cloud GPU.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

from mymlfw.saas.providers.service import pick_runner_auto


@dataclass(frozen=True)
class FairShareConfig:
    max_concurrent_jobs_per_org: int = 2


@dataclass
class FairShareQueue:
    config: FairShareConfig = field(default_factory=FairShareConfig)
    # org_id -> FIFO list of job dicts
    _pending: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _running_by_org: dict[str, int] = field(default_factory=dict)
    _rr_order: list[str] = field(default_factory=list)
    _rr_index: int = 0
    # Optional hook: org_id -> list of runner dicts for job runner=auto
    runners_for_org: Callable[[str], list[dict[str, Any]]] | None = None

    def enqueue(self, *, org_id: str, job: dict[str, Any]) -> None:
        if org_id not in self._pending:
            self._pending[org_id] = []
            self._rr_order.append(org_id)
            self._running_by_org.setdefault(org_id, 0)
        payload = dict(job)
        payload.setdefault("org_id", org_id)
        payload.setdefault("enqueued_at", datetime.now(UTC).isoformat())
        self._pending[org_id].append(payload)

    def pending_count(self, org_id: str | None = None) -> int:
        if org_id is None:
            return sum(len(v) for v in self._pending.values())
        return len(self._pending.get(org_id, []))

    def running_count(self, org_id: str) -> int:
        return int(self._running_by_org.get(org_id, 0))

    def claim_next(self) -> dict[str, Any] | None:
        """Round-robin claim respecting ``max_concurrent_jobs_per_org``."""
        if not self._rr_order:
            return None
        n = len(self._rr_order)
        for _ in range(n):
            org_id = self._rr_order[self._rr_index % n]
            self._rr_index = (self._rr_index + 1) % n
            if self._running_by_org.get(org_id, 0) >= self.config.max_concurrent_jobs_per_org:
                continue
            queue = self._pending.get(org_id) or []
            if not queue:
                continue
            job = queue.pop(0)
            self._running_by_org[org_id] = self._running_by_org.get(org_id, 0) + 1
            job["claimed_at"] = datetime.now(UTC).isoformat()
            job["org_id"] = org_id
            if str(job.get("runner") or job.get("runner_id") or "auto") == "auto":
                picked = self.pick_runner(org_id)
                if picked is not None:
                    job["runner_id"] = picked.get("runner_id") or picked.get("_id")
                    job["runner_kind"] = picked.get("kind")
                    job["runner_pick"] = "auto"
            return job
        return None

    def pick_runner(self, org_id: str) -> dict[str, Any] | None:
        """Job ``auto`` picker hook: local ready → cheapest fitting cloud GPU."""
        if self.runners_for_org is None:
            return None
        return pick_runner_auto(self.runners_for_org(org_id))

    def complete(self, org_id: str) -> None:
        cur = self._running_by_org.get(org_id, 0)
        self._running_by_org[org_id] = max(0, cur - 1)
