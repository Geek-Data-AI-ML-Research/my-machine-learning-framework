"""Notebook SDK: ``log_oof`` records fold scores through the Campaign API.

Set ``MYMLFW_API``, ``MYMLFW_TOKEN``, ``MYMLFW_PROJECT``, and
``MYMLFW_EXPERIMENT``. There is no local success path that skips the API.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
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
    """POST fold scores to ``/v1/projects/{id}/log-oof``.

    ``oof_df`` is accepted for call-site compatibility. Prediction bytes go
    through the presigned OOF artifact API, not this helper.
    """
    _ = oof_df
    project = project_id or os.environ.get("MYMLFW_PROJECT")
    experiment = experiment_id or os.environ.get("MYMLFW_EXPERIMENT")
    scores = [float(s) for s in (fold_scores or ())]
    for score in scores:
        if score != score or score in (float("inf"), float("-inf")):
            raise ValueError("fold_scores must be finite")
    if not project:
        raise ValueError("MYMLFW_PROJECT is required")
    api = os.environ.get("MYMLFW_API", "").rstrip("/")
    token = os.environ.get("MYMLFW_TOKEN", "")
    if not api or not token:
        raise ValueError("MYMLFW_API and MYMLFW_TOKEN are required to record OOF scores")
    body = json.dumps(
        {
            "experiment_id": experiment,
            "fold_scores": scores,
            "params": dict(params or {}),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{api}/v1/projects/{project}/log-oof",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"log-oof-{project}-{experiment or 'none'}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        note = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"log_oof_http_{exc.code}:{note}") from exc
    return LogOofResponse(
        status="accepted",
        experiment_id=payload.get("experiment_id") or experiment,
        fold_scores=scores,
        message=str(payload.get("message") or "recorded"),
    )
