"""GroupKFold OOF, train-only transformers, and nested temperature."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize
from scipy.special import log_softmax
from sklearn.model_selection import GroupKFold

from mymlfw.errors import MymlfwError


class FoldLocalDecision:
    """A post-process output. It must not be passed back in as a feature matrix."""

    def __init__(self, values):
        self.values = np.asarray(values)
        self.is_feature = False


def fit_unsupervised(estimator, X, train_idx, val_idx, *, on: str = "train"):
    """Fit a feature transformer on the train side of a fold and transform the val side."""
    if on != "train":
        raise MymlfwError(
            "VAL_FOLD_FIT",
            "Fit feature transformers on X_train_fold, then transform X_val_fold.",
        )
    if isinstance(X, FoldLocalDecision):
        raise MymlfwError(
            "DECISION_AS_FEATURE",
            "Fold-local Sinkhorn or cluster-cap outputs are decisions, not features.",
        )
    train_idx = np.asarray(train_idx)
    val_idx = np.asarray(val_idx)
    if set(train_idx.tolist()) & set(val_idx.tolist()):
        raise MymlfwError("FOLD_OVERLAP", "Train and val indices of a fold must be disjoint.")
    estimator.fit(X[train_idx])
    return estimator.transform(X[val_idx])


def fit_temperature(logits, y) -> float:
    logits = np.asarray(logits, dtype=float)
    y = np.asarray(y)

    def nll(log_t):
        temperature = float(np.exp(log_t[0]))
        logp = log_softmax(logits / temperature, axis=-1)
        return -float(np.mean(logp[np.arange(len(y)), y]))

    result = minimize(nll, np.zeros(1), method="L-BFGS-B")
    return float(np.exp(result.x[0]))


def nested_temperature(logits, y, folds, *, same_fold: bool = False, frozen: bool = False) -> dict:
    """Fit T for fold k on the other OOF folds. Selection scores stay uncalibrated."""
    if same_fold:
        raise MymlfwError(
            "SAME_FOLD_TEMPERATURE",
            "Fit T on the other OOF folds, then apply it to the held-out fold.",
        )
    logits = np.asarray(logits, dtype=float)
    y = np.asarray(y)
    calibrated = np.zeros_like(logits)
    temperatures = []
    for index, val_idx in enumerate(folds):
        val_idx = np.asarray(val_idx)
        others = [np.asarray(fold) for fold_i, fold in enumerate(folds) if fold_i != index]
        other_idx = np.concatenate(others) if others else val_idx
        if len(others) == 0:
            raise MymlfwError(
                "SAME_FOLD_TEMPERATURE",
                "Nested temperature needs at least one other fold to fit T.",
            )
        temperature = fit_temperature(logits[other_idx], y[other_idx])
        temperatures.append(temperature)
        calibrated[val_idx] = logits[val_idx] / temperature
    global_t = fit_temperature(logits, y) if frozen else None
    return {
        "selection_logits": logits.copy(),
        "calibrated": calibrated,
        "temperatures": temperatures,
        "global_t": global_t,
    }


@dataclass
class OOFResult:
    status: str
    fold0_score: float
    n_folds_fit: int
    oof: np.ndarray | None = None
    fold_scores: list = field(default_factory=list)


def run_oof(
    X,
    y,
    groups,
    fit_predict,
    *,
    n_splits: int = 5,
    metric,
    fold0_only: bool = False,
    baseline_fold0: float | None = None,
    min_delta: float = 0.0,
) -> OOFResult:
    """GroupKFold driver. Fold 0 is the first split and is deterministic for these groups."""
    X = np.asarray(X)
    y = np.asarray(y)
    groups = np.asarray(groups)
    splits = list(GroupKFold(n_splits=n_splits).split(X, y, groups))
    oof = np.full(len(y), np.nan, dtype=float)
    fold_scores = []
    fitted = 0
    for fold_id, (train_idx, val_idx) in enumerate(splits):
        pred = np.asarray(fit_predict(train_idx, val_idx), dtype=float)
        oof[val_idx] = pred
        score = float(metric(y[val_idx], pred))
        fold_scores.append(score)
        fitted += 1
        if fold_id == 0 and fold0_only:
            if baseline_fold0 is None:
                raise MymlfwError(
                    "MISSING_FOLD0_BASELINE",
                    "Pass baseline_fold0 when fold0_only is set.",
                )
            if score - float(baseline_fold0) <= float(min_delta):
                return OOFResult("fold0_reject", score, fitted, oof=oof, fold_scores=fold_scores)
    status = "complete"
    return OOFResult(status, fold_scores[0], fitted, oof=oof, fold_scores=fold_scores)
