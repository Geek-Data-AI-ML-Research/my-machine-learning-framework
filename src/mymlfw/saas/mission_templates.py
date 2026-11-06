"""Render mission CLI from template_id + typed args (shlex.quote)."""

from __future__ import annotations

import shlex
from typing import Any

_TEMPLATES = {
    "fold0_smoke": "python -m mymlfw research run --mode fold0_smoke --project {project_id}",
    "full_cv": "python -m mymlfw research run --mode full_cv --project {project_id}",
    "pytest": "pytest -q",
}


def render_cli_steps(*, template_id: str, args: dict[str, Any]) -> list[str]:
    if template_id not in _TEMPLATES:
        raise ValueError(f"unknown_template:{template_id}")
    if any(isinstance(v, str) and ("\n" in v or ";" in v) for v in args.values()):
        raise ValueError("raw_shell_rejected")
    pattern = _TEMPLATES[template_id]
    quoted = {k: shlex.quote(str(v)) for k, v in args.items()}
    try:
        line = pattern.format(**quoted) if "{" in pattern else pattern
    except KeyError as exc:
        raise ValueError(f"missing_arg:{exc}") from exc
    return [line]
