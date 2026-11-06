"""Frozen API / document contracts for Campaign SaaS (Phase 0).

Extend this module before inventing new JSON field names; regenerate
``contracts/openapi.json`` after changes.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Prefixed ULID helpers -------------------------------------------------

ULID_PREFIXES: dict[str, str] = {
    "org": "org_",
    "usr": "usr_",
    "prj": "prj_",
    "exp": "exp_",
    "gol": "gol_",
    "msn": "msn_",
    "ded": "ded_",
    "src": "src_",
    "rds": "rds_",
    "gap": "gap_",
    "aps": "aps_",
    "nd": "nd_",
    "crd": "crd_",
    "run": "run_",
    "oof": "oof_",
    "tok": "tok_",
    "obx": "obx_",
    "rnr": "rnr_",
    "jtk": "jtk_",
    "job": "job_",
    "pub": "pub_",
    "axm": "axm_",
    "epc": "epc_",
    "mem": "mem_",
    "cpa": "cpa_",
    "prg": "prg_",
}


def prefixed_ulid_pattern(prefix: str) -> str:
    """Regex for a Stripe-style prefixed ULID (26 Crockford chars)."""
    return rf"^{prefix}[0-9A-HJKMNP-TV-Z]{{26}}$"


PrefixedId = Annotated[str, Field(min_length=4, max_length=40)]


class FiniteMetric(BaseModel):
    """Metric wrapper that forbids NaN/Inf at the API boundary."""

    model_config = ConfigDict(extra="forbid")

    value: Annotated[float, Field(allow_inf_nan=False)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TenantDocument(ApiModel):
    """Base fields for all project-scoped Mongo documents."""

    id: PrefixedId = Field(alias="_id")
    workspace_id: PrefixedId
    project_id: PrefixedId
    schema_version: int = 1
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProjectKind(str, Enum):
    standalone = "standalone"
    kaggle = "kaggle"


class GoalKind(str, Enum):
    notebook_score = "notebook_score"
    kaggle_public = "kaggle_public"
    kaggle_private = "kaggle_private"
    cv_delta = "cv_delta"
    custom = "custom"


class GoalDirection(str, Enum):
    maximize = "maximize"
    minimize = "minimize"


class GoalStatus(str, Enum):
    active = "active"
    met = "met"
    abandoned = "abandoned"


class ErrorBody(ApiModel):
    error_code: str
    message: str
    suggested_fix: str | None = None
    details: dict[str, Any] | None = None


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    service: str = "mymlfw-api"
    version: str


class RegisterRequest(ApiModel):
    email: Annotated[str, Field(min_length=3, max_length=320)]
    password: Annotated[str, Field(min_length=8, max_length=128)]
    display_name: Annotated[str, Field(min_length=1, max_length=120)] = "dev"

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return value.strip().lower()


class LoginRequest(ApiModel):
    email: Annotated[str, Field(min_length=3, max_length=320)]
    password: Annotated[str, Field(min_length=8, max_length=128)]

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenResponse(ApiModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user_id: PrefixedId
    org_id: PrefixedId | None = None


class OrgEntitlements(ApiModel):
    max_private_projects: int = 5
    max_agents: int = 2
    max_llm_cost_micros_day: int = 5_000_000
    max_cloud_micros_day: int = 0
    advise_per_day: int = 20


class FeatureFlags(ApiModel):
    cloud_runners: bool = False
    night_shift: bool = False
    kaggle_sync: bool = False
    git_sync: bool = False
    mcp_oauth: bool = False


class OrgFeatureFlagsUpdate(ApiModel):
    """Owner PATCH for org feature flags (cloud_runners / night_shift / …)."""

    cloud_runners: bool | None = None
    night_shift: bool | None = None
    kaggle_sync: bool | None = None
    git_sync: bool | None = None
    mcp_oauth: bool | None = None


class OrgResponse(ApiModel):
    id: PrefixedId
    slug: str
    name: str
    plan: str = "dev"
    entitlements: OrgEntitlements = Field(default_factory=OrgEntitlements)
    feature_flags: FeatureFlags = Field(default_factory=FeatureFlags)


class UserResponse(ApiModel):
    id: PrefixedId
    email: str
    display_name: str


class MeResponse(ApiModel):
    user: UserResponse
    org: OrgResponse | None = None
    persona: str | None = None


class PersonaSwitchRequest(ApiModel):
    persona: Literal["owner", "member", "viewer", "agent"]


class ClientVersionWarning(ApiModel):
    client_version: str
    server_version: str
    level: Literal["warn", "reject"]


class OutboxEventCreate(ApiModel):
    event_type: str
    payload: dict[str, Any]
    workspace_id: PrefixedId
    project_id: PrefixedId | None = None


class MetricSample(ApiModel):
    """Finite metric payload used at API boundaries."""

    name: str
    value: Annotated[float, Field(allow_inf_nan=False)]


# --- Phase B2: MCP missions / PATs ------------------------------------------


class MissionStatus(str, Enum):
    queued = "queued"
    leased = "leased"
    succeeded = "succeeded"
    failed = "failed"
    abandoned_by_agent = "abandoned_by_agent"


class MissionOutcome(str, Enum):
    succeeded = "succeeded"
    failed = "failed"
    abandoned = "abandoned"


class MissionBrief(ApiModel):
    """Compact brief returned by ``get_next_mission`` (worktree path lands in E2)."""

    mission_id: PrefixedId
    project_id: PrefixedId
    title: str
    mission_type: str = "custom"
    status: MissionStatus = MissionStatus.leased
    lease_fencing_token: int
    lease_owner: str
    lease_expires_at: datetime
    brief_md: str = ""
    goal_id: PrefixedId | None = None
    template_id: str | None = None
    epoch_id: str | None = None
    detail_level: Literal["summary", "full"] = "summary"


class CompleteMissionRequest(ApiModel):
    mission_id: PrefixedId
    lease_fencing_token: int
    outcome: MissionOutcome
    fold_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )
    notes: str = ""
    idempotency_key: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class CompleteMissionResponse(ApiModel):
    mission_id: PrefixedId
    status: MissionStatus
    lease_fencing_token: int
    outcome: MissionOutcome
    replayed: bool = False


class ReportMissionProgressRequest(ApiModel):
    mission_id: PrefixedId
    lease_fencing_token: int
    note: str = ""
    percent: Annotated[float | None, Field(default=None, ge=0, le=100, allow_inf_nan=False)] = (
        None
    )
    idempotency_key: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class ReportMissionProgressResponse(ApiModel):
    mission_id: PrefixedId
    status: MissionStatus
    lease_fencing_token: int
    lease_expires_at: datetime
    replayed: bool = False


class QueryProjectBrainRequest(ApiModel):
    """Mid-mission RAG query (Phase E)."""

    project_id: PrefixedId
    scope: Literal["dead_ends", "episodes", "kaggle_intel", "all"] = "all"
    max_tokens: Annotated[int, Field(ge=64, le=8192)] = 512
    detail_level: Literal["summary", "full"] = "summary"
    query: Annotated[str, Field(default="", max_length=2000)] = ""


class BrainHit(ApiModel):
    doc_id: PrefixedId
    doc_type: Literal["promoted", "dead_end", "kaggle_intel", "episode", "axiom"]
    bucket: Literal["A", "B", "C"]
    text: str
    score: Annotated[float, Field(allow_inf_nan=False)] = 0.0
    epoch_id: str | None = None
    utility_weight: Annotated[float, Field(default=1.0, allow_inf_nan=False)] = 1.0
    badge: str | None = None


class QueryProjectBrainResponse(ApiModel):
    status: Literal["ready", "not_ready", "empty"] = "ready"
    message: str = ""
    results: list[BrainHit] = Field(default_factory=list)
    grounding_score: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    axioms: list[str] = Field(default_factory=list)


class AdviseRequest(ApiModel):
    project_id: PrefixedId
    task: Annotated[str, Field(min_length=1, max_length=2000)] = "next experiment"
    max_missions: Annotated[int, Field(ge=1, le=8)] = 3


class AdviseMissionDraft(ApiModel):
    title: Annotated[str, Field(min_length=1, max_length=240)]
    goal_id: PrefixedId | None = None
    rationale_md: str = ""
    cited_ids: list[PrefixedId] = Field(default_factory=list)


class AdviseResponse(ApiModel):
    project_id: PrefixedId
    brief_md: str
    proposed_missions: list[AdviseMissionDraft] = Field(default_factory=list)
    buckets: dict[str, list[BrainHit]] = Field(default_factory=dict)
    grounding_score: Annotated[float, Field(allow_inf_nan=False)] = 0.0
    strategy_efficacy: list[str] = Field(default_factory=list)
    axioms: list[str] = Field(default_factory=list)
    citation_firewall: dict[str, Any] = Field(default_factory=dict)


class PatCreateRequest(ApiModel):
    """Mint an MCP PAT for the current org (plaintext returned once).

    At most one **active** PAT per workspace. Pass ``replace=true`` to revoke
    the existing active token(s) and mint a new one.
    """

    scopes: list[str] = Field(default_factory=lambda: ["mcp:worker"])
    label: str = "mcp-worker"
    project_id: PrefixedId | None = None
    replace: bool = False


class PatCreateResponse(ApiModel):
    """Plaintext token shown once; only hash + prefix are retained."""

    token_id: PrefixedId
    token_prefix: str
    token: str
    workspace_id: PrefixedId
    project_id: PrefixedId | None = None
    scopes: list[str] = Field(default_factory=lambda: ["mcp:worker"])
    replaced_token_ids: list[PrefixedId] = Field(default_factory=list)


class PatListItem(ApiModel):
    """Safe row for Settings / Ops — never includes the raw token."""

    token_id: PrefixedId
    token_prefix: str
    workspace_id: PrefixedId
    project_id: PrefixedId | None = None
    scopes: list[str] = Field(default_factory=list)
    label: str = ""
    created_at: datetime | None = None
    revoked_at: datetime | None = None


class PatPrincipal(ApiModel):
    token_id: PrefixedId
    workspace_id: PrefixedId
    project_id: PrefixedId | None = None
    scopes: list[str] = Field(default_factory=list)
    label: str = ""


# --- Phase B: goals / experiments / dead_ends / dashboard -------------------


class ExperimentStatus(str, Enum):
    open = "open"
    closed = "closed"


class DeadEndStatus(str, Enum):
    active_block = "active_block"
    needs_reverification = "needs_reverification"


class FoldSnrLabel(str, Enum):
    solid = "SOLID"
    noise = "NOISE"


class FoldMeta(ApiModel):
    """Canonical folds.parquet registry metadata on a project."""

    folds_sha256: str | None = None
    adv_auc: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    epoch_id: str | None = None
    n_folds: int | None = None
    artifact_key: str | None = None


class ProjectGoalCreate(ApiModel):
    title: Annotated[str, Field(min_length=1, max_length=240)]
    kind: GoalKind = GoalKind.notebook_score
    metric_key: Annotated[str, Field(min_length=1, max_length=64)] = "cv_mean"
    threshold: Annotated[float, Field(allow_inf_nan=False)]
    direction: GoalDirection = GoalDirection.maximize
    constraints: list[str] = Field(default_factory=list)
    priority: int = 100
    notes: str = ""


class ProjectGoalUpdate(ApiModel):
    """Partial goal update (status / threshold / notes) for GOALS CRUD."""

    title: Annotated[str, Field(min_length=1, max_length=240)] | None = None
    status: GoalStatus | None = None
    threshold: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    notes: str | None = None
    priority: int | None = None
    best_value: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None


class ProjectGoalResponse(ApiModel):
    id: PrefixedId
    project_id: PrefixedId
    title: str
    kind: GoalKind
    metric_key: str
    threshold: Annotated[float, Field(allow_inf_nan=False)]
    direction: GoalDirection
    constraints: list[str] = Field(default_factory=list)
    status: GoalStatus = GoalStatus.active
    priority: int = 100
    notes: str = ""
    best_value: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None


class ProjectGoalListResponse(ApiModel):
    goals: list[ProjectGoalResponse] = Field(default_factory=list)


class ExperimentCreate(ApiModel):
    goal_id: PrefixedId
    variable: Annotated[str, Field(min_length=1, max_length=240)]
    band_low: Annotated[float, Field(allow_inf_nan=False)]
    band_high: Annotated[float, Field(allow_inf_nan=False)]
    parent_experiment_id: PrefixedId | None = None
    epoch_id: str | None = None
    fold_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )
    teacher_oof_ids: list[PrefixedId] = Field(default_factory=list)
    strategy: str | None = None
    parent_oof_ids: list[PrefixedId] = Field(default_factory=list)
    ensemble_weights: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )


class ExperimentResponse(ApiModel):
    id: PrefixedId
    project_id: PrefixedId
    goal_id: PrefixedId
    parent_experiment_id: PrefixedId | None = None
    epoch_id: str | None = None
    variable: str
    band_low: Annotated[float, Field(allow_inf_nan=False)]
    band_high: Annotated[float, Field(allow_inf_nan=False)]
    fold_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )
    cv_mean: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    cv_std: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    cv_delta: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    verdict: str | None = None
    status: ExperimentStatus = ExperimentStatus.open
    teacher_oof_ids: list[PrefixedId] = Field(default_factory=list)
    strategy: str | None = None
    parent_oof_ids: list[PrefixedId] = Field(default_factory=list)
    ensemble_weights: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )


class DeadEndCreate(ApiModel):
    variable: Annotated[str, Field(min_length=1, max_length=240)]
    lesson: Annotated[str, Field(min_length=1, max_length=2000)]
    epoch_id: str | None = None
    status: DeadEndStatus = DeadEndStatus.active_block


class DeadEndResponse(ApiModel):
    id: PrefixedId
    project_id: PrefixedId
    variable: str
    lesson: str
    epoch_id: str | None = None
    status: DeadEndStatus = DeadEndStatus.active_block
    # Utility counters (RAG bandit; empty until Phase E)
    times_retrieved: int = 0
    times_cited: int = 0
    utility_weight: Annotated[float, Field(default=1.0, allow_inf_nan=False)] = 1.0
    snr_weight: Annotated[float, Field(default=1.0, allow_inf_nan=False)] = 1.0


class DeadEndListResponse(ApiModel):
    dead_ends: list[DeadEndResponse] = Field(default_factory=list)


class ProjectSourceCreate(ApiModel):
    """User-curated link for a project (paper, notebook, dataset, write-up)."""

    title: Annotated[str, Field(min_length=1, max_length=240)]
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    description: Annotated[str, Field(default="", max_length=4000)] = ""

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        cleaned = value.strip()
        lower = cleaned.lower()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            raise ValueError("url_must_be_http_or_https")
        return cleaned


class ProjectSourceUpdate(ApiModel):
    title: Annotated[str, Field(min_length=1, max_length=240)] | None = None
    url: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    description: Annotated[str, Field(max_length=4000)] | None = None

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        lower = cleaned.lower()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            raise ValueError("url_must_be_http_or_https")
        return cleaned


class ProjectSourceResponse(ApiModel):
    id: PrefixedId
    project_id: PrefixedId
    title: str
    url: str
    description: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectSourceListResponse(ApiModel):
    sources: list[ProjectSourceResponse] = Field(default_factory=list)


class RoadmapStrategyStatus(str, Enum):
    planned = "planned"
    in_progress = "in_progress"
    executed = "executed"
    cancelled = "cancelled"


class RoadmapStrategyCreate(ApiModel):
    """Campaign roadmap strategy — plan first, results after execution."""

    title: Annotated[str, Field(min_length=1, max_length=240)]
    plan: Annotated[str, Field(min_length=1, max_length=8000)]
    priority: int = 100
    status: RoadmapStrategyStatus = RoadmapStrategyStatus.planned


class RoadmapStrategyUpdate(ApiModel):
    title: Annotated[str, Field(min_length=1, max_length=240)] | None = None
    plan: Annotated[str, Field(min_length=1, max_length=8000)] | None = None
    status: RoadmapStrategyStatus | None = None
    result: Annotated[str, Field(max_length=8000)] | None = None
    result_metric: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None
    priority: int | None = None


class RoadmapStrategyResponse(ApiModel):
    id: PrefixedId
    project_id: PrefixedId
    title: str
    plan: str
    status: RoadmapStrategyStatus = RoadmapStrategyStatus.planned
    result: str = ""
    result_metric: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = (
        None
    )
    priority: int = 100
    created_at: datetime | None = None
    updated_at: datetime | None = None
    executed_at: datetime | None = None


class RoadmapStrategyListResponse(ApiModel):
    strategies: list[RoadmapStrategyResponse] = Field(default_factory=list)


class ProjectGitLinkRequest(ApiModel):
    """Link a git remote to the project (https or git@)."""

    remote: Annotated[str, Field(min_length=1, max_length=500)]
    refresh: bool = True


class ProjectGitInfo(ApiModel):
    """Parsed remote + optional public host stats (cached on the project)."""

    remote: str
    host: str = ""
    owner: str = ""
    name: str = ""
    full_name: str = ""
    provider: Literal["github", "other"] = "other"
    html_url: str | None = None
    description: str = ""
    default_branch: str | None = None
    language: str | None = None
    license_spdx: str | None = None
    stars: int | None = None
    forks: int | None = None
    open_issues: int | None = None
    watchers: int | None = None
    size_kb: int | None = None
    pushed_at: datetime | str | None = None
    created_at_remote: datetime | str | None = None
    private: bool | None = None
    archived: bool | None = None
    topics: list[str] = Field(default_factory=list)
    refreshed_at: datetime | None = None
    refresh_error: str | None = None
    linked_at: datetime | None = None


class ProjectGitResponse(ApiModel):
    project_id: PrefixedId
    linked: bool = False
    git: ProjectGitInfo | None = None


class McpGapSeverity(str, Enum):
    blocker = "blocker"
    annoying = "annoying"
    nice_to_have = "nice_to_have"


class McpGapReportCreate(ApiModel):
    """Agent-reported missing MCP capability / friction while syncing a campaign."""

    title: Annotated[str, Field(min_length=1, max_length=240)]
    needed_capability: Annotated[str, Field(min_length=1, max_length=2000)]
    context: Annotated[str, Field(default="", max_length=4000)] = ""
    workaround: Annotated[str, Field(default="", max_length=4000)] = ""
    severity: McpGapSeverity = McpGapSeverity.annoying
    project_id: PrefixedId | None = None
    suggested_tool_name: Annotated[str, Field(default="", max_length=120)] = ""
    suggested_args_schema: Annotated[str, Field(default="", max_length=4000)] = ""


class McpGapReportResponse(ApiModel):
    id: PrefixedId
    workspace_id: PrefixedId
    project_id: PrefixedId | None = None
    title: str
    needed_capability: str
    context: str = ""
    workaround: str = ""
    severity: McpGapSeverity = McpGapSeverity.annoying
    suggested_tool_name: str = ""
    suggested_args_schema: str = ""
    status: Literal["open", "accepted", "wontfix", "shipped"] = "open"
    created_at: datetime | None = None


class McpGapReportListResponse(ApiModel):
    gaps: list[McpGapReportResponse] = Field(default_factory=list)


class ProgressNoteCreate(ApiModel):
    """Daily progress note (CLI ``progress add --note``)."""

    note: Annotated[str, Field(min_length=1, max_length=4000)]


class ProgressNoteResponse(ApiModel):
    id: PrefixedId
    project_id: PrefixedId
    note: str
    created_at: datetime


class ProgressNoteListResponse(ApiModel):
    notes: list[ProgressNoteResponse] = Field(default_factory=list)


class LeverCloseRequest(ApiModel):
    """Close an open lever (experiment); CLI ``lever close``."""

    verdict: Annotated[str, Field(default="", max_length=64)] = ""
    fold_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )
    notes: str = ""


class LeverListResponse(ApiModel):
    levers: list[ExperimentResponse] = Field(default_factory=list)


class MissionListItem(ApiModel):
    """Human dashboard mission row (claim/complete stay MCP-primary)."""

    id: PrefixedId
    project_id: PrefixedId
    title: str
    status: MissionStatus = MissionStatus.queued
    mission_type: str = "custom"
    goal_id: PrefixedId | None = None


class MissionListResponse(ApiModel):
    missions: list[MissionListItem] = Field(default_factory=list)


class FoldSnrBadge(ApiModel):
    wins: int
    n_folds: int
    win_ratio: Annotated[float, Field(allow_inf_nan=False)]
    snr: Annotated[float, Field(allow_inf_nan=False)]  # ±inf clamped by fold_badges
    label: FoldSnrLabel
    display: str


class DashboardHeader(ApiModel):
    primary_goal_id: PrefixedId | None = None
    primary_goal_title: str | None = None
    primary_threshold: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None
    primary_latest: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None
    primary_gap: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None
    primary_status: Literal["MET", "MISSED", "OPEN"] = "OPEN"
    progress_pct: Annotated[float, Field(allow_inf_nan=False)]
    goals_met_ratio: Annotated[float, Field(allow_inf_nan=False)]
    lever_close_rate: Annotated[float, Field(allow_inf_nan=False)]
    mission_success_rate: Annotated[float, Field(allow_inf_nan=False)]
    folds_sha256: str | None = None
    adv_auc: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    adv_auc_label: str = "UNKNOWN"
    days_active: int = 0
    last_activity: datetime | None = None


class DashboardGoalsPanel(ApiModel):
    active: int = 0
    met: int = 0
    abandoned: int = 0
    count: int = 0
    mean_gap: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None


class DashboardScoresPanel(ApiModel):
    """Overview Scores — empty-typed until score snapshots land."""

    best_public: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    best_cv: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    cv_std: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    fold_stability: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None
    last_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )
    shake_up_index: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None


class DashboardLeversPanel(ApiModel):
    open: int = 0
    closed: int = 0
    kills: int = 0
    promotes: int = 0
    fold_badges: list[FoldSnrBadge] = Field(default_factory=list)
    sparkline: list[dict[str, Any]] = Field(default_factory=list)


class DashboardEnsemblePanel(ApiModel):
    correlation_matrix: list[list[Annotated[float, Field(allow_inf_nan=False)]]] = (
        Field(default_factory=list)
    )
    blend_weights: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )
    last_cv: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    recipe: str = ""


class DashboardComputePanel(ApiModel):
    cv_delta_per_gpu_hour: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None
    cv_delta_per_cpu_hour: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None


class DashboardParadigmsPanel(ApiModel):
    count: int = 0
    success_rate: Annotated[float, Field(allow_inf_nan=False)] = 0.0
    last_shift_title: str | None = None
    last_shift_metric: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None


class DashboardStrategyRow(ApiModel):
    name: str
    levers: int = 0
    cv_delta: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None


class DashboardStrategiesPanel(ApiModel):
    total: int = 0
    active: int = 0
    ranked: list[DashboardStrategyRow] = Field(default_factory=list)
    top_strategy: str | None = None
    top_cv_delta: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None


class DashboardResearchPanel(ApiModel):
    notebooks_tracked: int = 0
    runs_7d: int = 0
    pct_met_bound: Annotated[float, Field(allow_inf_nan=False)] = 0.0
    mean_runtime_sec: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None


class DashboardMissionsPanel(ApiModel):
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    agent_connected: bool = False
    last_mission_type: str | None = None


class DashboardDeadEndsPanel(ApiModel):
    count: int = 0
    top_variables: list[str] = Field(default_factory=list)
    confirmed_large_gap_pct: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None


class DashboardDailyProgressPanel(ApiModel):
    streak_days: int = 0
    notes_last_7d: list[str] = Field(default_factory=list)
    calendar_strip: str = ""


class DashboardLeaderboardRow(ApiModel):
    rank: int | None = None
    team_name: str | None = None
    score: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    is_me: bool = False


class DashboardKagglePanel(ApiModel):
    linked: bool = False
    competition: str | None = None
    rank: int | None = None
    public_score: Annotated[
        float | None, Field(default=None, allow_inf_nan=False)
    ] = None
    medal_pace: str | None = None
    last_sync: datetime | None = None
    submission_count: int = 0
    my_kernel_count: int = 0
    leaderboard_top: list[DashboardLeaderboardRow] = Field(default_factory=list)


class DashboardGitPanel(ApiModel):
    linked: bool = False
    last_sync: datetime | None = None
    commits_pushed_7d: int = 0
    status: Literal["unlinked", "linked", "synced", "behind", "error"] = "unlinked"


class DashboardBrainPanel(ApiModel):
    episode_count: int = 0
    field_notes: int = 0
    retrieval_hits_last_advise: int = 0


class DashboardResponse(ApiModel):
    project_id: PrefixedId
    header: DashboardHeader
    goals: DashboardGoalsPanel
    scores: DashboardScoresPanel = Field(default_factory=DashboardScoresPanel)
    levers: DashboardLeversPanel
    ensemble: DashboardEnsemblePanel = Field(default_factory=DashboardEnsemblePanel)
    compute: DashboardComputePanel = Field(default_factory=DashboardComputePanel)
    paradigms: DashboardParadigmsPanel = Field(default_factory=DashboardParadigmsPanel)
    strategies: DashboardStrategiesPanel = Field(
        default_factory=DashboardStrategiesPanel
    )
    research: DashboardResearchPanel = Field(default_factory=DashboardResearchPanel)
    missions: DashboardMissionsPanel
    dead_ends: DashboardDeadEndsPanel
    daily_progress: DashboardDailyProgressPanel = Field(
        default_factory=DashboardDailyProgressPanel
    )
    kaggle: DashboardKagglePanel = Field(default_factory=DashboardKagglePanel)
    git: DashboardGitPanel = Field(default_factory=DashboardGitPanel)
    brain: DashboardBrainPanel = Field(default_factory=DashboardBrainPanel)


class ProjectSummary(ApiModel):
    id: PrefixedId
    slug: str
    name: str
    kind: ProjectKind
    is_demo: bool = False
    folds: FoldMeta = Field(default_factory=FoldMeta)
    public_share_slug: str | None = None
    updated_at: datetime | None = None


class ProjectListResponse(ApiModel):
    projects: list[ProjectSummary]


class ProjectCreate(ApiModel):
    """Studio New project wizard + CLI ``project create``."""

    name: Annotated[str, Field(min_length=1, max_length=120)]
    kind: ProjectKind = ProjectKind.standalone
    goals: list[ProjectGoalCreate] = Field(min_length=1)
    kaggle_competition: Annotated[str, Field(default="", max_length=200)] = ""
    git_remote: Annotated[str, Field(default="", max_length=500)] = ""


class ProjectInviteCreate(ApiModel):
    """Studio invite / CLI ``project invite``."""

    email: Annotated[str, Field(min_length=3, max_length=320)]
    role: Literal["owner", "member", "viewer"] = "member"

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return value.strip().lower()


class ProjectMemberResponse(ApiModel):
    project_id: PrefixedId
    email: str
    role: Literal["owner", "member", "viewer"]
    user_id: PrefixedId | None = None
    status: Literal["invited", "active"] = "invited"


class ProjectMemberListResponse(ApiModel):
    members: list[ProjectMemberResponse] = Field(default_factory=list)


class ProjectArchiveResponse(ApiModel):
    id: PrefixedId
    deleted_at: datetime


class SettingsResponse(ApiModel):
    """Settings read surface — same entitlements/flags as ``/v1/me`` + org."""

    user: UserResponse
    org: OrgResponse | None = None
    persona: str | None = None


class PublicSnapshotCreate(ApiModel):
    """Publish a redacted PLG share (never a live ProjectGoalDoc dump)."""

    include_goals: bool = True
    include_lever_stats: bool = True
    include_dead_end_lessons: bool = False


class PublicSnapshotResponse(ApiModel):
    slug: str
    org_slug: str
    project_slug: str
    share_path: str
    redacted: dict[str, Any]
    entropy: str


class EpisodeCard(ApiModel):
    """Contrastive episode card written on mission/lever close (Phase E)."""

    id: PrefixedId
    project_id: PrefixedId
    semantic_summary: str = ""
    epoch_id: str | None = None
    family: str | None = None
    verdict: str | None = None
    snr_weight: Annotated[float, Field(default=1.0, allow_inf_nan=False)] = 1.0
    utility_weight: Annotated[float, Field(default=1.0, allow_inf_nan=False)] = 1.0
    times_retrieved: int = 0
    times_cited: int = 0
    falsified_on_cv: bool = False
    attributed_cv_gains: Annotated[
        float, Field(default=0.0, allow_inf_nan=False)
    ] = 0.0


# Back-compat alias
EpisodeCardStub = EpisodeCard


class ProjectAxiom(ApiModel):
    """Sleep-cycle axiom pinned atop briefs (Phase E consolidate)."""

    id: PrefixedId
    project_id: PrefixedId
    statement: str = ""
    evidence_count: int = 0
    pinned: bool = False
    epoch_id: str | None = None


ProjectAxiomStub = ProjectAxiom


class LogOofRequest(ApiModel):
    """SDK payload for fold scores. Prediction bytes use the OOF presign route."""

    experiment_id: PrefixedId | None = None
    fold_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )
    params: dict[str, Any] = Field(default_factory=dict)


class LogOofResponse(ApiModel):
    status: Literal["accepted"] = "accepted"
    experiment_id: PrefixedId | None = None
    fold_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )
    message: str = "recorded"



# --- Phase C: research runs, OOF artifacts, BYOC runners -------------------


class ResearchRunMode(str, Enum):
    fold0_smoke = "fold0_smoke"
    full_cv = "full_cv"


class OofArtifactStatus(str, Enum):
    pending_upload = "pending_upload"
    ready = "ready"
    expired = "expired"


class RunnerKind(str, Enum):
    local = "local"
    runpod_pod = "runpod_pod"
    runpod_serverless = "runpod_serverless"
    aws_ec2 = "aws_ec2"


class CloudProviderName(str, Enum):
    runpod = "runpod"
    aws = "aws"


class CloudAccountStatus(str, Enum):
    connected = "connected"
    disconnected = "disconnected"
    error = "error"


class RunnerLifecycleStatus(str, Enum):
    provisioning = "provisioning"
    starting = "starting"
    online = "online"
    stopping = "stopping"
    stopped = "stopped"
    terminating = "terminating"
    terminated = "terminated"
    error = "error"


class CloudProviderAccountResponse(ApiModel):
    """Connected cloud account — never includes sealed API keys."""

    account_id: PrefixedId
    org_id: PrefixedId
    provider: CloudProviderName
    status: CloudAccountStatus = CloudAccountStatus.connected
    role_arn: str | None = None
    external_id: str | None = None
    region: str | None = None
    has_credentials: bool = False
    kek_version: int | None = None
    connected_at: datetime | None = None


class CloudConnectRunPodRequest(ApiModel):
    api_key: Annotated[str, Field(min_length=8, max_length=512)]


class CloudConnectAwsRequest(ApiModel):
    role_arn: Annotated[str, Field(min_length=20, max_length=256)]
    region: Annotated[str, Field(min_length=2, max_length=32)] = "us-east-1"


class CloudGpuOffer(ApiModel):
    provider: CloudProviderName
    gpu_type: str
    gpu_id: str
    stock: Annotated[int, Field(ge=0)] = 0
    cost_estimate_micros_hr: Annotated[int, Field(ge=0)]
    region: str = ""
    vram_gb: Annotated[int, Field(ge=0)] = 0
    spot_ok: bool = False


class CloudLaunchQuote(ApiModel):
    provider: CloudProviderName
    gpu_type: str
    cost_estimate_micros_hr: Annotated[int, Field(ge=0)]
    region: str = ""
    max_cloud_micros_day: Annotated[int, Field(ge=0)] = 0
    used_cloud_micros_today: Annotated[int, Field(ge=0)] = 0
    within_entitlement: bool = True


class CloudLaunchRequest(ApiModel):
    provider: CloudProviderName
    gpu_type: Annotated[str, Field(min_length=1, max_length=128)]
    cost_estimate_micros_hr: Annotated[int, Field(ge=0)]
    spot: bool = True


class RunnerResponse(ApiModel):
    """Unified runners row (local | RunPod | AWS)."""

    runner_id: PrefixedId
    org_id: PrefixedId
    kind: RunnerKind
    status: RunnerLifecycleStatus
    provider: CloudProviderName | None = None
    region: str = ""
    gpu_type: str = ""
    cost_estimate_micros_hr: Annotated[int, Field(ge=0)] = 0
    provider_instance_id: str | None = None
    idle_timeout_minutes: Annotated[int, Field(ge=1, le=24 * 60)] = 30
    last_heartbeat_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CloudRunnersResource(ApiModel):
    """``mymlfw://orgs/{id}/runners`` read-only MCP payload (no secrets)."""

    org_id: PrefixedId
    runners: list[RunnerResponse] = Field(default_factory=list)
    feature_flag: Literal["cloud_runners"] = "cloud_runners"
    cloud_runners_enabled: bool = False


