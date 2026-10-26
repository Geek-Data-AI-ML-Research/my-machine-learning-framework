"""Simplex weight search with a pull toward equal weights."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from mymlfw.blend.bundle import as_log_probs
from mymlfw.blend.pool import blend
from mymlfw.errors import MymlfwError


def score_bundle(y_true, bundle, metric: str = "log_loss") -> float:
    """Higher is better. ``log_loss`` returns the mean log probability of the label."""
    y_true = np.asarray(y_true)
    if len(y_true) != len(bundle.ids):
        raise MymlfwError(
            "SHAPE",
            "Labels and prediction rows differ.",
            rows=int(len(bundle.ids)),
            labels=int(len(y_true)),
        )
    if metric not in {"log_loss", "accuracy", "balanced_accuracy"}:
        raise MymlfwError("BAD_METRIC", "Use log_loss, accuracy, or balanced_accuracy.", metric=metric)
    logp = as_log_probs(bundle)
    classes = [str(label) for label in bundle.classes.tolist()]
    index = {label: i for i, label in enumerate(classes)}
    labels = [str(value) for value in y_true.tolist()]
    missing = sorted({label for label in labels if label not in index})
    if missing:
        raise MymlfwError("BAD_LABEL", "Every label must belong to the bundle classes.", missing=missing)
    gold = np.array([index[label] for label in labels])
    if metric == "log_loss":
        return float(np.mean(logp[np.arange(len(gold)), gold]))
    pred_idx = logp.argmax(axis=1)
    if metric == "accuracy":
        return float(np.mean(pred_idx == gold))
    from mymlfw.metrics import balanced_accuracy

    pred = np.asarray(classes, dtype=object)[pred_idx]
    return balanced_accuracy(np.asarray(labels, dtype=object), pred, classes)


def _softmax(raw: np.ndarray) -> np.ndarray:
    shifted = raw - np.max(raw)
    exp = np.exp(shifted)
    return exp / exp.sum()


def optimize_weights(bundles, y_true, metric, method: str = "dirichlet_lbfgs", l2: float = 0.05) -> np.ndarray:
    if method != "dirichlet_lbfgs":
        raise ValueError(f"unsupported method {method}")
    y_true = np.asarray(y_true)
    n_members = len(bundles)

    def objective(raw):
        weights = _softmax(np.asarray(raw, dtype=float))
        blended = blend(bundles, weights, pool="log_linear")
        score = float(metric(y_true, blended))
        penalty = float(l2) * float(np.sum((weights - (1.0 / n_members)) ** 2))
        return -(score - penalty)

    result = minimize(objective, np.zeros(n_members), method="L-BFGS-B")
    return _softmax(result.x)
