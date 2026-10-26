"""Redundancy check before a branch spends inference quota."""

from __future__ import annotations

import numpy as np

from mymlfw.blend.bundle import as_log_probs
from mymlfw.errors import MymlfwError


def _pair_correlation(left: np.ndarray, right: np.ndarray) -> float:
    if np.allclose(left, right):
        return 1.0
    if float(np.std(left)) < 1e-12 or float(np.std(right)) < 1e-12:
        return float("nan")
    return float(np.corrcoef(left, right)[0, 1])


def diversity_matrix(bundles, standalone_cv, strict: bool = False) -> dict:
    vectors = [as_log_probs(bundle).ravel() for bundle in bundles]
    corr = np.eye(len(bundles))
    for i in range(len(bundles)):
        for j in range(i):
            value = _pair_correlation(vectors[i], vectors[j])
            corr[i, j] = corr[j, i] = value
    reference = np.exp(as_log_probs(bundles[0]))
    confidence = reference.max(axis=1)
    cutoff = np.quantile(confidence, 0.25)
    hard = confidence <= cutoff
    warnings = []
    for i in range(len(bundles)):
        for j in range(i):
            correlation = float(corr[i, j])
            if not np.isfinite(correlation):
                if np.allclose(vectors[i], vectors[j]):
                    correlation = 1.0
                else:
                    continue
            worse = float(standalone_cv[i]) < float(standalone_cv[j])
            if correlation > 0.995 and worse:
                pred_i = as_log_probs(bundles[i]).argmax(axis=1)
                pred_j = as_log_probs(bundles[j]).argmax(axis=1)
                disagree = float(np.mean(pred_i[hard] != pred_j[hard])) if np.any(hard) else 0.0
                warnings.append(
                    {
                        "error_code": "HIGH_REDUNDANCY",
                        "branch": bundles[i].name,
                        "other": bundles[j].name,
                        "correlation": correlation,
                        "hard_disagreement": disagree,
                    }
                )
    if strict and warnings:
        raise MymlfwError(
            "HIGH_REDUNDANCY",
            "Drop the redundant branch and save the inference quota.",
            **warnings[0],
        )
    return {"correlation": corr, "warnings": warnings}