class OofArtifactCreateRequest(ApiModel):
    """Create an OOF upload slot; response includes a pinned PUT presign."""

    experiment_id: PrefixedId
    run_id: PrefixedId | None = None
    filename: Annotated[str, Field(min_length=1, max_length=256)] = "oof.npz"
    content_length: Annotated[int, Field(gt=0, le=2_147_483_648)]
    content_sha256: Annotated[str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]
    split_hash: Annotated[str, Field(min_length=8, max_length=128)] | None = None


class OofArtifactPresignResponse(ApiModel):
    oof_id: PrefixedId
    status: Literal[OofArtifactStatus.pending_upload] = OofArtifactStatus.pending_upload
    upload_url: str
    object_key: str
    expires_at: datetime
    headers: dict[str, str] = Field(default_factory=dict)
    content_disposition: str = "attachment"


class OofArtifactConfirmRequest(ApiModel):
    """Client asks API to HEAD the object and promote pending → ready."""

    expected_etag: str | None = None


class OofArtifactResponse(ApiModel):
    oof_id: PrefixedId
    experiment_id: PrefixedId
    run_id: PrefixedId | None = None
    status: OofArtifactStatus
    object_key: str
    content_length: int
    content_sha256: str
    split_hash: str | None = None
    etag: str | None = None
    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None = None


