"""Ensemble sandbox stub — nested-CV hill-climb lands in ``pc-ensemble``.

Control plane: NumPy/SciPy only (no torch). Hook surface kept so OOF
``ready`` artifacts can be referenced without implementing blend math yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


EnsembleMode = Literal["linear", "rank", "logit", "geometric", "auto"]


@dataclass(frozen=True)
class EnsembleHook:
    """Placeholder for promote_blend / nested CV — intentionally unimplemented."""

    status: Literal["not_implemented"] = "not_implemented"
    detail: str = "pc-ensemble: nested-CV Caruana+SLSQP not started"


def plan_ensemble(
    oof_ids: list[str],
    *,
    mode: EnsembleMode = "auto",
) -> dict[str, Any]:
    """Return a stub plan; does not load OOF matrices or run nested CV."""
    _ = mode
    return {
        "status": "not_implemented",
        "oof_ids": list(oof_ids),
        "hook": EnsembleHook().detail,
        "suggested_fix": "Wait for pc-ensemble; use ready oof_artifacts only.",
    }


def promote_blend_to_experiment_stub(*_args: Any, **_kwargs: Any) -> None:
    raise NotImplementedError("promote_blend_to_experiment lands in pc-ensemble")
