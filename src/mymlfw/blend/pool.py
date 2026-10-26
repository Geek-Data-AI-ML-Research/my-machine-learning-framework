"""Log-linear, linear, rank, and power pools."""

from __future__ import annotations

import numpy as np
from scipy.special import log_softmax
from scipy.stats import rankdata

from mymlfw.blend.bundle import PredictionBundle
from mymlfw.errors import MymlfwError


def _probabilities(bundle: PredictionBundle, temperature: float) -> np.ndarray:
    temperature = float(temperature)
    if bundle.kind == "logits":
        return np.exp(log_softmax(bundle.values / temperature, axis=-1))
    if bundle.kind == "log_probs":
        return np.exp(log_softmax(bundle.values / temperature, axis=-1))
    probs = np.clip(bundle.values, 0.0, None)
    totals = probs.sum(axis=1, keepdims=True)
    totals = np.where(totals <= 0, 1.0, totals)
    probs = probs / totals
    if temperature == 1.0:
        return probs
    return np.exp(log_softmax(np.log(np.clip(probs, 1e-12, None)) / temperature, axis=-1))


def blend(bundles, weights, pool: str = "log_linear", temperatures=None, eps: float = 1e-6, power: float = 2.0) -> PredictionBundle:
    if not (1e-7 <= float(eps) <= 1e-5):
        raise MymlfwError(
            "EPS_OUT_OF_RANGE",
            "eps must lie in [1e-7, 1e-5].",
            eps=eps,
        )
    from mymlfw.blend.align import align

    weights = np.asarray(weights, dtype=float)
    if weights.ndim != 1 or len(weights) != len(bundles):
        raise MymlfwError(
            "WEIGHT_COUNT",
            "Pass one weight for each prediction bundle.",
            weights=int(weights.size),
            bundles=len(bundles),
        )
    if not np.isfinite(weights).all() or float(weights.sum()) <= 0:
        raise MymlfwError("BAD_WEIGHTS", "Weights must be finite and sum to a positive number.")
    if temperatures is not None and len(temperatures) != len(bundles):
        raise MymlfwError(
            "TEMPERATURE_COUNT",
            "Pass one temperature for each prediction bundle.",
            temperatures=len(temperatures),
            bundles=len(bundles),
        )
    aligned = align(bundles, weights, on_mismatch="raise")
    bundles = aligned.bundles
    weights = np.asarray(aligned.weights, dtype=float)
    if temperatures is None:
        temperatures = [1.0] * len(bundles)
    probs = [_probabilities(bundle, temperature) for bundle, temperature in zip(bundles, temperatures)]
    reference = bundles[0]
    if pool == "log_linear":
        acc = np.zeros_like(probs[0])
        for weight, prob in zip(weights, probs):
            acc = acc + weight * np.log(np.clip(prob, eps, 1.0))
        values = log_softmax(acc, axis=-1)
        kind = "log_probs"
    elif pool == "linear":
        acc = np.zeros_like(probs[0])
        for weight, prob in zip(weights, probs):
            acc = acc + weight * prob
        values = np.log(np.clip(acc, eps, 1.0))
        kind = "log_probs"
    elif pool == "rank":
        acc = np.zeros_like(probs[0])
        n_rows = probs[0].shape[0]
        for weight, prob in zip(weights, probs):
            ranks = np.column_stack(
                [rankdata(prob[:, column], method="average") / (n_rows + 1) for column in range(prob.shape[1])]
            )
            acc = acc + weight * ranks
        values = acc
        kind = "scores"
    elif pool == "power":
        acc = np.zeros_like(probs[0])
        for weight, prob in zip(weights, probs):
            acc = acc + weight * np.power(prob, power)
        values = acc
        kind = "scores"
    else:
        raise MymlfwError("BAD_POOL", "Use log_linear, linear, rank, or power.", pool=pool)
    return PredictionBundle(
        ids=reference.ids,
        classes=reference.classes,
        values=values,
        kind=kind,
        name=pool,
    )