class ResearchRunCreateRequest(ApiModel):
    notebook_id: PrefixedId | None = None
    goal_id: PrefixedId | None = None
    mode: ResearchRunMode = ResearchRunMode.fold0_smoke
    runner_id: PrefixedId | None = None
    hardware_fingerprint: Annotated[str, Field(min_length=0, max_length=512)] = ""


class ResearchRunResponse(ApiModel):
    run_id: PrefixedId
    mode: ResearchRunMode
    status: Literal["queued", "running", "succeeded", "failed"] = "queued"
    runner_id: PrefixedId | None = None
    hardware_fingerprint: str = ""
    created_at: datetime


class ErrorSliceItem(ApiModel):
    """Worst residual / hard-example slice after log_oof (MCP resource shape)."""

    slice_key: str
    label: str
    n_examples: Annotated[int, Field(ge=0)]
    mean_residual: Annotated[float, Field(allow_inf_nan=False)]
    example_ids: list[str] = Field(default_factory=list)


class ErrorSlicesResource(ApiModel):
    """Worst residual / hard-example slice after log_oof."""

    run_id: PrefixedId
    oof_id: PrefixedId | None = None
    slices: list[ErrorSliceItem] = Field(default_factory=list)
    generated_at: datetime | None = None
    status: Literal["empty", "ready"] = "empty"


