"""Render launch scripts. This module never calls a cloud API."""

from __future__ import annotations

import os
from dataclasses import dataclass

from mymlfw.campaign.ledger import register_probe
from mymlfw.errors import MymlfwError


@dataclass
class JobSpec:
    project: str
    role: str
    gpu: str
    command: str
    idle_kill_minutes: int
    max_runtime_minutes: int
    experiment_id: str
    baseline_id: str
    variable: str
    expected_band_low: float
    expected_band_high: float
    note: str = ""

    def __post_init__(self):
        if self.role not in {"primary", "fleet"}:
            raise MymlfwError("BAD_ROLE", "role must be primary or fleet.", role=self.role)
        if int(self.idle_kill_minutes) <= 0 or int(self.max_runtime_minutes) <= 0:
            raise MymlfwError("BAD_RUNTIME", "Time limits must be positive.")
        if int(self.max_runtime_minutes) < int(self.idle_kill_minutes):
            raise MymlfwError(
                "BAD_RUNTIME",
                "max_runtime_minutes must be at least idle_kill_minutes.",
            )


def require_approval(env=None) -> str:
    env = os.environ if env is None else env
    token = env.get("CLOUD_APPROVAL", "")
    if not token:
        raise MymlfwError(
            "CLOUD_APPROVAL_MISSING",
            "Set CLOUD_APPROVAL before rendering a launch command.",
        )
    return token


def _one_line(value: str, field: str) -> str:
    text = str(value)
    if "\n" in text or "\r" in text or "\x00" in text:
        raise MymlfwError(
            "BAD_SHELL_FIELD",
            "Keep project, gpu, role, and command on one line.",
            field=field,
        )
    return text


def render_launch(spec: JobSpec, ledger, env=None) -> str:
    require_approval(env)
    project = _one_line(spec.project, "project")
    role = _one_line(spec.role, "role")
    gpu = _one_line(spec.gpu, "gpu")
    command = _one_line(spec.command, "command")
    register_probe(
        ledger,
        experiment_id=spec.experiment_id,
        baseline_id=spec.baseline_id,
        variable=spec.variable,
        change_count=1,
        expected_band_low=spec.expected_band_low,
        expected_band_high=spec.expected_band_high,
        note=spec.note,
    )
    return (
        "#!/bin/sh\n"
        f"# project={project}\n"
        "# env=kaggle\n"
        f"# role={role}\n"
        f"# gpu={gpu}\n"
        f"shutdown -h +{int(spec.max_runtime_minutes)}\n"
        f"{command}\n"
    )
