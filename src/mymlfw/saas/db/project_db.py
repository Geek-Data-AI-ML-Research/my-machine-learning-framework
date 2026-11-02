"""ProjectScopedDB: injected after membership check; scoped collections only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from mymlfw.saas.db.errors import MissionNotFoundError, StaleLeaseError
from mymlfw.saas.db.outbox import enqueue_outbox_event
from mymlfw.saas.db.tenant_repo import ScopedCollection

DEFAULT_LEASE_SECONDS = 900


@dataclass(frozen=True)
class MissionLeaseClaim:
    """Atomic claim result; ``attempt_count`` is the lease fencing token."""

    mission_id: str
    attempt_count: int
    lease_owner: str
    lease_expires_at: datetime
    title: str = ""
    mission_type: str = "custom"
    brief_md: str = ""
    goal_id: str | None = None
    template_id: str | None = None
    epoch_id: str | None = None
    doc: dict[str, Any] | None = None


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

    @property
    def axioms(self) -> ScopedCollection:
        return self._scoped("project_axioms")

    @property
    def episode_cards(self) -> ScopedCollection:
        """Alias over memory_chunks for contrastive episode card docs."""
        return self._scoped("memory_chunks")

    def _mission_tenant_base(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "deleted_at": None,
        }

    async def claim_next_mission(
        self,
        *,
        lease_owner: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> MissionLeaseClaim | None:
        """Atomically claim the next queued (or expired-lease) mission.

        ``$inc attempt_count`` yields the fencing token returned to the agent.
        Uses the raw missions collection (operator filter) while still forcing
        tenant keys — ScopedCollection rejects ``$or`` / ``$lte`` in filters.
        """
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=lease_seconds)
        filt: dict[str, Any] = {
            **self._mission_tenant_base(),
            "$or": [
                {"status": "queued"},
                {"status": "leased", "lease_expires_at": {"$lte": now}},
            ],
        }
        update = {
            "$set": {
                "status": "leased",
                "lease_owner": lease_owner,
                "lease_expires_at": expires,
                "updated_at": now,
            },
            "$inc": {"attempt_count": 1},
        }
        doc = await self._db["missions"].find_one_and_update(
            filt,
            update,
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return None
        return MissionLeaseClaim(
            mission_id=str(doc["_id"]),
            attempt_count=int(doc["attempt_count"]),
            lease_owner=str(doc["lease_owner"]),
            lease_expires_at=doc["lease_expires_at"],
            title=str(doc.get("title") or doc.get("mission_type") or "mission"),
            mission_type=str(doc.get("mission_type") or "custom"),
            brief_md=str(doc.get("brief_md") or ""),
            goal_id=doc.get("goal_id"),
            template_id=doc.get("template_id"),
            epoch_id=doc.get("epoch_id"),
            doc=doc,
        )

    # Back-compat alias for Wave 1 stub callers.
    async def claim_next_mission_stub(
        self, *, lease_owner: str
    ) -> MissionLeaseClaim | None:
        return await self.claim_next_mission(lease_owner=lease_owner)

    async def complete_mission_transactional(
        self,
        *,
        mission_id: str,
        attempt_count: int,
        outcome: str,
        fold_scores: list[float] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Complete a leased mission; fencing mismatch → ``StaleLeaseError`` (409)."""
        now = datetime.now(UTC)
        if outcome in ("succeeded", "success", "promote"):
            status = "succeeded"
            normalized_outcome = "succeeded"
        elif outcome in ("abandoned", "abandoned_by_agent"):
            status = "abandoned_by_agent"
            normalized_outcome = "abandoned"
        else:
            status = "failed"
            normalized_outcome = "failed"

        scores = list(fold_scores or [])
        client = self._db.client

        async def _txn(session: Any) -> dict[str, Any]:
            async with session.bind(end_session=False):
                coll = self._db["missions"]
                doc = await coll.find_one_and_update(
                    {
                        **self._mission_tenant_base(),
                        "_id": mission_id,
                        "status": "leased",
                        "attempt_count": attempt_count,
                    },
                    {
                        "$set": {
                            "status": status,
                            "outcome": normalized_outcome,
                            "fold_scores": scores,
                            "completion_notes": notes,
                            "lease_expires_at": now,
                            "updated_at": now,
                        }
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if doc is None:
                    existing = await coll.find_one(
                        {
                            **self._mission_tenant_base(),
                            "_id": mission_id,
                        }
                    )
                    if existing is None:
                        raise MissionNotFoundError(mission_id=mission_id)
                    raise StaleLeaseError(
                        mission_id=mission_id,
                        expected=existing.get("attempt_count"),
                    )
                await enqueue_outbox_event(
                    self._db,
                    event_type="mission.completed",
                    payload={
                        "mission_id": mission_id,
                        "outcome": normalized_outcome,
                        "attempt_count": attempt_count,
                        "status": status,
                    },
                    workspace_id=self.workspace_id,
                    project_id=self.project_id,
                )
                return doc

        async with client.start_session() as session:
            return await session.with_transaction(_txn)

    async def complete_mission_stub(
        self,
        *,
        mission_id: str,
        attempt_count: int,
    ) -> None:
        await self.complete_mission_transactional(
            mission_id=mission_id,
            attempt_count=attempt_count,
            outcome="succeeded",
        )

    async def renew_mission_lease(
        self,
        *,
        mission_id: str,
        attempt_count: int,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        note: str = "",
        percent: float | None = None,
    ) -> dict[str, Any]:
        """Heartbeat / renew; fencing mismatch → ``StaleLeaseError``."""
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=lease_seconds)
        set_fields: dict[str, Any] = {
            "lease_expires_at": expires,
            "updated_at": now,
            "progress_note": note,
        }
        if percent is not None:
            set_fields["progress_percent"] = percent
        doc = await self._db["missions"].find_one_and_update(
            {
                **self._mission_tenant_base(),
                "_id": mission_id,
                "status": "leased",
                "attempt_count": attempt_count,
            },
            {"$set": set_fields},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            existing = await self._db["missions"].find_one(
                {**self._mission_tenant_base(), "_id": mission_id}
            )
            if existing is None:
                raise MissionNotFoundError(mission_id=mission_id)
            raise StaleLeaseError(
                mission_id=mission_id,
                expected=existing.get("attempt_count"),
            )
        return doc

    async def list_mission_docs(self) -> list[dict[str, Any]]:
        cursor = self.missions.find({})
        return [doc async for doc in cursor]

    async def list_goal_docs(self) -> list[dict[str, Any]]:
        cursor = self.goals.find({})
        return [doc async for doc in cursor]

    async def list_experiment_docs(self) -> list[dict[str, Any]]:
        cursor = self.experiments.find({})
        return [doc async for doc in cursor]

    async def list_dead_end_docs(self) -> list[dict[str, Any]]:
        cursor = self.dead_ends.find({})
        return [doc async for doc in cursor]