class RunnerHeartbeatRequest(ApiModel):
    runner_id: PrefixedId
    kind: RunnerKind = RunnerKind.local
    capability_tags: list[str] = Field(default_factory=list)
    status: Literal["idle", "busy", "draining"] = "idle"
    # Present after register; hashed at rest — never logged.
    runner_token: str | None = None


class RunnerHeartbeatResponse(ApiModel):
    runner_id: PrefixedId
    accepted: bool = True
    server_time: datetime
    # One-time reveal on /runners/register only.
    runner_token: str | None = None


class JobClaimRequest(ApiModel):
    runner_id: PrefixedId
    capability_tags: list[str] = Field(default_factory=list)
    runner_token: str | None = None


class JobScopedCredentials(ApiModel):
    """Minted on claim: 2h job_token + path-scoped presigns. No Mongo/KEK."""

    job_id: PrefixedId
    job_token: str
    expires_at: datetime
    run_id: PrefixedId | None = None
    upload_presigns: list[dict[str, str]] = Field(default_factory=list)
    download_presigns: list[dict[str, str]] = Field(default_factory=list)
    sandbox_notes: list[str] = Field(default_factory=list)


class JobClaimResponse(ApiModel):
    claimed: bool
    credentials: JobScopedCredentials | None = None


class TrainStripEvent(ApiModel):
    """SSE kit train-strip payload hook (Motion = Active State while running)."""

    event: Literal["train_strip"] = "train_strip"
    run_id: PrefixedId
    mode: ResearchRunMode
    progress_pct: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)] = 0.0
    fold: int | None = None
    message: str = ""


