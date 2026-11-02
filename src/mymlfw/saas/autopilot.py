"""Night-Shift Autopilot stub — UCT + successive halving lands in ``pc-autopilot``.

Behind feature flag ``night_shift``. Never auto-submits to Kaggle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class AutopilotHook:
    status: Literal["not_implemented"] = "not_implemented"
    detail: str = "pc-autopilot: UCT+halving + headless driver not started"
    feature_flag: str = "night_shift"


def start_autopilot_stub(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    hook = AutopilotHook()
    return {
        "status": hook.status,
        "detail": hook.detail,
        "feature_flag": hook.feature_flag,
        "suggested_fix": "Enable night_shift after pc-autopilot ships.",
    }
