"""Shift predicted class marginals onto a known test prior. Labels are not read."""

from __future__ import annotations

import numpy as np
from scipy.special import log_softmax, softmax


def fit_class_bias(logits, prior, steps: int = 40) -> np.ndarray:
    logits = np.asarray(logits, dtype=float)
    target = np.asarray(prior, dtype=float)
    target = target / target.sum()
    bias = np.zeros(logits.shape[1], dtype=float)
    for _ in range(steps):
        mean = softmax(logits + bias, axis=-1).mean(axis=0)
        bias = bias + np.log(target + 1e-12) - np.log(mean + 1e-12)
    return bias


def apply_class_bias(logits, bias) -> np.ndarray:
    return log_softmax(np.asarray(logits, dtype=float) + np.asarray(bias, dtype=float), axis=-1)