# --- Phase C: nested-CV ensemble sandbox ------------------------------------


class EnsembleMode(str, Enum):
    linear = "linear"
    rank = "rank"
    logit = "logit"
    geometric = "geometric"
    auto = "auto"


class EnsembleCandidatePayload(ApiModel):
    """Inline OOF vector for sandbox optimize (float32 on the server)."""

    name: Annotated[str, Field(min_length=1, max_length=128)] = "model"
    oof_id: PrefixedId | None = None
    split_hash: Annotated[str, Field(min_length=8, max_length=128)] | None = None
    # Row-major predictions: length N (binary) or nested N×C.
    predictions: list[Any]


class EnsembleOptimizeRequest(ApiModel):
    """Optimize blend weights; prefer ``candidates`` inline until MinIO load lands."""

    oof_ids: list[PrefixedId] = Field(default_factory=list)
    mode: EnsembleMode = EnsembleMode.auto
    metric: Literal["auc", "log_loss", "mse"] = "auc"
    diversity_method: Literal["spearman", "pearson"] = "spearman"
    corr_threshold: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)] = 0.99
    polish: bool = True
    allow_subsample: bool = True
    labels: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(default_factory=list)
    folds: list[Annotated[int, Field(ge=0)]] = Field(default_factory=list)
    candidates: list[EnsembleCandidatePayload] = Field(default_factory=list)
    expected_split_hash: Annotated[str, Field(min_length=8, max_length=128)] | None = None


