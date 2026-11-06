"""Prefixed ULID helpers for Campaign SaaS documents."""

from __future__ import annotations

from ulid import ULID

from mymlfw.saas.schemas import ULID_PREFIXES


def new_prefixed_id(kind: str) -> str:
    """Return ``{prefix}{ULID}`` for a known document kind."""
    prefix = ULID_PREFIXES.get(kind)
    if prefix is None:
        raise ValueError(f"unknown_id_kind:{kind}")
    return f"{prefix}{ULID()}"


def new_goal_id() -> str:
    return new_prefixed_id("gol")


def new_experiment_id() -> str:
    return new_prefixed_id("exp")


def new_project_id() -> str:
    return new_prefixed_id("prj")


def new_dead_end_id() -> str:
    return new_prefixed_id("ded")


def new_mission_id() -> str:
    return new_prefixed_id("msn")


def new_snapshot_id() -> str:
    return f"pub_{ULID()}"


def new_oof_id() -> str:
    return new_prefixed_id("oof")


def new_run_id() -> str:
    return new_prefixed_id("run")


def new_runner_id() -> str:
    return new_prefixed_id("rnr")


def new_job_id() -> str:
    return new_prefixed_id("job")


def new_job_token_id() -> str:
    return new_prefixed_id("jtk")


def new_cloud_account_id() -> str:
    return new_prefixed_id("cpa")


def new_autopilot_session_id() -> str:
    return new_prefixed_id("aps")


def new_autopilot_node_id() -> str:
    return new_prefixed_id("nd")


def new_episode_card_id() -> str:
    return new_prefixed_id("epc")


def new_axiom_id() -> str:
    return new_prefixed_id("axm")


def new_memory_id() -> str:
    return new_prefixed_id("mem")


def new_credit_id() -> str:
    return new_prefixed_id("crd")


def new_progress_id() -> str:
    return new_prefixed_id("prg")


def new_source_id() -> str:
    return new_prefixed_id("src")


def new_roadmap_strategy_id() -> str:
    return new_prefixed_id("rds")


def new_gap_id() -> str:
    return new_prefixed_id("gap")
