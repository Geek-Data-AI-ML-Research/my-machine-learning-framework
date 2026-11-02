"""Fold win-ratio and SNR badge helpers for dashboard / lever tables."""

from __future__ import annotations

import math
from typing import Sequence

from mymlfw.saas.schemas import FoldSnrBadge, FoldSnrLabel


def fold_win_ratio(fold_scores: Sequence[float], *, baseline: float | None = None) -> float:
    """Fraction of folds beating ``baseline`` (default: mean of other folds' mean)."""
    scores = [float(s) for s in fold_scores]
    if not scores:
        return 0.0
    if baseline is None:
        mean = sum(scores) / len(scores)
        baseline = mean
    wins = sum(1 for s in scores if s >= baseline)
    return wins / len(scores)


def paired_snr(fold_deltas: Sequence[float]) -> float:
    """Mean / std of per-fold deltas; 0 when variance is zero or empty."""
    vals = [float(d) for d in fold_deltas]
    n = len(vals)
    if n == 0:
        return 0.0
    mean = sum(vals) / n
    if n == 1:
        return float("inf") if mean != 0 else 0.0
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    std = math.sqrt(var)
    if std == 0:
        return float("inf") if mean != 0 else 0.0
    return mean / std


def classify_snr(snr: float, *, solid_threshold: float = 1.0) -> FoldSnrLabel:
    if snr != snr or snr in (float("inf"), float("-inf")):  # NaN guard; inf → solid if positive
        if snr == float("inf") or (isinstance(snr, float) and snr > solid_threshold):
            return FoldSnrLabel.solid
        return FoldSnrLabel.noise
    if snr >= solid_threshold:
        return FoldSnrLabel.solid
    return FoldSnrLabel.noise


def fold_snr_badge(
    fold_scores: Sequence[float],
    *,
    baseline_scores: Sequence[float] | None = None,
    solid_threshold: float = 1.0,
) -> FoldSnrBadge:
    """Build ``5/5 FOLDS | SOLID`` style badge from fold scores.

    When ``baseline_scores`` is provided (same length), deltas are paired.
    Otherwise each fold is compared to the mean of all folds.
    """
    scores = [float(s) for s in fold_scores]
    n = len(scores)
    if n == 0:
        return FoldSnrBadge(
            wins=0,
            n_folds=0,
            win_ratio=0.0,
            snr=0.0,
            label=FoldSnrLabel.noise,
            display="0/0 FOLDS | NOISE",
        )

    if baseline_scores is not None and len(baseline_scores) == n:
        deltas = [s - float(b) for s, b in zip(scores, baseline_scores)]
        wins = sum(1 for d in deltas if d > 0)
        snr = paired_snr(deltas)
    else:
        mean = sum(scores) / n
        wins = sum(1 for s in scores if s >= mean)
        deltas = [s - mean for s in scores]
        snr = paired_snr(deltas)

    # Clamp ±inf for JSON-safe API payloads; label still reflects solid/noise.
    if snr == float("inf"):
        snr_out = 1e6
    elif snr == float("-inf"):
        snr_out = -1e6
    else:
        snr_out = float(snr)
    label = classify_snr(snr_out, solid_threshold=solid_threshold)
    display = f"{wins}/{n} FOLDS | {label.value}"
    return FoldSnrBadge(
        wins=wins,
        n_folds=n,
        win_ratio=wins / n,
        snr=snr_out,
        label=label,
        display=display,
    )


def adv_auc_label(adv_auc: float | None) -> str:
    """SAFE ~0.5 vs TIME/DOMAIN SHIFT when adversarial AUC is high."""
    if adv_auc is None:
        return "UNKNOWN"
    if abs(adv_auc - 0.5) <= 0.08:
        return "SAFE"
    return "TIME/DOMAIN SHIFT"