class EnsembleOptimizeResponse(ApiModel):
    status: Literal["ok", "plan", "error", "needs_worker_offload"] = "ok"
    mode: EnsembleMode | None = None
    requested_mode: EnsembleMode | None = None
    weights: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(default_factory=list)
    candidate_names: list[str] = Field(default_factory=list)
    candidate_oof_ids: list[PrefixedId | None] = Field(default_factory=list)
    nested_cv_score: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    oof_blend_score: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    fold_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(default_factory=list)
    fold_snr: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    p_value: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    verdict: str | None = None
    ascii_board: str | None = None
    diversity_method: Literal["spearman", "pearson"] | None = None
    metric: Literal["auc", "log_loss", "mse"] | None = None
    subsampled: bool = False
    offload_hint: str | None = None
    ncm: int | None = None
    oof_ids: list[PrefixedId] = Field(default_factory=list)
    error_code: str | None = None
    message: str | None = None
    suggested_fix: str | None = None
    plan: dict[str, Any] | None = None


class EnsemblePromoteRequest(ApiModel):
    parent_oof_ids: list[PrefixedId] = Field(min_length=2)
    weights: list[Annotated[float, Field(allow_inf_nan=False)]]
    mode: EnsembleMode = EnsembleMode.linear
    goal_id: PrefixedId | None = None
    parent_experiment_ids: list[PrefixedId] = Field(default_factory=list)
    nested_cv_score: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    fold_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(default_factory=list)


