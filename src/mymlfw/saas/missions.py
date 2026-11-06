"""Mission claim / complete / progress services for API, CLI, and MCP."""

from __future__ import annotations

from typing import Any, Callable

from mymlfw.saas.brain_store import BRAIN_STORE, CampaignBrainStore
from mymlfw.saas.dashboard import compute_dashboard
from mymlfw.saas.db.errors import MissionNotFoundError, StaleLeaseError
from mymlfw.saas.db.project_db import DEFAULT_LEASE_SECONDS, MissionLeaseClaim, ProjectScopedDB
from mymlfw.saas.idempotency import IdempotencyStore, run_idempotent
from mymlfw.saas.schemas import (
    CompleteMissionResponse,
    DashboardResponse,
    MissionBrief,
    MissionOutcome,
    MissionStatus,
    ProjectListResponse,
    ProjectSummary,
    QueryProjectBrainResponse,
    ReportMissionProgressResponse,
)

ProjectDbFactory = Callable[[str, str], ProjectScopedDB]


class MissionService:
    """Thin orchestration over ``ProjectScopedDB`` (Mongo) or ``CampaignBrainStore``."""

    def __init__(
        self,
        *,
        brain: CampaignBrainStore | None = None,
        project_db_factory: ProjectDbFactory | None = None,
        idem_store: IdempotencyStore | None = None,
        mongo_db: Any | None = None,
    ) -> None:
        self.brain = brain or BRAIN_STORE
        self._project_db_factory = project_db_factory
        self.idem = idem_store or IdempotencyStore()
        self._mongo = mongo_db

    def _pdb(self, workspace_id: str, project_id: str) -> ProjectScopedDB | None:
        if self._project_db_factory is None:
            return None
        return self._project_db_factory(workspace_id, project_id)

    async def list_projects(self, workspace_id: str) -> ProjectListResponse:
        if self._mongo is not None:
            from mymlfw.saas.db import project_data

            return ProjectListResponse(
                projects=await project_data.list_projects(self._mongo, workspace_id)
            )
        return ProjectListResponse(projects=self.brain.list_projects(workspace_id))

    async def get_project_dashboard(
        self, workspace_id: str, project_id: str
    ) -> DashboardResponse | None:
        if self._mongo is not None:
            from mymlfw.saas.db import project_data

            return await project_data.load_dashboard(
                self._mongo, workspace_id, project_id
            )
        pdb = self._pdb(workspace_id, project_id)
        if pdb is not None:
            proj = self.brain.get_project(workspace_id, project_id)
            goals = await pdb.list_goal_docs()
            experiments = await pdb.list_experiment_docs()
            missions = await pdb.list_mission_docs()
            dead_ends = await pdb.list_dead_end_docs()
            if goals or experiments or missions or dead_ends:
                return compute_dashboard(
                    project_id=project_id,
                    goals=goals,
                    experiments=experiments,
                    missions=missions,
                    dead_ends=dead_ends,
                    folds_sha256=proj.get("folds_sha256") if proj else None,
                    adv_auc=proj.get("adv_auc") if proj else None,
                )
        return self.brain.dashboard(workspace_id, project_id)

    async def get_next_mission(
        self,
        *,
        workspace_id: str,
        project_id: str,
        lease_owner: str,
        idempotency_key: str | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        detail_level: str = "summary",
    ) -> MissionBrief | None:
        async def _claim() -> MissionBrief | None:
            claim = await self._claim(
                workspace_id=workspace_id,
                project_id=project_id,
                lease_owner=lease_owner,
                lease_seconds=lease_seconds,
            )
            if claim is None:
                return None
            return self._brief_from_claim(
                claim, project_id=project_id, detail_level=detail_level
            )

        result, _replayed = await run_idempotent(
            self.idem,
            scope=f"get_next_mission:{workspace_id}:{project_id}:{lease_owner}",
            key=idempotency_key,
            fn=_claim,
        )
        return result

    async def complete_mission(
        self,
        *,
        workspace_id: str,
        project_id: str,
        mission_id: str,
        lease_fencing_token: int,
        outcome: MissionOutcome | str,
        fold_scores: list[float] | None = None,
        notes: str = "",
        idempotency_key: str | None = None,
    ) -> CompleteMissionResponse:
        outcome_value = (
            outcome.value if isinstance(outcome, MissionOutcome) else str(outcome)
        )

        async def _complete() -> CompleteMissionResponse:
            doc = await self._complete(
                workspace_id=workspace_id,
                project_id=project_id,
                mission_id=mission_id,
                attempt_count=lease_fencing_token,
                outcome=outcome_value,
                fold_scores=fold_scores,
                notes=notes,
            )
            return CompleteMissionResponse(
                mission_id=mission_id,
                status=MissionStatus(doc["status"]),
                lease_fencing_token=lease_fencing_token,
                outcome=MissionOutcome(
                    doc.get("outcome")
                    if doc.get("outcome") in ("succeeded", "failed", "abandoned")
                    else outcome_value
                ),
                replayed=False,
            )

        result, replayed = await run_idempotent(
            self.idem,
            scope=f"complete_mission:{workspace_id}:{project_id}:{mission_id}",
            key=idempotency_key,
            fn=_complete,
        )
        if replayed and isinstance(result, CompleteMissionResponse):
            return result.model_copy(update={"replayed": True})
        return result

    async def report_mission_progress(
        self,
        *,
        workspace_id: str,
        project_id: str,
        mission_id: str,
        lease_fencing_token: int,
        note: str = "",
        percent: float | None = None,
        idempotency_key: str | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> ReportMissionProgressResponse:
        async def _renew() -> ReportMissionProgressResponse:
            doc = await self._renew(
                workspace_id=workspace_id,
                project_id=project_id,
                mission_id=mission_id,
                attempt_count=lease_fencing_token,
                lease_seconds=lease_seconds,
                note=note,
                percent=percent,
            )
            return ReportMissionProgressResponse(
                mission_id=mission_id,
                status=MissionStatus(doc["status"]),
                lease_fencing_token=lease_fencing_token,
                lease_expires_at=doc["lease_expires_at"],
                replayed=False,
            )

        result, replayed = await run_idempotent(
            self.idem,
            scope=f"report_mission_progress:{workspace_id}:{project_id}:{mission_id}",
            key=idempotency_key,
            fn=_renew,
        )
        if replayed and isinstance(result, ReportMissionProgressResponse):
            return result.model_copy(update={"replayed": True})
        return result

    async def query_project_brain(
        self,
        *,
        workspace_id: str,
        project_id: str,
        scope: str = "all",
        max_tokens: int = 512,
        detail_level: str = "summary",
        query: str = "",
    ) -> QueryProjectBrainResponse:
        _ = detail_level
        from mymlfw.saas.advise import query_project_brain_from_store

        store = self.brain
        if self._mongo is not None:
            from mymlfw.saas.db import project_data

            hydrated = await project_data.hydrate_brain_store(
                self._mongo, workspace_id, project_id
            )
            if hydrated is not None:
                store = hydrated
        return query_project_brain_from_store(
            store,
            workspace_id=workspace_id,
            project_id=project_id,
            scope=scope,
            max_tokens=max_tokens,
            query=query,
        )

    async def _claim(
        self,
        *,
        workspace_id: str,
        project_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> MissionLeaseClaim | None:
        pdb = self._pdb(workspace_id, project_id)
        if pdb is not None:
            return await pdb.claim_next_mission(
                lease_owner=lease_owner, lease_seconds=lease_seconds
            )
        return self.brain.claim_next_mission(
            workspace_id,
            project_id,
            lease_owner=lease_owner,
            lease_seconds=lease_seconds,
        )

    async def _complete(
        self,
        *,
        workspace_id: str,
        project_id: str,
        mission_id: str,
        attempt_count: int,
        outcome: str,
        fold_scores: list[float] | None,
        notes: str,
    ) -> dict[str, Any]:
        pdb = self._pdb(workspace_id, project_id)
        if pdb is not None:
            return await pdb.complete_mission_transactional(
                mission_id=mission_id,
                attempt_count=attempt_count,
                outcome=outcome,
                fold_scores=fold_scores,
                notes=notes,
            )
        return self.brain.complete_mission(
            workspace_id,
            project_id,
            mission_id=mission_id,
            attempt_count=attempt_count,
            outcome=outcome,
            fold_scores=fold_scores,
            notes=notes,
        )

    async def _renew(
        self,
        *,
        workspace_id: str,
        project_id: str,
        mission_id: str,
        attempt_count: int,
        lease_seconds: int,
        note: str,
        percent: float | None,
    ) -> dict[str, Any]:
        pdb = self._pdb(workspace_id, project_id)
        if pdb is not None:
            return await pdb.renew_mission_lease(
                mission_id=mission_id,
                attempt_count=attempt_count,
                lease_seconds=lease_seconds,
                note=note,
                percent=percent,
            )
        return self.brain.renew_mission_lease(
            workspace_id,
            project_id,
            mission_id=mission_id,
            attempt_count=attempt_count,
            lease_seconds=lease_seconds,
            note=note,
            percent=percent,
        )

    @staticmethod
    def _brief_from_claim(
        claim: MissionLeaseClaim,
        *,
        project_id: str,
        detail_level: str,
    ) -> MissionBrief:
        brief_md = claim.brief_md
        if not brief_md:
            brief_md = (
                f"# Mission `{claim.mission_id}`\n\n"
                f"Title: **{claim.title}**\n\n"
                "Call `complete_mission` with this `lease_fencing_token` when done.\n"
            )
        if detail_level == "summary" and len(brief_md) > 1200:
            brief_md = brief_md[:1200] + "\n…"
        return MissionBrief(
            mission_id=claim.mission_id,
            project_id=project_id,
            title=claim.title,
            mission_type=claim.mission_type,
            status=MissionStatus.leased,
            lease_fencing_token=claim.attempt_count,
            lease_owner=claim.lease_owner,
            lease_expires_at=claim.lease_expires_at,
            brief_md=brief_md,
            goal_id=claim.goal_id,
            template_id=claim.template_id,
            epoch_id=claim.epoch_id,
            detail_level="full" if detail_level == "full" else "summary",
        )


__all__ = [
    "MissionService",
    "MissionNotFoundError",
    "StaleLeaseError",
    "ProjectSummary",
]
