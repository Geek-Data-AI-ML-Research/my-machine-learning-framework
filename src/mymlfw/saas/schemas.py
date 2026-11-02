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
    """Reserved until Phase E — B2 returns not-ready."""

    project_id: PrefixedId
    scope: Literal["dead_ends", "episodes", "kaggle_intel", "all"] = "all"
    max_tokens: Annotated[int, Field(ge=64, le=8192)] = 512
    detail_level: Literal["summary", "full"] = "summary"


class QueryProjectBrainResponse(ApiModel):
    status: Literal["not_ready"] = "not_ready"
    message: str = "query_project_brain lands in Phase E"
    results: list[dict[str, Any]] = Field(default_factory=list)


class PatCreateResponse(ApiModel):
    """Plaintext token shown once; only hash + prefix are retained."""

    token_id: PrefixedId
    token_prefix: str
    token: str
    workspace_id: PrefixedId
    project_id: PrefixedId | None = None
    scopes: list[str] = Field(default_factory=lambda: ["mcp:worker"])


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
    artifact_key: str | None = None  # MinIO key stub for folds.parquet


class ProjectGoalCreate(ApiModel):
    title: Annotated[str, Field(min_length=1, max_length=240)]
    kind: GoalKind = GoalKind.notebook_score
    metric_key: Annotated[str, Field(min_length=1, max_length=64)] = "cv_mean"
    threshold: Annotated[float, Field(allow_inf_nan=False)]
    direction: GoalDirection = GoalDirection.maximize
    constraints: list[str] = Field(default_factory=list)
    priority: int = 100
    notes: str = ""


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
    primary_status: Literal["MET", "MISSED", "OPEN"] = "OPEN"
    progress_pct: Annotated[float, Field(allow_inf_nan=False)]
    goals_met_ratio: Annotated[float, Field(allow_inf_nan=False)]
    lever_close_rate: Annotated[float, Field(allow_inf_nan=False)]
    mission_success_rate: Annotated[float, Field(allow_inf_nan=False)]
    folds_sha256: str | None = None
    adv_auc: Annotated[float | None, Field(default=None, allow_inf_nan=False)] = None
    adv_auc_label: str = "UNKNOWN"


class DashboardGoalsPanel(ApiModel):
    active: int = 0
    met: int = 0
    abandoned: int = 0
    count: int = 0


class DashboardLeversPanel(ApiModel):
    open: int = 0
    closed: int = 0
    kills: int = 0
    promotes: int = 0
    fold_badges: list[FoldSnrBadge] = Field(default_factory=list)
    sparkline: list[dict[str, Any]] = Field(default_factory=list)


class DashboardMissionsPanel(ApiModel):
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0


class DashboardDeadEndsPanel(ApiModel):
    count: int = 0
    top_variables: list[str] = Field(default_factory=list)


class DashboardResponse(ApiModel):
    project_id: PrefixedId
    header: DashboardHeader
    goals: DashboardGoalsPanel
    levers: DashboardLeversPanel
    missions: DashboardMissionsPanel
    dead_ends: DashboardDeadEndsPanel


class ProjectSummary(ApiModel):
    id: PrefixedId
    slug: str
    name: str
    kind: ProjectKind
    is_demo: bool = False
    folds: FoldMeta = Field(default_factory=FoldMeta)
    public_share_slug: str | None = None


class ProjectListResponse(ApiModel):
    projects: list[ProjectSummary]


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


class EpisodeCardStub(ApiModel):
    """Schema stub for contrastive episode cards (RAG empty until Phase E)."""

    id: PrefixedId
    project_id: PrefixedId
    semantic_summary: str = ""
    epoch_id: str | None = None
    snr_weight: Annotated[float, Field(default=1.0, allow_inf_nan=False)] = 1.0
    utility_weight: Annotated[float, Field(default=1.0, allow_inf_nan=False)] = 1.0
    times_retrieved: int = 0
    times_cited: int = 0
    falsified_on_cv: bool = False
    attributed_cv_gains: Annotated[
        float, Field(default=0.0, allow_inf_nan=False)
    ] = 0.0


class ProjectAxiomStub(ApiModel):
    """Schema stub for sleep-cycle axioms (pinned in briefs; empty until E)."""

    id: PrefixedId
    project_id: PrefixedId
    statement: str = ""
    evidence_count: int = 0
    pinned: bool = False
    epoch_id: str | None = None


class LogOofRequest(ApiModel):
    """Thin SDK payload; real MinIO upload lands in Phase C."""

    experiment_id: PrefixedId | None = None
    fold_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )
    params: dict[str, Any] = Field(default_factory=dict)


class LogOofResponse(ApiModel):
    status: Literal["stub", "accepted"] = "stub"
    experiment_id: PrefixedId | None = None
    fold_scores: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=list
    )
    message: str = "log_oof stub — MinIO OOF upload lands in Phase C"



# --- Phase C: research / OOF / BYOC stubs ---------------------------------


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
    """``mymlfw://projects/{id}/runs/{run_id}/error_slices`` stub payload."""

    run_id: PrefixedId
    oof_id: PrefixedId | None = None
    slices: list[ErrorSliceItem] = Field(default_factory=list)
    generated_at: datetime | None = None
    status: Literal["empty", "ready", "not_ready"] = "not_ready"


class RunnerHeartbeatRequest(ApiModel):
    runner_id: PrefixedId
    kind: RunnerKind = RunnerKind.local
    capability_tags: list[str] = Field(default_factory=list)
    status: Literal["idle", "busy", "draining"] = "idle"


class RunnerHeartbeatResponse(ApiModel):
    runner_id: PrefixedId
    accepted: bool = True
    server_time: datetime


class JobClaimRequest(ApiModel):
    runner_id: PrefixedId
    capability_tags: list[str] = Field(default_factory=list)


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
    status: Literal["stub", "created"] = "stub"
    experiment_id: PrefixedId
    strategy: Literal["ensemble_blend"] = "ensemble_blend"
    parent_oof_ids: list[PrefixedId]
    weights: list[Annotated[float, Field(allow_inf_nan=False)]]
    mode: EnsembleMode
    detail: str = ""
    experiment: dict[str, Any] = Field(default_factory=dict)