class EnsemblePromoteResponse(ApiModel):
    status: Literal["created", "draft"] = "created"
    experiment_id: PrefixedId
    strategy: Literal["ensemble_blend"] = "ensemble_blend"
    parent_oof_ids: list[PrefixedId]
    weights: list[Annotated[float, Field(allow_inf_nan=False)]]
    mode: EnsembleMode
    detail: str = ""
    experiment: dict[str, Any] = Field(default_factory=dict)


# --- Phase C: Night-Shift Autopilot -----------------------------------------


class AutopilotMode(str, Enum):
    grandmaster_sweep = "grandmaster_sweep"
    feature_evolution = "feature_evolution"
    paradigm_explorer = "paradigm_explorer"
    loss_and_postproc = "loss_and_postproc"


class AutopilotSessionStatus(str, Enum):
    running = "running"
    paused = "paused"
    halted = "halted"
    completed = "completed"


class AutopilotStartRequest(ApiModel):
    mode: AutopilotMode = AutopilotMode.grandmaster_sweep
    hours: Annotated[float, Field(gt=0, le=72, allow_inf_nan=False)] = 8.0
    max_probes: Annotated[int, Field(ge=1, le=10_000)] = 64
    max_gpu_hours: Annotated[float, Field(gt=0, le=168, allow_inf_nan=False)] = 8.0
    # Prefer micros; CLI may send dollars via max_llm_usd.
    max_llm_cost_micros: Annotated[int | None, Field(default=None, ge=0)] = None
    max_llm_usd: Annotated[float | None, Field(default=None, ge=0, allow_inf_nan=False)] = None
    baseline_cv: Annotated[float, Field(allow_inf_nan=False)] = 0.0


class AutopilotDriverTickRequest(ApiModel):
    """Headless driver step (local runner hook). Never auto-submits to Kaggle."""

    session_id: PrefixedId | None = None
    variable: Annotated[str, Field(min_length=1, max_length=256)] = "probe_mutation"
    smoke_ok: bool = True
    fold0_delta: Annotated[float, Field(allow_inf_nan=False)] = 0.001
    max_spearman_to_pool: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)] = 0.5
    cv_delta: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    integrity_ok: bool = True
    llm_cost_micros: Annotated[int, Field(ge=0)] = 0
    # Runner-attested ticks only; bare bearer cannot forge promote metrics.
    job_token: Annotated[str | None, Field(default=None, max_length=512)] = None


class AutopilotHaltRequest(ApiModel):
    session_id: PrefixedId | None = None
    reason: Annotated[str, Field(default="operator_halt", max_length=240)] = "operator_halt"


class AutopilotSessionResponse(ApiModel):
    status: str
    session: dict[str, Any] = Field(default_factory=dict)
    root_node: dict[str, Any] | None = None
    node_count: int | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    budget_remaining: bool | None = None
    active_execution_lock: dict[str, Any] | None = None
    feature_flag: Literal["night_shift"] = "night_shift"
    auto_kaggle_submit: Literal[False] = False
    ascii_board: str | None = None
    cta: list[str] = Field(default_factory=list)
    session_id: PrefixedId | None = None
    detail: str | None = None
    error_code: str | None = None
    message: str | None = None
    suggested_fix: str | None = None


