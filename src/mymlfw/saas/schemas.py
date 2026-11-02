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
