"""Research run modes (``fold0_smoke`` | ``full_cv``) and error-slice resources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from mymlfw.saas.ids import new_run_id
from mymlfw.saas.schemas import (
    ErrorSliceItem,
    ErrorSlicesResource,
    ResearchRunCreateRequest,
    ResearchRunMode,
    ResearchRunResponse,
)


@dataclass
class ResearchRunService:
    """In-memory research run scaffolding (Mongo ScopedCollection wiring later)."""

    workspace_id: str
    project_id: str
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    error_slices: dict[str, ErrorSlicesResource] = field(default_factory=dict)

    def create_run(self, body: ResearchRunCreateRequest) -> ResearchRunResponse:
        if body.mode not in (ResearchRunMode.fold0_smoke, ResearchRunMode.full_cv):
            raise ValueError("invalid_run_mode")
        run_id = new_run_id()
        now = datetime.now(UTC)
        doc = {
            "_id": run_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "notebook_id": body.notebook_id,
            "goal_id": body.goal_id,
            "mode": body.mode.value,
            "runner_id": body.runner_id,
            "hardware_fingerprint": body.hardware_fingerprint,
            "status": "queued",
            "schema_version": 1,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        self.runs[run_id] = doc
        # Empty resource until log_oof fills slices.
        self.error_slices[run_id] = ErrorSlicesResource(
            run_id=run_id,
            status="empty",
            slices=[],
            generated_at=None,
        )
        return ResearchRunResponse(
            run_id=run_id,
            mode=body.mode,
            status="queued",
            runner_id=body.runner_id,
            hardware_fingerprint=body.hardware_fingerprint,
            created_at=now,
        )

    def get_error_slices(self, run_id: str) -> ErrorSlicesResource:
        resource = self.error_slices.get(run_id)
        if resource is None:
            return ErrorSlicesResource(run_id=run_id, status="empty", slices=[])
        return resource

    def set_error_slices(
        self,
        run_id: str,
        *,
        oof_id: str | None,
        slices: list[ErrorSliceItem],
    ) -> ErrorSlicesResource:
        """Store residual slices for a run. Empty input stays status ``empty``."""
        if run_id not in self.runs:
            raise KeyError("run_not_found")
        resource = ErrorSlicesResource(
            run_id=run_id,
            oof_id=oof_id,
            slices=slices,
            generated_at=datetime.now(UTC),
            status="ready" if slices else "empty",
        )
        self.error_slices[run_id] = resource
        return resource

    def set_error_slices_stub(
        self,
        run_id: str,
        *,
        oof_id: str | None,
        slices: list[ErrorSliceItem],
    ) -> ErrorSlicesResource:
        return self.set_error_slices(run_id, oof_id=oof_id, slices=slices)


def suggested_next_mode(current: ResearchRunMode) -> ResearchRunMode | None:
    """Smoke first, then full_cv — never jump straight to full without smoke."""
    if current == ResearchRunMode.fold0_smoke:
        return ResearchRunMode.full_cv
    return None