class AutopilotDigestResponse(ApiModel):
    status: str
    session_id: PrefixedId
    ascii_board: str
    cta: list[str] = Field(default_factory=list)
    auto_kaggle_submit: Literal[False] = False
    feature_flag: Literal["night_shift"] = "night_shift"


class AutopilotDriverTickResponse(ApiModel):
    status: str
    session_id: PrefixedId | None = None
    parent_id: PrefixedId | None = None
    uct: dict[str, Any] | None = None
    child: dict[str, Any] | None = None
    halving: list[dict[str, Any]] = Field(default_factory=list)
    lever_verifier: dict[str, Any] | None = None
    local_runner_hook: bool = True
    auto_kaggle_submit: Literal[False] = False
    feature_flag: Literal["night_shift"] = "night_shift"
    notes: list[str] = Field(default_factory=list)
    reason: str | None = None
    ascii_board: str | None = None


# --- Phase D: provenance / credits / licenses --------------------------------


class CreditKind(str, Enum):
    hf_model = "hf_model"
    hf_dataset = "hf_dataset"
    kaggle_dataset = "kaggle_dataset"
    kaggle_model = "kaggle_model"
    kaggle_kernel = "kaggle_kernel"
    paper = "paper"
    code = "code"
    url = "url"
    other = "other"


class LicenseStatus(str, Enum):
    """Verdict stored on ``project_credits`` (``BLOCKED_*`` gates final artifacts)."""

    ok = "OK"
    attribution_required = "ATTRIBUTION_REQUIRED"
    unverified = "UNVERIFIED_LICENSE"
    blocked_copyleft = "BLOCKED_COPYLEFT"
    blocked_noncommercial = "BLOCKED_NONCOMMERCIAL"

    @property
    def is_blocked(self) -> bool:
        return self.value.startswith("BLOCKED_")


class ProjectLicensePolicy(ApiModel):
    """Per-project license policy: what the shipped artifacts are licensed as."""

    # SPDX id of the shipped code/submission tree, or ``Proprietary``.
    project_license: Annotated[str, Field(min_length=1, max_length=64)] = "Proprietary"
    # True when the Kaggle competition rules allow commercial use of submissions.
    kaggle_commercial_rule: bool = True
    # When False, UNVERIFIED_LICENSE credits on the final ensemble also block.
    allow_unverified: bool = True


class CreditAssetDoc(TenantDocument):
    """``project_credits`` document (``crd_`` ULID) for one external asset."""

    kind: CreditKind
    identifier: Annotated[str, Field(min_length=1, max_length=512)]
    identifier_key: Annotated[str, Field(min_length=1, max_length=560)]
    name: Annotated[str, Field(min_length=1, max_length=256)]
    source_url: str | None = None
    spdx_id: str | None = None
    license_raw: str | None = None
    license_status: LicenseStatus = LicenseStatus.unverified
    license_reason: str = ""
    attribution_required: bool = False
    attribution_text: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: Annotated[int | None, Field(default=None, ge=1900, le=2200)] = None
    doi: str | None = None
    arxiv_id: str | None = None
    used_in_final_ensemble: bool = False
    linked_oof_ids: list[PrefixedId] = Field(default_factory=list)
    linked_candidate_names: list[str] = Field(default_factory=list)
    harvest_source: Literal["agent", "ast", "cli"] = "agent"
    resolved_at: datetime | None = None


class CreditAssetResponse(ApiModel):
    """Tenant-free credit view for API / MCP / CLI payloads."""

    id: PrefixedId
    kind: CreditKind
    identifier: str
    name: str
    source_url: str | None = None
    spdx_id: str | None = None
    license_raw: str | None = None
    license_status: LicenseStatus = LicenseStatus.unverified
    license_reason: str = ""
    attribution_required: bool = False
    attribution_text: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    used_in_final_ensemble: bool = False
    linked_oof_ids: list[PrefixedId] = Field(default_factory=list)
    linked_candidate_names: list[str] = Field(default_factory=list)
    harvest_source: Literal["agent", "ast", "cli"] = "agent"


class RegisterExternalAssetRequest(ApiModel):
    """Agent-registered HF/Kaggle/paper/kernel asset (Idempotency-Key required)."""

    kind: CreditKind
    identifier: Annotated[str, Field(min_length=1, max_length=512)]
    name: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    source_url: str | None = None
    # Free-form license string (SPDX id, HF tag, or card text). Never trusted as SPDX.
    license: Annotated[str, Field(max_length=256)] | None = None
    authors: list[str] = Field(default_factory=list)
    year: Annotated[int | None, Field(default=None, ge=1900, le=2200)] = None
    doi: str | None = None
    arxiv_id: str | None = None
    attribution_text: str | None = None
    used_in_final_ensemble: bool = False
    linked_oof_ids: list[PrefixedId] = Field(default_factory=list)
    linked_candidate_names: list[str] = Field(default_factory=list)


class RegisterExternalAssetResponse(ApiModel):
    status: Literal["registered", "updated"] = "registered"
    credit: CreditAssetResponse
    outbox_enqueued: bool = False
    replayed: bool = False


class LicenseFinding(ApiModel):
    credit_id: PrefixedId
    identifier: str
    spdx_id: str | None = None
    license_status: LicenseStatus
    reason: str = ""
    used_in_final_ensemble: bool = False


class VerifyProjectLicensesResponse(ApiModel):
    status: Literal["ok", "warn", "blocked"] = "ok"
    project_id: PrefixedId
    policy: ProjectLicensePolicy = Field(default_factory=ProjectLicensePolicy)
    credit_count: int = 0
    # False when any used_in_final_ensemble credit is BLOCKED_* (gate for ship actions).
    can_ship: bool = True
    blocked: list[LicenseFinding] = Field(default_factory=list)
    unverified: list[LicenseFinding] = Field(default_factory=list)
    attribution_required: list[LicenseFinding] = Field(default_factory=list)
    ascii_board: str | None = None
