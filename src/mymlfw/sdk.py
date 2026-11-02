"""Thin notebook SDK helpers (Phase B stubs).

``log_oof`` reads ``MYMLFW_PROJECT`` / ``MYMLFW_EXPERIMENT`` from the
environment. Real MinIO upload + dashboard SSE land in Phase C.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

from mymlfw.saas.schemas import LogOofResponse


def log_oof(
    oof_df: Any = None,
    *,
    fold_scores: Sequence[float] | None = None,
    params: Mapping[str, Any] | None = None,
    experiment_id: str | None = None,
    project_id: str | None = None,
) -> LogOofResponse:
    """Stub: validate env + fold_scores; defer artifact upload to Phase C.

    Parameters
    ----------
    oof_df:
        Placeholder for a DataFrame / array of OOF predictions (unused in stub).
    fold_scores:
        Per-fold metric values (finite floats required by callers upstream).
    params:
        Free-form run params recorded later with the experiment.
    """
    _ = oof_df
    project = project_id or os.environ.get("MYMLFW_PROJECT")
    experiment = experiment_id or os.environ.get("MYMLFW_EXPERIMENT")
    scores = [float(s) for s in (fold_scores or ())]
    for s in scores:
        if s != s or s in (float("inf"), float("-inf")):
            raise ValueError("fold_scores must be finite")
    _ = (project, params)
    return LogOofResponse(
        status="stub",
        experiment_id=experiment,
        fold_scores=scores,
        message=(
            "log_oof stub — set MYMLFW_PROJECT / MYMLFW_EXPERIMENT; "
            "MinIO OOF upload + SSE land in Phase C"
        ),
    )
