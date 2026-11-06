"""In-memory Campaign brain store (Wave 1 auth twin) + Demo Campaign seed."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from mymlfw.saas.dashboard import compute_dashboard
from mymlfw.saas.db.errors import MissionNotFoundError, StaleLeaseError
from mymlfw.saas.db.project_db import DEFAULT_LEASE_SECONDS, MissionLeaseClaim
from mymlfw.saas.ids import (
    new_dead_end_id,
    new_experiment_id,
    new_goal_id,
    new_mission_id,
    new_project_id,
    new_snapshot_id,
)
from mymlfw.saas.schemas import (
    DashboardResponse,
    DeadEndStatus,
    ExperimentStatus,
    GoalKind,
    GoalStatus,
    ProjectKind,
    ProjectSummary,
    PublicSnapshotResponse,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CampaignBrainStore:
    """Org-scoped projects / goals / experiments / dead_ends for Phase B.

    Production path when ``MYMLFW_MONGO_URI`` is set: Mongo via
    ``saas.db.project_data`` / ``ProjectScopedDB``. This in-memory store is
    only for unit tests and when Mongo is unset.
    """

    def __init__(self) -> None:
        self.projects: dict[str, dict[str, Any]] = {}  # project_id -> doc
        self.by_org: dict[str, list[str]] = {}  # org_id -> [project_id]
        self.goals: dict[str, list[dict[str, Any]]] = {}
        self.experiments: dict[str, list[dict[str, Any]]] = {}
        self.missions: dict[str, list[dict[str, Any]]] = {}
        self.dead_ends: dict[str, list[dict[str, Any]]] = {}
        self.sources: dict[str, list[dict[str, Any]]] = {}
        self.roadmap_strategies: dict[str, list[dict[str, Any]]] = {}
        self.progress: dict[str, list[dict[str, Any]]] = {}
        self.members: dict[str, list[dict[str, Any]]] = {}
        self.snapshots: dict[str, dict[str, Any]] = {}  # full slug -> doc
        self.axioms: dict[str, list[dict[str, Any]]] = {}
        self.episode_cards: dict[str, list[dict[str, Any]]] = {}

    def ensure_demo_campaign(
        self, *, org_id: str, org_slug: str
    ) -> ProjectSummary:
        """Idempotent Demo Campaign seed for studio time-to-value."""
        for pid in self.by_org.get(org_id, []):
            proj = self.projects[pid]
            if proj.get("is_demo"):
                return self._summary(proj)

        project_id = new_project_id()
        now = _utcnow()
        folds_sha = secrets.token_hex(32)
        project = {
            "_id": project_id,
            "workspace_id": org_id,
            "project_id": project_id,
            "schema_version": 1,
            "slug": "demo-campaign",
            "name": "Demo Campaign",
            "kind": ProjectKind.standalone.value,
            "is_demo": True,
            "epoch_id": "epoch_0",
            "folds_sha256": folds_sha,
            "adv_auc": 0.51,
            "n_folds": 5,
            "folds_artifact_key": f"projects/{project_id}/folds.parquet",
            "public_share_slug": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        self.projects[project_id] = project
        self.by_org.setdefault(org_id, []).append(project_id)

        goal_id = new_goal_id()
        goal = {
            "_id": goal_id,
            "id": goal_id,
            "workspace_id": org_id,
            "project_id": project_id,
            "schema_version": 1,
            "title": "Notebook CV >= 0.30",
            "kind": GoalKind.notebook_score.value,
            "metric_key": "cv_mean",
            "threshold": 0.30,
            "direction": "maximize",
            "constraints": ["cv_std<=0.05"],
            "status": GoalStatus.active.value,
            "priority": 10,
            "notes": "Demo primary goal",
            "best_value": 0.28,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        met_goal_id = new_goal_id()
        met_goal = {
            **{k: v for k, v in goal.items() if k not in ("_id", "id", "title", "status", "best_value")},
            "_id": met_goal_id,
            "id": met_goal_id,
            "title": "Smoke fold0 passes",
            "status": GoalStatus.met.value,
            "threshold": 0.20,
            "best_value": 0.22,
            "priority": 20,
        }
        self.goals[project_id] = [goal, met_goal]

        parent_id = new_experiment_id()
        child_id = new_experiment_id()
        parent = {
            "_id": parent_id,
            "workspace_id": org_id,
            "project_id": project_id,
            "schema_version": 1,
            "goal_id": goal_id,
            "parent_experiment_id": None,
            "epoch_id": "epoch_0",
            "variable": "baseline",
            "band_low": 0.0,
            "band_high": 0.05,
            "fold_scores": [0.27, 0.28, 0.26, 0.29, 0.28],
            "cv_mean": 0.276,
            "cv_std": 0.011,
            "cv_delta": 0.0,
            "verdict": "promote-candidate",
            "status": ExperimentStatus.closed.value,
            "teacher_oof_ids": [],
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        child = {
            "_id": child_id,
            "workspace_id": org_id,
            "project_id": project_id,
            "schema_version": 1,
            "goal_id": goal_id,
            "parent_experiment_id": parent_id,
            "epoch_id": "epoch_0",
            "variable": "lora_r=16",
            "band_low": 0.005,
            "band_high": 0.02,
            "fold_scores": [0.29, 0.30, 0.28, 0.31, 0.30],
            "cv_mean": 0.296,
            "cv_std": 0.011,
            "cv_delta": 0.02,
            "verdict": None,
            "status": ExperimentStatus.open.value,
            "teacher_oof_ids": [],
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        killed = {
            "_id": new_experiment_id(),
            "workspace_id": org_id,
            "project_id": project_id,
            "schema_version": 1,
            "goal_id": goal_id,
            "parent_experiment_id": parent_id,
            "epoch_id": "epoch_0",
            "variable": "dropout=0.5",
            "band_low": -0.02,
            "band_high": 0.01,
            "fold_scores": [0.25, 0.24, 0.26, 0.23, 0.25],
            "cv_mean": 0.246,
            "cv_std": 0.011,
            "cv_delta": -0.03,
            "verdict": "kill",
            "status": ExperimentStatus.closed.value,
            "teacher_oof_ids": [],
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        self.experiments[project_id] = [parent, child, killed]

        self.dead_ends[project_id] = [
            {
                "_id": new_dead_end_id(),
                "workspace_id": org_id,
                "project_id": project_id,
                "schema_version": 1,
                "variable": "dropout=0.5",
                "lesson": "High dropout collapsed fold SNR; keep <=0.2 on this corpus.",
                "epoch_id": "epoch_0",
                "status": DeadEndStatus.active_block.value,
                "times_retrieved": 0,
                "times_cited": 0,
                "utility_weight": 1.0,
                "snr_weight": 1.0,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        ]

        self.missions[project_id] = [
            {
                "_id": new_mission_id(),
                "workspace_id": org_id,
                "project_id": project_id,
                "schema_version": 1,
                "title": "split_setup",
                "status": "queued",
                "attempt_count": 0,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            },
            {
                "_id": new_mission_id(),
                "workspace_id": org_id,
                "project_id": project_id,
                "schema_version": 1,
                "title": "cpu_research",
                "status": "succeeded",
                "attempt_count": 1,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            },
        ]

        # Empty RAG stubs (schema presence only).
        self.axioms[project_id] = []
        self.episode_cards[project_id] = []
        _ = org_slug
        return self._summary(project)

    def list_projects(self, org_id: str) -> list[ProjectSummary]:
        return [
            self._summary(self.projects[pid])
            for pid in self.by_org.get(org_id, [])
            if self.projects[pid].get("deleted_at") is None
        ]

    def ensure_org_project(
        self,
        org_id: str,
        project_id: str,
        *,
        name: str | None = None,
    ) -> dict[str, Any] | None:
        """Upsert a project under ``org_id``. Returns None if id is owned by another org."""
        existing = self.projects.get(project_id)
        if existing is not None:
            if existing.get("workspace_id") != org_id:
                return None
            return existing
        if not str(project_id).startswith("prj_"):
            return None
        now = _utcnow()
        project = {
            "_id": project_id,
            "workspace_id": org_id,
            "project_id": project_id,
            "schema_version": 1,
            "slug": (name or project_id)[:48].lower().replace(" ", "-"),
            "name": name or project_id,
            "kind": ProjectKind.standalone.value,
            "is_demo": False,
            "epoch_id": "epoch_0",
            "folds_sha256": secrets.token_hex(32),
            "adv_auc": None,
            "n_folds": 5,
            "folds_artifact_key": f"projects/{project_id}/folds.parquet",
            "public_share_slug": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        self.projects[project_id] = project
        self.by_org.setdefault(org_id, []).append(project_id)
        self.goals.setdefault(project_id, [])
        self.experiments.setdefault(project_id, [])
        self.missions.setdefault(project_id, [])
        self.dead_ends.setdefault(project_id, [])
        self.progress.setdefault(project_id, [])
        self.members.setdefault(project_id, [])
        return project

    def create_project(self, org_id: str, body: Any) -> ProjectSummary:
        from mymlfw.saas.studio import memory_create_project

        return memory_create_project(self, org_id=org_id, body=body)

    def archive_project(self, org_id: str, project_id: str) -> Any:
        from mymlfw.saas.studio import memory_archive_project

        return memory_archive_project(self, org_id=org_id, project_id=project_id)

    def invite_member(
        self, org_id: str, project_id: str, body: Any, *, user_id: str | None = None
    ) -> Any:
        from mymlfw.saas.studio import memory_invite

        return memory_invite(
            self, org_id=org_id, project_id=project_id, body=body, user_id=user_id
        )

    def list_members(self, org_id: str, project_id: str) -> list[Any]:
        from mymlfw.saas.studio import member_from_doc

        if self.get_project(org_id, project_id) is None:
            raise KeyError("project_not_found")
        return [
            member_from_doc(doc) for doc in self.members.get(project_id, [])
        ]

    def list_goals(self, org_id: str, project_id: str) -> list[Any]:
        from mymlfw.saas.studio import goal_from_doc

        if self.get_project(org_id, project_id) is None:
            return []
        return [goal_from_doc(g) for g in self.goals.get(project_id, [])]

    def add_goal(self, org_id: str, project_id: str, body: Any) -> Any:
        from mymlfw.saas.studio import build_goal_doc, goal_from_doc

        if self.get_project(org_id, project_id) is None:
            raise KeyError("project_not_found")
        doc = build_goal_doc(
            workspace_id=org_id, project_id=project_id, body=body
        )
        self.goals.setdefault(project_id, []).append(doc)
        return goal_from_doc(doc)

    def update_goal(
        self, org_id: str, project_id: str, goal_id: str, body: Any
    ) -> Any:
        from mymlfw.saas.studio import apply_goal_update, goal_from_doc

        if self.get_project(org_id, project_id) is None:
            raise KeyError("project_not_found")
        for goal in self.goals.get(project_id, []):
            if goal.get("_id") == goal_id or goal.get("id") == goal_id:
                apply_goal_update(goal, body)
                return goal_from_doc(goal)
        raise KeyError("goal_not_found")

    def list_progress(self, org_id: str, project_id: str) -> list[Any]:
        from mymlfw.saas.studio import progress_from_doc

        if self.get_project(org_id, project_id) is None:
            return []
        notes = sorted(
            self.progress.get(project_id, []),
            key=lambda d: d.get("created_at") or _utcnow(),
            reverse=True,
        )
        return [progress_from_doc(n) for n in notes]

    def add_progress(self, org_id: str, project_id: str, body: Any) -> Any:
        from mymlfw.saas.studio import build_progress_doc, progress_from_doc

        if self.get_project(org_id, project_id) is None:
            raise KeyError("project_not_found")
        doc = build_progress_doc(
            workspace_id=org_id, project_id=project_id, body=body
        )
        self.progress.setdefault(project_id, []).append(doc)
        return progress_from_doc(doc)

    def list_dead_ends(self, org_id: str, project_id: str) -> list[Any]:
        from mymlfw.saas.studio import dead_end_from_doc

        if self.get_project(org_id, project_id) is None:
            return []
        return [dead_end_from_doc(d) for d in self.dead_ends.get(project_id, [])]

    def add_dead_end(self, org_id: str, project_id: str, body: Any) -> Any:
        from mymlfw.saas.studio import build_dead_end_doc, dead_end_from_doc

        proj = self.get_project(org_id, project_id)
        if proj is None:
            raise KeyError("project_not_found")
        doc = build_dead_end_doc(
            workspace_id=org_id,
            project_id=project_id,
            body=body,
            epoch_id=proj.get("epoch_id"),
        )
        self.dead_ends.setdefault(project_id, []).append(doc)
        return dead_end_from_doc(doc)

    def list_sources(self, org_id: str, project_id: str) -> list[Any]:
        from mymlfw.saas.studio import source_from_doc

        if self.get_project(org_id, project_id) is None:
            return []
        return [
            source_from_doc(d)
            for d in self.sources.get(project_id, [])
            if d.get("deleted_at") is None
        ]

    def add_source(self, org_id: str, project_id: str, body: Any) -> Any:
        from mymlfw.saas.studio import build_source_doc, source_from_doc

        if self.get_project(org_id, project_id) is None:
            raise KeyError("project_not_found")
        doc = build_source_doc(
            workspace_id=org_id, project_id=project_id, body=body
        )
        self.sources.setdefault(project_id, []).append(doc)
        return source_from_doc(doc)

    def update_source(
        self, org_id: str, project_id: str, source_id: str, body: Any
    ) -> Any:
        from mymlfw.saas.studio import apply_source_update, source_from_doc

        if self.get_project(org_id, project_id) is None:
            raise KeyError("project_not_found")
        for doc in self.sources.get(project_id, []):
            if (doc.get("id") or doc.get("_id")) == source_id and doc.get(
                "deleted_at"
            ) is None:
                apply_source_update(doc, body)
                return source_from_doc(doc)
        raise KeyError("source_not_found")

    def delete_source(self, org_id: str, project_id: str, source_id: str) -> bool:
        if self.get_project(org_id, project_id) is None:
            raise KeyError("project_not_found")
        for doc in self.sources.get(project_id, []):
            if (doc.get("id") or doc.get("_id")) == source_id and doc.get(
                "deleted_at"
            ) is None:
                doc["deleted_at"] = _utcnow()
                return True
        raise KeyError("source_not_found")

    def list_roadmap_strategies(self, org_id: str, project_id: str) -> list[Any]:
        from mymlfw.saas.studio import roadmap_strategy_from_doc

        if self.get_project(org_id, project_id) is None:
            return []
        rows = [
            d
            for d in self.roadmap_strategies.get(project_id, [])
            if d.get("deleted_at") is None
        ]
        rows.sort(
            key=lambda d: (int(d.get("priority") or 100), d.get("created_at") or _utcnow())
        )
        return [roadmap_strategy_from_doc(d) for d in rows]

    def add_roadmap_strategy(self, org_id: str, project_id: str, body: Any) -> Any:
        from mymlfw.saas.studio import (
            build_roadmap_strategy_doc,
            roadmap_strategy_from_doc,
        )

        if self.get_project(org_id, project_id) is None:
            raise KeyError("project_not_found")
        doc = build_roadmap_strategy_doc(
            workspace_id=org_id, project_id=project_id, body=body
        )
        self.roadmap_strategies.setdefault(project_id, []).append(doc)
        return roadmap_strategy_from_doc(doc)

    def update_roadmap_strategy(
        self, org_id: str, project_id: str, strategy_id: str, body: Any
    ) -> Any:
        from mymlfw.saas.studio import (
            apply_roadmap_strategy_update,
            roadmap_strategy_from_doc,
        )

        if self.get_project(org_id, project_id) is None:
            raise KeyError("project_not_found")
        for doc in self.roadmap_strategies.get(project_id, []):
            if (doc.get("id") or doc.get("_id")) == strategy_id and doc.get(
                "deleted_at"
            ) is None:
                apply_roadmap_strategy_update(doc, body)
                return roadmap_strategy_from_doc(doc)
        raise KeyError("roadmap_strategy_not_found")

    def delete_roadmap_strategy(
        self, org_id: str, project_id: str, strategy_id: str
    ) -> bool:
        if self.get_project(org_id, project_id) is None:
            raise KeyError("project_not_found")
        for doc in self.roadmap_strategies.get(project_id, []):
            if (doc.get("id") or doc.get("_id")) == strategy_id and doc.get(
                "deleted_at"
            ) is None:
                doc["deleted_at"] = _utcnow()
                return True
        raise KeyError("roadmap_strategy_not_found")

    def get_project_git(self, org_id: str, project_id: str) -> Any:
        from mymlfw.saas.schemas import ProjectGitInfo, ProjectGitResponse

        proj = self.get_project(org_id, project_id)
        if proj is None:
            raise KeyError("project_not_found")
        remote = (proj.get("git_remote") or "").strip()
        raw = proj.get("git_info")
        info = None
        if isinstance(raw, dict) and raw.get("remote"):
            info = ProjectGitInfo(
                **{k: v for k, v in raw.items() if k in ProjectGitInfo.model_fields}
            )
        elif remote:
            info = ProjectGitInfo(remote=remote)
        return ProjectGitResponse(
            project_id=project_id, linked=bool(remote), git=info
        )

    def set_project_git(
        self, org_id: str, project_id: str, remote: str, *, refresh: bool = True
    ) -> Any:
        from mymlfw.saas.git_info import build_git_info

        proj = self.get_project(org_id, project_id)
        if proj is None:
            raise KeyError("project_not_found")
        # In-memory path: parse only (no live GitHub) so unit tests stay offline.
        _ = refresh
        info = build_git_info(remote, live=False)
        proj["git_remote"] = info["remote"]
        proj["git_info"] = info
        proj["updated_at"] = _utcnow()
        return self.get_project_git(org_id, project_id)

    def refresh_project_git(self, org_id: str, project_id: str) -> Any:
        from mymlfw.saas.git_info import build_git_info

        proj = self.get_project(org_id, project_id)
        if proj is None:
            raise KeyError("project_not_found")
        remote = (proj.get("git_remote") or "").strip()
        if not remote:
            raise KeyError("git_not_linked")
        linked_at = None
        if isinstance(proj.get("git_info"), dict):
            linked_at = proj["git_info"].get("linked_at")
        info = build_git_info(remote, live=False)
        info["refresh_error"] = "stats_refresh_requires_mongo"
        if linked_at is not None:
            info["linked_at"] = linked_at
        proj["git_info"] = info
        proj["updated_at"] = _utcnow()
        return self.get_project_git(org_id, project_id)

    def clear_project_git(self, org_id: str, project_id: str) -> Any:
        proj = self.get_project(org_id, project_id)
        if proj is None:
            raise KeyError("project_not_found")
        proj["git_remote"] = None
        proj["git_info"] = None
        proj["updated_at"] = _utcnow()
        return self.get_project_git(org_id, project_id)

    def list_levers(self, org_id: str, project_id: str) -> list[Any]:
        from mymlfw.saas.studio import experiment_from_doc

        if self.get_project(org_id, project_id) is None:
            return []
        return [
            experiment_from_doc(e) for e in self.experiments.get(project_id, [])
        ]

    def open_lever(self, org_id: str, project_id: str, body: Any) -> Any:
        from mymlfw.saas.studio import build_experiment_doc, experiment_from_doc

        proj = self.get_project(org_id, project_id)
        if proj is None:
            raise KeyError("project_not_found")
        open_n = sum(
            1
            for e in self.experiments.get(project_id, [])
            if e.get("status") == ExperimentStatus.open.value
            and e.get("deleted_at") is None
        )
        if open_n >= 1:
            raise RuntimeError("one_open_lever")
        goal_ids = {
            g.get("_id") or g.get("id") for g in self.goals.get(project_id, [])
        }
        if body.goal_id not in goal_ids:
            raise KeyError("goal_not_found")
        doc = build_experiment_doc(
            workspace_id=org_id,
            project_id=project_id,
            body=body,
            epoch_id=proj.get("epoch_id"),
        )
        self.experiments.setdefault(project_id, []).append(doc)
        proj["active_execution_lock"] = {
            "holder_type": "lever",
            "holder_id": doc["_id"],
            "expires_at": _utcnow() + timedelta(hours=24),
        }
        proj["updated_at"] = _utcnow()
        return experiment_from_doc(doc)

    def close_lever(
        self, org_id: str, project_id: str, experiment_id: str, body: Any
    ) -> Any:
        from mymlfw.saas.studio import apply_lever_close, experiment_from_doc

        proj = self.get_project(org_id, project_id)
        if proj is None:
            raise KeyError("project_not_found")
        for exp in self.experiments.get(project_id, []):
            if exp.get("_id") == experiment_id and exp.get("deleted_at") is None:
                apply_lever_close(exp, body)
                lock = proj.get("active_execution_lock") or {}
                if lock.get("holder_id") == experiment_id:
                    proj["active_execution_lock"] = None
                proj["updated_at"] = _utcnow()
                return experiment_from_doc(exp)
        raise KeyError("lever_not_found")

    def list_missions(self, org_id: str, project_id: str) -> list[Any]:
        from mymlfw.saas.studio import mission_from_doc

        if self.get_project(org_id, project_id) is None:
            return []
        return [mission_from_doc(m) for m in self.missions.get(project_id, [])]

    def get_project(self, org_id: str, project_id: str) -> dict[str, Any] | None:
        proj = self.projects.get(project_id)
        if proj is None or proj.get("workspace_id") != org_id:
            return None
        if proj.get("deleted_at") is not None:
            return None
        return proj

    def set_kaggle_intel(
        self, org_id: str, project_id: str, panel: dict[str, Any]
    ) -> None:
        proj = self.get_project(org_id, project_id)
        if proj is None:
            raise KeyError("project_not_found")
        proj["kaggle_intel"] = dict(panel)
        proj["updated_at"] = _utcnow()

    def set_kaggle_data(
        self, org_id: str, project_id: str, inventory: dict[str, Any]
    ) -> None:
        proj = self.get_project(org_id, project_id)
        if proj is None:
            raise KeyError("project_not_found")
        proj["kaggle_data"] = dict(inventory)
        proj["updated_at"] = _utcnow()

    def dashboard(self, org_id: str, project_id: str) -> DashboardResponse | None:
        from mymlfw.saas.schemas import DashboardKagglePanel, ProjectKind

        proj = self.get_project(org_id, project_id)
        if proj is None:
            return None
        kaggle_panel = None
        intel = proj.get("kaggle_intel") if isinstance(proj.get("kaggle_intel"), dict) else None
        if intel or proj.get("kind") == ProjectKind.kaggle.value:
            from mymlfw.saas.db.kaggle_docs import finite_float, finite_int, parse_utc

            kaggle_panel = DashboardKagglePanel(
                linked=bool(proj.get("kaggle_competition")),
                rank=finite_int((intel or {}).get("rank")),
                public_score=finite_float((intel or {}).get("public_score")),
                medal_pace=(intel or {}).get("medal_pace"),
                last_sync=parse_utc((intel or {}).get("last_sync")),
            )
        return compute_dashboard(
            project_id=project_id,
            goals=self.goals.get(project_id, []),
            experiments=self.experiments.get(project_id, []),
            missions=self.missions.get(project_id, []),
            dead_ends=self.dead_ends.get(project_id, []),
            folds_sha256=proj.get("folds_sha256"),
            adv_auc=proj.get("adv_auc"),
            kaggle=kaggle_panel,
        )

    def claim_next_mission(
        self,
        org_id: str,
        project_id: str,
        *,
        lease_owner: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> MissionLeaseClaim | None:
        """In-memory atomic claim + fencing ``attempt_count`` (tests / no-Mongo)."""
        if self.get_project(org_id, project_id) is None:
            return None
        now = _utcnow()
        expires = now + timedelta(seconds=lease_seconds)
        for mission in self.missions.get(project_id, []):
            if mission.get("deleted_at") is not None:
                continue
            status = mission.get("status")
            expired = (
                status == "leased"
                and mission.get("lease_expires_at") is not None
                and mission["lease_expires_at"] <= now
            )
            if status == "queued" or expired:
                mission["status"] = "leased"
                mission["lease_owner"] = lease_owner
                mission["lease_expires_at"] = expires
                mission["attempt_count"] = int(mission.get("attempt_count") or 0) + 1
                mission["updated_at"] = now
                return MissionLeaseClaim(
                    mission_id=str(mission["_id"]),
                    attempt_count=int(mission["attempt_count"]),
                    lease_owner=lease_owner,
                    lease_expires_at=expires,
                    title=str(mission.get("title") or "mission"),
                    mission_type=str(mission.get("mission_type") or "custom"),
                    brief_md=str(mission.get("brief_md") or ""),
                    goal_id=mission.get("goal_id"),
                    template_id=mission.get("template_id"),
                    epoch_id=mission.get("epoch_id"),
                    doc=dict(mission),
                )
        return None

    def complete_mission(
        self,
        org_id: str,
        project_id: str,
        *,
        mission_id: str,
        attempt_count: int,
        outcome: str,
        fold_scores: list[float] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        mission = self._require_mission(org_id, project_id, mission_id)
        if (
            mission.get("status") != "leased"
            or int(mission.get("attempt_count") or 0) != attempt_count
        ):
            raise StaleLeaseError(
                mission_id=mission_id,
                expected=mission.get("attempt_count"),
            )
        now = _utcnow()
        if outcome in ("succeeded", "success", "promote"):
            status = "succeeded"
            normalized = "succeeded"
        elif outcome in ("abandoned", "abandoned_by_agent"):
            status = "abandoned_by_agent"
            normalized = "abandoned"
        else:
            status = "failed"
            normalized = "failed"
        mission["status"] = status
        mission["outcome"] = normalized
        mission["fold_scores"] = list(fold_scores or [])
        mission["completion_notes"] = notes
        mission["lease_expires_at"] = now
        mission["updated_at"] = now
        # Phase E: contrastive episode card + utility bandit on cited IDs.
        from mymlfw.saas.rag.contrastive import build_episode_card
        from mymlfw.saas.rag.consolidate import consolidate_project_brain
        from mymlfw.saas.rag.contradiction import mark_needs_reverification
        from mymlfw.saas.rag.utility import update_cited_memory_utility

        proj = self.projects.get(project_id) or {}
        variable = str(mission.get("variable") or mission.get("title") or "")
        card = build_episode_card(
            project_id=project_id,
            workspace_id=org_id,
            outcome=normalized,
            notes=notes,
            fold_scores=list(fold_scores or []),
            variable=variable,
            epoch_id=proj.get("epoch_id"),
            mission_title=str(mission.get("title") or ""),
        )
        self.episode_cards.setdefault(project_id, []).append(card)
        cited = list(mission.get("cited_memory_ids") or [])
        update_cited_memory_utility(
            [
                *self.dead_ends.get(project_id, []),
                *self.episode_cards.get(project_id, []),
            ],
            cited_ids=cited,
            outcome=normalized,
        )
        context_shifted = "context_shift" in (notes or "").lower() or bool(
            mission.get("context_conditions")
        )
        mark_needs_reverification(
            self.dead_ends.get(project_id, []),
            variable_family=variable.split("=", 1)[0] if variable else None,
            new_epoch_id=proj.get("epoch_id"),
            context_shifted=context_shifted,
        )
        closed = sum(
            1
            for m in self.missions.get(project_id, [])
            if m.get("status") in {"succeeded", "failed", "abandoned_by_agent"}
        )
        if closed > 0 and closed % 10 == 0:
            self.axioms[project_id] = consolidate_project_brain(
                project_id=project_id,
                workspace_id=org_id,
                dead_ends=self.dead_ends.get(project_id, []),
                episode_cards=self.episode_cards.get(project_id, []),
                epoch_id=proj.get("epoch_id"),
            )
        return dict(mission)

    def renew_mission_lease(
        self,
        org_id: str,
        project_id: str,
        *,
        mission_id: str,
        attempt_count: int,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        note: str = "",
        percent: float | None = None,
    ) -> dict[str, Any]:
        mission = self._require_mission(org_id, project_id, mission_id)
        if (
            mission.get("status") != "leased"
            or int(mission.get("attempt_count") or 0) != attempt_count
        ):
            raise StaleLeaseError(
                mission_id=mission_id,
                expected=mission.get("attempt_count"),
            )
        now = _utcnow()
        mission["lease_expires_at"] = now + timedelta(seconds=lease_seconds)
        mission["progress_note"] = note
        if percent is not None:
            mission["progress_percent"] = percent
        mission["updated_at"] = now
        return dict(mission)

    def _require_mission(
        self, org_id: str, project_id: str, mission_id: str
    ) -> dict[str, Any]:
        if self.get_project(org_id, project_id) is None:
            raise MissionNotFoundError(mission_id=mission_id)
        for mission in self.missions.get(project_id, []):
            if mission.get("_id") == mission_id and mission.get("deleted_at") is None:
                return mission
        raise MissionNotFoundError(mission_id=mission_id)

    def publish_snapshot(
        self,
        *,
        org_id: str,
        org_slug: str,
        project_id: str,
        include_goals: bool = True,
        include_lever_stats: bool = True,
        include_dead_end_lessons: bool = False,
    ) -> PublicSnapshotResponse | None:
        from mymlfw.saas.public_share import build_redacted_snapshot, make_share_slug

        proj = self.get_project(org_id, project_id)
        if proj is None:
            return None
        dash = self.dashboard(org_id, project_id)
        assert dash is not None
        entropy = secrets.token_urlsafe(9)
        slug = make_share_slug(proj["slug"], entropy)
        redacted = build_redacted_snapshot(
            project=proj,
            dashboard=dash,
            goals=self.goals.get(project_id, []) if include_goals else [],
            dead_ends=self.dead_ends.get(project_id, []),
            include_goals=include_goals,
            include_lever_stats=include_lever_stats,
            include_dead_end_lessons=include_dead_end_lessons,
        )
        snap_id = new_snapshot_id()
        doc = {
            "_id": snap_id,
            "workspace_id": org_id,
            "project_id": project_id,
            "schema_version": 1,
            "slug": slug,
            "org_slug": org_slug,
            "project_slug": proj["slug"],
            "entropy": entropy,
            "redacted": redacted,
            "created_at": _utcnow(),
            "deleted_at": None,
        }
        self.snapshots[slug] = doc
        proj["public_share_slug"] = slug
        return PublicSnapshotResponse(
            slug=slug,
            org_slug=org_slug,
            project_slug=proj["slug"],
            share_path=f"/p/{org_slug}/{slug}",
            redacted=redacted,
            entropy=entropy,
        )

    def get_public_snapshot(self, org_slug: str, slug: str) -> dict[str, Any] | None:
        doc = self.snapshots.get(slug)
        if doc is None or doc.get("org_slug") != org_slug:
            return None
        return doc

    @staticmethod
    def _summary(proj: dict[str, Any]) -> ProjectSummary:
        from mymlfw.saas.schemas import FoldMeta

        return ProjectSummary(
            id=proj["_id"],
            slug=proj["slug"],
            name=proj["name"],
            kind=ProjectKind(proj["kind"]),
            is_demo=bool(proj.get("is_demo")),
            folds=FoldMeta(
                folds_sha256=proj.get("folds_sha256"),
                adv_auc=proj.get("adv_auc"),
                epoch_id=proj.get("epoch_id"),
                n_folds=proj.get("n_folds"),
                artifact_key=proj.get("folds_artifact_key"),
            ),
            public_share_slug=proj.get("public_share_slug"),
            updated_at=proj.get("updated_at"),
        )


BRAIN_STORE = CampaignBrainStore()
