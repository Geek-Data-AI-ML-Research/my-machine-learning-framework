"""Metrics that keep a stable class set and reject duplicate rankings."""

from __future__ import annotations

import numpy as np

from mymlfw.errors import DuplicateCandidateError, MymlfwError


def balanced_accuracy(y_true, y_pred, classes) -> float:
    """Macro recall over ``classes``. A missing class contributes 0 and does not warn."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    recalls = []
    for label in classes:
        mask = y_true == label
        if not np.any(mask):
            recalls.append(0.0)
            continue
        recalls.append(float(np.mean(y_pred[mask] == label)))
    return float(np.mean(recalls)) if recalls else 0.0


def mrr_at_k(ranked, truth, k: int | None = None) -> float:
    """Mean reciprocal rank. ``ranked`` is one list, or a list of lists."""
    if ranked and isinstance(ranked[0], (list, tuple)):
        truth_list = list(truth)
        if len(ranked) != len(truth_list):
            raise MymlfwError(
                "MRR_LENGTH",
                "Pass one truth label for each ranked list.",
                ranked=len(ranked),
                truths=len(truth_list),
            )
        scores = [mrr_at_k(row, gold, k=k) for row, gold in zip(ranked, truth_list)]
        return float(np.mean(scores)) if scores else 0.0
    if len(ranked) != len(set(ranked)):
        raise DuplicateCandidateError(ranked=list(ranked))
    limit = list(ranked if k is None else ranked[:k])
    for index, candidate in enumerate(limit, start=1):
        if candidate == truth:
            return 1.0 / index
    return 0.0
