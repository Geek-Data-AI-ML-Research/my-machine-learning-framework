"""ProjectScopedDB: injected after membership check; scoped collections only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from mymlfw.saas.db.tenant_repo import ScopedCollection


@dataclass(frozen=True)
class MissionLeaseClaim:
    """Fencing fields for mission claim/complete (Phase B2 fills the logic)."""

    mission_id: str
    attempt_count: int
    lease_owner: str
    lease_expires_at: Any


@dataclass(frozen=True)
class ExecutionLock:
    """Unified one-open-lever / autopilot mutex on ``projects.active_execution_lock``."""

    holder_type: str  # lever | autopilot
    holder_id: str
    expires_at: Any


class ProjectScopedDB:
    """Tenant-isolated view of a single project's collections."""

    def __init__(
        self,
        db: AsyncDatabase,
        *,
        workspace_id: str,
        project_id: str,
    ) -> None:
        self._db = db
        self.workspace_id = workspace_id
        self.project_id = project_id

    def _scoped(self, name: str) -> ScopedCollection:
        return ScopedCollection(
            self._db[name],
            workspace_id=self.workspace_id,
            project_id=self.project_id,
        )

    @property
    def goals(self) -> ScopedCollection:
        return self._scoped("project_goals")

    @property
    def experiments(self) -> ScopedCollection:
        return self._scoped("experiments")

    @property
    def missions(self) -> ScopedCollection:
        return self._scoped("missions")

    @property
    def dead_ends(self) -> ScopedCollection:
        return self._scoped("dead_ends")

    @property
    def runs(self) -> ScopedCollection:
        return self._scoped("runs")

    @property
    def progress(self) -> ScopedCollection:
        return self._scoped("daily_progress")

    @property
    def memory(self) -> ScopedCollection:
        return self._scoped("memory_chunks")

    @property
    def autopilot_nodes(self) -> ScopedCollection:
        return self._scoped("autopilot_nodes")

    @property
    def project_credits(self) -> ScopedCollection:
        return self._scoped("project_credits")

    async def claim_next_mission_stub(
        self, *, lease_owner: str
    ) -> MissionLeaseClaim | None:
        """Stub: fencing token is ``attempt_count``; real claim lands in B2."""
        _ = lease_owner
        return None

    async def complete_mission_stub(
        self,
        *,
        mission_id: str,
        attempt_count: int,
    ) -> None:
        """Stub: mismatch must 409 when B2 implements transactional complete."""
        _ = (mission_id, attempt_count)
        raise NotImplementedError("complete_mission_transactional lands in Phase B2")
