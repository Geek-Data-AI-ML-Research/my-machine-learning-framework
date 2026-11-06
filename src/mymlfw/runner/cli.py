"""``mymlfw runner start|status`` CLI helpers."""

from __future__ import annotations

import json
import time
from typing import Any

from mymlfw.errors import MymlfwError
from mymlfw.runner.client import RunnerClient
from mymlfw.runner.env import RunnerEnvError, validate_runner_env


def runner_status(*, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        validate_runner_env(env)
    except RunnerEnvError as exc:
        raise MymlfwError(
            "RUNNER_ENV_FORBIDDEN",
            "Unset forbidden keys; set MYMLFW_API_URL + MYMLFW_RUNNER_TOKEN only.",
            note=str(exc),
        ) from exc
    client = RunnerClient.from_env(env)
    return client.status()


def runner_start(
    *,
    once: bool = False,
    poll_seconds: float = 5.0,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Heartbeat until interrupted. ``once`` returns after a single claim."""
    try:
        validate_runner_env(env)
    except RunnerEnvError as exc:
        raise MymlfwError(
            "RUNNER_ENV_FORBIDDEN",
            "Unset forbidden keys; set MYMLFW_API_URL + MYMLFW_RUNNER_TOKEN only.",
            note=str(exc),
        ) from exc
    client = RunnerClient.from_env(env)
    hb = client.heartbeat(status="idle")
    claim = client.claim_job()
    result = {
        "runner_id": client.runner_id,
        "heartbeat": hb.model_dump(mode="json"),
        "claim": claim.model_dump(mode="json"),
        "mode": "once" if once else "loop",
    }
    if once:
        return result
    while True:
        time.sleep(poll_seconds)
        client.heartbeat(status="idle")
        client.claim_job()


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))
