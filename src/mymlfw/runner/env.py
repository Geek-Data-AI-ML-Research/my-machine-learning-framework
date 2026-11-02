"""Runner process environment contract.

Runner must never receive Mongo URI, KEK material, or upstream provider API
keys — only a runner token + API base URL + job-scoped presigns.
"""

from __future__ import annotations

import os
from typing import Mapping

FORBIDDEN_ENV_KEYS: frozenset[str] = frozenset(
    {
        "MYMLFW_MONGO_URI",
        "MONGO_URI",
        "MONGODB_URI",
        "MYMLFW_KEK",
        "MYMLFW_KEK_MATERIAL",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID",
        "RUNPOD_API_KEY",
        "MINIO_ROOT_PASSWORD",
    }
)

REQUIRED_HINTS: frozenset[str] = frozenset(
    {
        "MYMLFW_API_URL",
        "MYMLFW_RUNNER_TOKEN",
    }
)


class RunnerEnvError(ValueError):
    """Raised when the runner env violates the BYOC contract."""


def validate_runner_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a sanitized view; raise if forbidden secrets are present."""
    source = os.environ if env is None else env
    present_forbidden = sorted(k for k in FORBIDDEN_ENV_KEYS if source.get(k))
    if present_forbidden:
        raise RunnerEnvError(
            "runner_env_forbidden_keys:" + ",".join(present_forbidden)
        )
    return {
        "MYMLFW_API_URL": source.get("MYMLFW_API_URL", ""),
        "MYMLFW_RUNNER_TOKEN": source.get("MYMLFW_RUNNER_TOKEN", ""),
        "MYMLFW_RUNNER_ID": source.get("MYMLFW_RUNNER_ID", ""),
    }
