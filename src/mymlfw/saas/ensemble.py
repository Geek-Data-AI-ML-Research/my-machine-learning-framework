"""Nested-CV ensemble sandbox (NumPy/SciPy only — no torch).

Shared by API, CLI, MCP, and the ascii board renderer. Caruana forward
hill-climb with optional SLSQP polish; ``mode=auto`` picks the best
``nested_cv_score``.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

import numpy as np
from scipy import stats
from scipy.optimize import minimize

from mymlfw.saas.fold_badges import paired_snr
from mymlfw.saas.ids import new_experiment_id

EnsembleMode = Literal["linear", "rank", "logit", "geometric", "auto"]
DiversityMethod = Literal["spearman", "pearson"]
MetricName = Literal["auc", "log_loss", "mse"]

# Refuse full-matrix work above this in the API process (N × C × M).
IN_API_CEILING = 50_000_000
DUST_WEIGHT = 1e-4
_EPS = 1e-7
_ALPHA_GRID = np.linspace(0.05, 0.95, 19, dtype=np.float64)
_BLEND_MODES: tuple[EnsembleMode, ...] = ("linear", "rank", "logit", "geometric")
BOARD_WIDTH = 88


class EnsembleError(Exception):
    """Validation / ceiling failure for the ensemble sandbox."""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error_code": self.code, "message": self.message}
        body.update(self.extra)
        return body


@dataclass(frozen=True)
class OofCandidate:
    """One model's OOF predictions aligned to a shared row order."""

    name: str
    predictions: np.ndarray  # (N,) or (N, C) float32
    oof_id: str | None = None
    split_hash: str | None = None


@dataclass
class EnsembleResult:
    mode: EnsembleMode
    weights: np.ndarray
    candidate_names: list[str]
    candidate_oof_ids: list[str | None]
    nested_cv_score: float
    oof_blend_score: float
    fold_scores: list[float]
    fold_deltas: list[float]
    fold_snr: float
    p_value: float
    verdict: str
    diversity: np.ndarray
    diversity_method: DiversityMethod
    metric: MetricName
    subsampled: bool = False
    offload_hint: str | None = None
    ncm: int = 0
    kept_indices: list[int] = field(default_factory=list)
    requested_mode: EnsembleMode | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": self.mode,
            "requested_mode": self.requested_mode or self.mode,
            "weights": [float(w) for w in self.weights.tolist()],
            "candidate_names": list(self.candidate_names),
            "candidate_oof_ids": list(self.candidate_oof_ids),
            "nested_cv_score": float(self.nested_cv_score),
            "oof_blend_score": float(self.oof_blend_score),
            "fold_scores": [float(x) for x in self.fold_scores],
            "fold_deltas": [float(x) for x in self.fold_deltas],
            "fold_snr": float(self.fold_snr),
            "p_value": float(self.p_value),
            "verdict": self.verdict,
            "diversity_method": self.diversity_method,
            "metric": self.metric,
            "subsampled": self.subsampled,
            "offload_hint": self.offload_hint,
            "ncm": int(self.ncm),
            "kept_indices": list(self.kept_indices),
            "ascii_board": render_ensemble_ascii_board(self),
        }


def compute_split_hash(
    folds: np.ndarray,
    *,
    row_ids: Sequence[str] | np.ndarray | None = None,
) -> str:
    """Stable hash of fold assignment (+ optional row ids) for OOF alignment."""
    folds_i = np.asarray(folds, dtype=np.int64)
    h = hashlib.sha256()
    h.update(b"folds:")
    h.update(folds_i.tobytes())
    if row_ids is not None:
        ids = np.asarray(row_ids, dtype=object)
        h.update(b"|ids:")
        for rid in ids.tolist():
            h.update(str(rid).encode("utf-8"))
            h.update(b"\0")
    return h.hexdigest()[:32]


def load_predictions_f32(values: np.ndarray | Sequence[Any]) -> np.ndarray:
    """Cast predictions to float32; accept (N,) or (N, C)."""
    arr = np.asarray(values, dtype=np.float32)
    if arr.ndim not in (1, 2):
        raise EnsembleError(
            "bad_pred_shape",
            "Predictions must be rank-1 (N,) or rank-2 (N, C).",
            shape=list(arr.shape),
        )
    return arr


def ncm_product(n: int, c: int, m: int) -> int:
    return int(n) * int(c) * int(m)


def maybe_subsample_indices(
    n: int,
    c: int,
    m: int,
    folds: np.ndarray,
    *,
    ceiling: int = IN_API_CEILING,
    rng: np.random.Generator | None = None,
    allow_subsample: bool = True,
) -> tuple[np.ndarray | None, str | None]:
    """Return ``(indices, offload_hint)``. ``indices`` is None when unused.

    When N×C×M exceeds ``ceiling`` and ``allow_subsample`` is False, returns a
    worker-offload hint and no indices (caller must refuse in-api work).
    """
    product = ncm_product(n, c, m)
    if product <= ceiling:
        return None, None
    hint = (
        f"N×C×M={product} exceeds in-api ceiling {ceiling}; "
        "dispatch optimize_ensemble to a worker (float32 memmap / chunked) "
        "or pass allow_subsample=True for a fold-stratified row subsample."
    )
    if not allow_subsample:
        return None, hint
    target_n = max(ceiling // max(c * m, 1), 1)
    target_n = min(target_n, n)
    folds_i = np.asarray(folds, dtype=np.int64)
    rng = rng or np.random.default_rng(0)
    unique = np.unique(folds_i)
    # Guarantee ≥1 row per fold first so nested CV never sees empty held-out folds.
    picked: list[int] = []
    for f in unique:
        ix = np.flatnonzero(folds_i == f)
        if len(ix) == 0:
            continue
        picked.append(int(rng.choice(ix, size=1, replace=False)[0]))
    remaining_budget = max(target_n - len(picked), 0)
    if remaining_budget > 0:
        per_fold = max(remaining_budget // max(len(unique), 1), 0)
        for f in unique:
            if remaining_budget <= 0:
                break
            ix = np.flatnonzero(folds_i == f)
            already = set(picked)
            avail = [int(i) for i in ix.tolist() if int(i) not in already]
            if not avail:
                continue
            take = min(len(avail), max(per_fold, 1), remaining_budget)
            if take <= 0:
                continue
            chosen = rng.choice(np.asarray(avail, dtype=np.int64), size=take, replace=False)
            for i in chosen.tolist():
                picked.append(int(i))
                remaining_budget -= 1
    if len(picked) < target_n:
        remaining = np.setdiff1d(np.arange(n), np.asarray(picked, dtype=np.int64))
        extra = min(len(remaining), target_n - len(picked))
        if extra:
            picked.extend(
                int(i) for i in rng.choice(remaining, size=extra, replace=False).tolist()
            )
    indices = np.asarray(sorted(set(picked)), dtype=np.int64)
    kept = set(int(x) for x in np.unique(folds_i[indices]).tolist())
    missing = [int(f) for f in unique.tolist() if int(f) not in kept]
    if missing:
        raise EnsembleError(
            "subsample_empty_fold",
            "Fold-stratified subsample dropped fold(s); refuse nested CV.",
            missing_folds=missing,
        )
    return indices, hint


def validate_oof_alignment(
    candidates: Sequence[OofCandidate],
    *,
    y: np.ndarray,
    folds: np.ndarray,
    expected_split_hash: str | None = None,
) -> None:
    """Refuse misaligned / constant / <2-model OOF stacks."""
    if len(candidates) < 2:
        raise EnsembleError(
            "need_two_models",
            "Ensemble requires at least 2 OOF candidates.",
            n_candidates=len(candidates),
        )
    y_arr = np.asarray(y)
    folds_i = np.asarray(folds)
    n = int(y_arr.shape[0])
    if folds_i.shape[0] != n:
        raise EnsembleError(
            "fold_length_mismatch",
            "folds length must match labels.",
            n_labels=n,
            n_folds=int(folds_i.shape[0]),
        )
    if len(np.unique(folds_i)) < 2:
        raise EnsembleError("need_two_folds", "Nested CV needs at least 2 folds.")

    ref_hash = expected_split_hash
    for cand in candidates:
        pred = np.asarray(cand.predictions)
        if pred.shape[0] != n:
            raise EnsembleError(
                "n_mismatch",
                f"Candidate {cand.name!r} row count differs from labels.",
                name=cand.name,
                n_pred=int(pred.shape[0]),
                n_labels=n,
            )
        flat = pred.reshape(pred.shape[0], -1)
        if flat.shape[1] == 0:
            raise EnsembleError("empty_pred", f"Candidate {cand.name!r} has empty preds.")
        if float(np.nanstd(flat.astype(np.float64))) < 1e-12:
            raise EnsembleError(
                "constant_preds",
                f"Candidate {cand.name!r} predictions are constant.",
                name=cand.name,
            )
        if cand.split_hash and ref_hash and cand.split_hash != ref_hash:
            raise EnsembleError(
                "split_hash_mismatch",
                f"Candidate {cand.name!r} split_hash does not match expected.",
                name=cand.name,
                got=cand.split_hash,
                expected=ref_hash,
            )
        if cand.split_hash and ref_hash is None:
            ref_hash = cand.split_hash
    hashes = {c.split_hash for c in candidates if c.split_hash}
    if len(hashes) > 1:
        raise EnsembleError(
            "split_hash_mismatch",
            "OOF candidates disagree on split_hash.",
            hashes=sorted(hashes),
        )


def diversity_matrix(
    candidates: Sequence[OofCandidate],
    *,
    method: DiversityMethod = "spearman",
) -> np.ndarray:
    """Vectorized Spearman (default) or Pearson correlation across candidates."""
    m = len(candidates)
    if m == 0:
        return np.zeros((0, 0), dtype=np.float64)
    cols: list[np.ndarray] = []
    for cand in candidates:
        pred = np.asarray(cand.predictions, dtype=np.float64)
        if pred.ndim == 1:
            cols.append(pred)
        else:
            cols.append(pred.mean(axis=1))
    mat = np.column_stack(cols)
    if method == "spearman":
        ranked = np.apply_along_axis(stats.rankdata, 0, mat)
        corr = np.corrcoef(ranked, rowvar=False)
    elif method == "pearson":
        corr = np.corrcoef(mat, rowvar=False)
    else:
        raise EnsembleError("bad_diversity_method", "Use spearman or pearson.", method=method)
    if np.ndim(corr) == 0:
        corr = np.array([[float(corr)]], dtype=np.float64)
    corr = np.asarray(corr, dtype=np.float64)
    np.fill_diagonal(corr, 1.0)
    return np.nan_to_num(corr, nan=0.0, posinf=1.0, neginf=-1.0)


def select_diverse_candidates(
    candidates: Sequence[OofCandidate],
    *,
    y: np.ndarray,
    metric: MetricName = "auc",
    method: DiversityMethod = "spearman",
    corr_threshold: float = 0.99,
) -> tuple[list[int], np.ndarray]:
    """Greedy prune: keep best solo score, drop clones above corr threshold."""
    if not candidates:
        return [], np.zeros((0, 0))
    corr = diversity_matrix(candidates, method=method)
    y_arr = np.asarray(y)
    solo = [
        _score_predictions(y_arr, np.asarray(c.predictions, dtype=np.float64), metric)
        for c in candidates
    ]
    order = list(np.argsort(np.asarray(solo))[::-1])
    kept: list[int] = []
    for idx in order:
        if any(float(corr[idx, j]) >= corr_threshold for j in kept):
            continue
        kept.append(int(idx))
    if not kept:
        kept = [int(order[0])]
    return kept, corr


def _clip_probs(p: np.ndarray) -> np.ndarray:
    return np.clip(p, _EPS, 1.0 - _EPS)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


def fold_local_ranks(preds: np.ndarray, folds: np.ndarray) -> np.ndarray:
    """Rank predictions within each fold (avoids cross-fold range leakage)."""
    folds_i = np.asarray(folds)
    out = np.empty_like(preds, dtype=np.float64)
    if preds.ndim == 1:
        for f in np.unique(folds_i):
            mask = folds_i == f
            n = int(mask.sum())
            if n == 0:
                continue
            out[mask] = stats.rankdata(preds[mask], method="average") / max(n, 1)
        return out
    for c in range(preds.shape[1]):
        out[:, c] = fold_local_ranks(preds[:, c], folds_i)
    return out


def transform_for_blend(
    preds: np.ndarray,
    folds: np.ndarray,
    mode: EnsembleMode,
) -> np.ndarray:
    """Map predictions into the blend space (linear/rank/logit/geometric)."""
    p = np.asarray(preds, dtype=np.float64)
    if mode == "linear":
        return p
    if mode == "rank":
        return fold_local_ranks(p, folds)
    if mode == "logit":
        return np.log(_clip_probs(p) / (1.0 - _clip_probs(p)))
    if mode == "geometric":
        return np.log(_clip_probs(p))
    raise EnsembleError("bad_mode", "Unknown blend mode.", mode=mode)


def inverse_transform(blended: np.ndarray, mode: EnsembleMode) -> np.ndarray:
    if mode in ("linear", "rank"):
        return blended
    if mode == "logit":
        return _sigmoid(blended)
    if mode == "geometric":
        return np.exp(blended)
    raise EnsembleError("bad_mode", "Unknown blend mode.", mode=mode)


def _stack_models(
    candidates: Sequence[OofCandidate],
    folds: np.ndarray,
    mode: EnsembleMode,
) -> np.ndarray:
    """Stack transformed preds to (N, M) binary or (N, C, M) multiclass."""
    transformed = [
        transform_for_blend(np.asarray(c.predictions, dtype=np.float64), folds, mode)
        for c in candidates
    ]
    return np.stack(transformed, axis=-1)


def blend_weights(stack: np.ndarray, weights: np.ndarray, mode: EnsembleMode) -> np.ndarray:
    w = np.asarray(weights, dtype=np.float64)
    w = w / max(float(w.sum()), _EPS)
    if stack.ndim == 2:
        blended = stack @ w
    else:
        blended = np.tensordot(stack, w, axes=([-1], [0]))
    return inverse_transform(blended, mode)


def _binary_auc(y: np.ndarray, scores: np.ndarray) -> float:
    y_i = np.asarray(y, dtype=np.int64).ravel()
    s = np.asarray(scores, dtype=np.float64).ravel()
    pos = s[y_i == 1]
    neg = s[y_i == 0]
    n_pos = int(pos.size)
    n_neg = int(neg.size)
    if n_pos == 0 or n_neg == 0:
        return 0.5
    all_s = np.concatenate([pos, neg])
    ranks = stats.rankdata(all_s)
    sum_pos = float(ranks[:n_pos].sum())
    return float((sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _log_loss_score(y: np.ndarray, preds: np.ndarray) -> float:
    """Higher is better (= negated binary / multiclass log loss)."""
    y_i = np.asarray(y).ravel()
    p = np.asarray(preds, dtype=np.float64)
    if p.ndim == 1:
        p1 = _clip_probs(p)
        ll = y_i * np.log(p1) + (1 - y_i) * np.log(1.0 - p1)
        return float(np.mean(ll))
    p = p / np.clip(p.sum(axis=1, keepdims=True), _EPS, None)
    p = _clip_probs(p)
    rows = np.arange(len(y_i))
    return float(np.mean(np.log(p[rows, y_i.astype(np.int64)])))


def _mse_score(y: np.ndarray, preds: np.ndarray) -> float:
    y_f = np.asarray(y, dtype=np.float64).ravel()
    p = np.asarray(preds, dtype=np.float64)
    if p.ndim == 2:
        p = p[:, 1] if p.shape[1] > 1 else p[:, 0]
    return float(-np.mean((y_f - p.ravel()) ** 2))


def _score_predictions(y: np.ndarray, preds: np.ndarray, metric: MetricName) -> float:
    p = np.asarray(preds, dtype=np.float64)
    if metric == "auc":
        if p.ndim == 2:
            if p.shape[1] == 2:
                return _binary_auc(y, p[:, 1])
            y_i = np.asarray(y, dtype=np.int64).ravel()
            aucs = []
            for c in range(p.shape[1]):
                binary = (y_i == c).astype(np.int64)
                if binary.min() == binary.max():
                    continue
                aucs.append(_binary_auc(binary, p[:, c]))
            return float(np.mean(aucs)) if aucs else 0.5
        return _binary_auc(y, p)
    if metric == "log_loss":
        return _log_loss_score(y, p)
    if metric == "mse":
        return _mse_score(y, p)
    raise EnsembleError("bad_metric", "Use auc, log_loss, or mse.", metric=metric)


def _renorm_dust(weights: np.ndarray, dust: float = DUST_WEIGHT) -> np.ndarray:
    w = np.asarray(weights, dtype=np.float64).copy()
    w[w < dust] = 0.0
    s = float(w.sum())
    if s <= 0:
        w[:] = 1.0 / len(w)
        return w
    return w / s


def caruana_hillclimb(
    stack: np.ndarray,
    y: np.ndarray,
    mode: EnsembleMode,
    *,
    metric: MetricName = "auc",
    max_rounds: int | None = None,
) -> np.ndarray:
    """Forward stepwise blend with a vectorized α mixing grid."""
    m = stack.shape[-1]
    y_arr = np.asarray(y)
    solo = np.array(
        [
            _score_predictions(y_arr, inverse_transform(stack[..., j], mode), metric)
            for j in range(m)
        ],
        dtype=np.float64,
    )
    best_i = int(np.argmax(solo))
    weights = np.zeros(m, dtype=np.float64)
    weights[best_i] = 1.0
    current = stack[..., best_i].copy()
    best_score = float(solo[best_i])
    rounds = max_rounds if max_rounds is not None else max(2 * m, 8)

    for _ in range(rounds):
        improved = False
        best_alpha = 0.0
        best_j = -1
        best_trial_score = best_score
        for j in range(m):
            cand = stack[..., j]
            # trials[a] = (1-α)*current + α*cand  — vectorized over α
            if current.ndim == 1:
                trials = (1.0 - _ALPHA_GRID)[:, None] * current + _ALPHA_GRID[:, None] * cand
            else:
                trials = (
                    (1.0 - _ALPHA_GRID)[:, None, None] * current
                    + _ALPHA_GRID[:, None, None] * cand
                )
            scores = np.empty(len(_ALPHA_GRID), dtype=np.float64)
            for a_i in range(len(_ALPHA_GRID)):
                scores[a_i] = _score_predictions(
                    y_arr, inverse_transform(trials[a_i], mode), metric
                )
            a_best = int(np.argmax(scores))
            if scores[a_best] > best_trial_score + 1e-12:
                best_trial_score = float(scores[a_best])
                best_alpha = float(_ALPHA_GRID[a_best])
                best_j = j
                improved = True
        if not improved or best_j < 0:
            break
        current = (1.0 - best_alpha) * current + best_alpha * stack[..., best_j]
        weights = (1.0 - best_alpha) * weights
        weights[best_j] += best_alpha
        best_score = best_trial_score

    return _renorm_dust(weights)


def slsqp_polish(
    stack: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    mode: EnsembleMode,
    *,
    metric: MetricName = "auc",
) -> np.ndarray:
    """Optional SLSQP refinement on active (above-dust) weights."""
    w0 = _renorm_dust(weights)
    active = np.flatnonzero(w0 > DUST_WEIGHT)
    if active.size < 2:
        return w0
    y_arr = np.asarray(y)
    x0 = w0[active].copy()
    x0 = x0 / x0.sum()

    def objective(x: np.ndarray) -> float:
        full = np.zeros_like(w0)
        full[active] = np.maximum(x, 0.0)
        s = float(full.sum())
        if s <= 0:
            return 1e6
        full /= s
        pred = blend_weights(stack, full, mode)
        return -_score_predictions(y_arr, pred, metric)

    cons = {"type": "eq", "fun": lambda x: float(np.sum(x) - 1.0)}
    bounds = [(0.0, 1.0)] * int(active.size)
    result = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"maxiter": 200, "ftol": 1e-12},
    )
    full = np.zeros_like(w0)
    if result.success:
        full[active] = np.maximum(result.x, 0.0)
    else:
        full[active] = x0
    return _renorm_dust(full)


def fit_weights(
    candidates: Sequence[OofCandidate],
    y: np.ndarray,
    folds: np.ndarray,
    mode: EnsembleMode,
    *,
    metric: MetricName = "auc",
    polish: bool = True,
) -> np.ndarray:
    if mode == "auto":
        raise EnsembleError("bad_mode", "fit_weights requires a concrete mode, not auto.")
    stack = _stack_models(candidates, folds, mode)
    w = caruana_hillclimb(stack, y, mode, metric=metric)
    if polish:
        w = slsqp_polish(stack, y, w, mode, metric=metric)
    return w


def nested_cv_scores(
    candidates: Sequence[OofCandidate],
    y: np.ndarray,
    folds: np.ndarray,
    mode: EnsembleMode,
    *,
    metric: MetricName = "auc",
    polish: bool = True,
) -> tuple[float, list[float], np.ndarray]:
    """Fit on K−1 folds, score held-out fold; also return full-OOF weights."""
    folds_i = np.asarray(folds)
    y_arr = np.asarray(y)
    unique = np.unique(folds_i)
    fold_scores: list[float] = []
    for f in unique:
        train_mask = folds_i != f
        test_mask = folds_i == f
        train_cands = [
            OofCandidate(
                name=c.name,
                predictions=np.asarray(c.predictions)[train_mask],
                oof_id=c.oof_id,
                split_hash=c.split_hash,
            )
            for c in candidates
        ]
        w = fit_weights(
            train_cands,
            y_arr[train_mask],
            folds_i[train_mask],
            mode,
            metric=metric,
            polish=polish,
        )
        test_cands = [
            OofCandidate(
                name=c.name,
                predictions=np.asarray(c.predictions)[test_mask],
                oof_id=c.oof_id,
                split_hash=c.split_hash,
            )
            for c in candidates
        ]
        stack_te = _stack_models(test_cands, folds_i[test_mask], mode)
        pred = blend_weights(stack_te, w, mode)
        fold_scores.append(_score_predictions(y_arr[test_mask], pred, metric))
    full_w = fit_weights(candidates, y_arr, folds_i, mode, metric=metric, polish=polish)
    nested = float(np.mean(fold_scores)) if fold_scores else 0.0
    return nested, fold_scores, full_w


def _baseline_fold_scores(
    candidates: Sequence[OofCandidate],
    y: np.ndarray,
    folds: np.ndarray,
    metric: MetricName,
) -> list[float]:
    """Best single-model score per fold (for paired SNR / t-test)."""
    folds_i = np.asarray(folds)
    y_arr = np.asarray(y)
    out: list[float] = []
    for f in np.unique(folds_i):
        mask = folds_i == f
        best = -math.inf
        for c in candidates:
            s = _score_predictions(y_arr[mask], np.asarray(c.predictions)[mask], metric)
            if s > best:
                best = s
        out.append(float(best))
    return out


def _verdict(oof_blend: float, nested: float, p_value: float, snr: float) -> str:
    gap = oof_blend - nested
    if gap > 0.01 and (p_value > 0.1 or snr < 1.0):
        return "WARN: WEIGHT OVERFIT (TRUST NESTED CV)"
    if snr >= 1.0 and p_value <= 0.1:
        return "SOLID SIGNAL"
    if gap > 0.02:
        return "WARN: WEIGHT OVERFIT (TRUST NESTED CV)"
    return "SOLID SIGNAL" if snr >= 0.5 else "WARN: WEIGHT OVERFIT (TRUST NESTED CV)"


def optimize_ensemble(
    candidates: Sequence[OofCandidate],
    *,
    y: np.ndarray,
    folds: np.ndarray,
    mode: EnsembleMode = "auto",
    metric: MetricName = "auc",
    diversity_method: DiversityMethod = "spearman",
    corr_threshold: float = 0.99,
    polish: bool = True,
    expected_split_hash: str | None = None,
    allow_subsample: bool = True,
    rng: np.random.Generator | None = None,
    prune_diverse: bool = True,
) -> EnsembleResult:
    """Validate → diversify → nested-CV Caruana (+ SLSQP); ``auto`` picks best nested score."""
    y_arr = np.asarray(y)
    folds_i = np.asarray(folds)
    validate_oof_alignment(
        candidates, y=y_arr, folds=folds_i, expected_split_hash=expected_split_hash
    )

    loaded = [
        OofCandidate(
            name=c.name,
            predictions=load_predictions_f32(c.predictions),
            oof_id=c.oof_id,
            split_hash=c.split_hash,
        )
        for c in candidates
    ]

    sample = np.asarray(loaded[0].predictions)
    c_dim = 1 if sample.ndim == 1 else int(sample.shape[1])
    n, m = int(sample.shape[0]), len(loaded)
    idx, offload_hint = maybe_subsample_indices(
        n, c_dim, m, folds_i, allow_subsample=allow_subsample, rng=rng
    )
    subsampled = False
    if offload_hint and idx is None:
        raise EnsembleError(
            "needs_worker_offload",
            offload_hint,
            ncm=ncm_product(n, c_dim, m),
            ceiling=IN_API_CEILING,
            suggested_fix=(
                "Re-run with allow_subsample=True or dispatch to a worker "
                "with float32 memmap / chunked Caruana."
            ),
        )
    if idx is not None:
        subsampled = True
        y_arr = y_arr[idx]
        folds_i = folds_i[idx]
        loaded = [
            OofCandidate(
                name=c.name,
                predictions=np.asarray(c.predictions)[idx],
                oof_id=c.oof_id,
                split_hash=c.split_hash,
            )
            for c in loaded
        ]

    working = list(loaded)
    kept = list(range(len(working)))
    corr = diversity_matrix(working, method=diversity_method)
    if prune_diverse:
        kept, corr = select_diverse_candidates(
            working,
            y=y_arr,
            metric=metric,
            method=diversity_method,
            corr_threshold=corr_threshold,
        )
        working = [working[i] for i in kept]
        if len(working) < 2:
            solo = [
                _score_predictions(y_arr, np.asarray(c.predictions, dtype=np.float64), metric)
                for c in loaded
            ]
            kept = [int(i) for i in np.argsort(solo)[::-1][:2]]
            working = [loaded[i] for i in kept]
            corr = diversity_matrix(working, method=diversity_method)

    modes: tuple[EnsembleMode, ...] = _BLEND_MODES if mode == "auto" else (mode,)
    best: EnsembleResult | None = None
    for md in modes:
        nested, fold_scores, weights = nested_cv_scores(
            working, y_arr, folds_i, md, metric=metric, polish=polish
        )
        stack = _stack_models(working, folds_i, md)
        oof_pred = blend_weights(stack, weights, md)
        oof_blend = _score_predictions(y_arr, oof_pred, metric)
        baseline = _baseline_fold_scores(working, y_arr, folds_i, metric)
        deltas = [fs - b for fs, b in zip(fold_scores, baseline)]
        snr = float(paired_snr(deltas))
        if snr == float("inf"):
            snr_out = 1e6
        elif snr == float("-inf"):
            snr_out = -1e6
        else:
            snr_out = float(snr)
        if len(deltas) >= 2 and float(np.std(deltas, ddof=1)) > 0:
            p_value = float(stats.ttest_1samp(deltas, 0.0).pvalue)
        else:
            p_value = 1.0
        if p_value != p_value:
            p_value = 1.0
        cand_result = EnsembleResult(
            mode=md,
            weights=weights,
            candidate_names=[c.name for c in working],
            candidate_oof_ids=[c.oof_id for c in working],
            nested_cv_score=nested,
            oof_blend_score=oof_blend,
            fold_scores=fold_scores,
            fold_deltas=deltas,
            fold_snr=snr_out,
            p_value=p_value,
            verdict=_verdict(oof_blend, nested, p_value, snr_out),
            diversity=corr,
            diversity_method=diversity_method,
            metric=metric,
            subsampled=subsampled,
            offload_hint=offload_hint if subsampled else None,
            ncm=ncm_product(n, c_dim, m),
            kept_indices=list(kept),
            requested_mode=mode,
        )
        if best is None or cand_result.nested_cv_score > best.nested_cv_score + 1e-15:
            best = cand_result
    assert best is not None
    return best


def render_ensemble_ascii_board(result: EnsembleResult | dict[str, Any]) -> str:
    """Identical 88-col ``<pre>`` board for web / CLI / MCP."""
    if isinstance(result, EnsembleResult):
        mode = result.mode
        nested = result.nested_cv_score
        oof_b = result.oof_blend_score
        snr = result.fold_snr
        p_value = result.p_value
        verdict = result.verdict
        names = result.candidate_names
        weights = [float(w) for w in result.weights.tolist()]
        subsampled = result.subsampled
        req = result.requested_mode
    else:
        mode = str(result.get("mode", "?"))
        nested = float(result.get("nested_cv_score", 0.0))
        oof_b = float(result.get("oof_blend_score", 0.0))
        snr = float(result.get("fold_snr", 0.0))
        p_value = float(result.get("p_value", 1.0))
        verdict = str(result.get("verdict", ""))
        names = list(result.get("candidate_names") or [])
        weights = [float(w) for w in (result.get("weights") or [])]
        subsampled = bool(result.get("subsampled"))
        req = result.get("requested_mode")

    def line(text: str) -> str:
        inner = text[: BOARD_WIDTH - 4]
        return "| " + inner.ljust(BOARD_WIDTH - 4) + " |"

    border = "+" + ("=" * (BOARD_WIDTH - 2)) + "+"
    gap = oof_b - nested
    weight_bits = " ".join(
        f"{names[i] if i < len(names) else f'm{i}'}={weights[i]:.3f}"
        for i in range(len(weights))
    )
    mode_label = f"{mode}" if req in (None, mode) else f"{mode} (auto)"
    sub = " subsampled" if subsampled else ""
    rows = [
        border,
        line(f"ENSEMBLE SANDBOX  mode={mode_label}{sub}"),
        line(
            f"nested_cv={nested:.4f}  oof_blend={oof_b:.4f}  "
            f"Δ={gap:+.4f}  p={p_value:.3f}  SNR={snr:.2f}"
        ),
        line(f"VERDICT: {verdict}"),
        line(f"weights: {weight_bits}"),
        border,
    ]
    return "\n".join(rows)


def plan_ensemble(
    oof_ids: list[str],
    *,
    mode: EnsembleMode = "auto",
) -> dict[str, Any]:
    """Describe an ensemble job for the given ready OOF artifact ids."""
    ids = list(oof_ids)
    if len(ids) < 2:
        return {
            "status": "error",
            "error_code": "need_two_models",
            "oof_ids": ids,
            "suggested_fix": "Pass at least two ready oof_artifacts.",
        }
    return {
        "status": "ready",
        "oof_ids": ids,
        "mode": mode,
        "blend_modes": list(_BLEND_MODES) if mode == "auto" else [mode],
        "ceiling": IN_API_CEILING,
        "offload_path": (
            "If N×C×M > 5e7: fold-stratified subsample in-api, or worker "
            "float32 memmap / chunked Caruana (never OOM the api process)."
        ),
        "steps": [
            "validate_oof_alignment + split_hash",
            "diversity_matrix + select_diverse_candidates",
            "Caruana hill-climb (+ optional SLSQP)",
            "nested_cv_score vs oof_blend_score",
            "render_ensemble_ascii_board",
            "optional promote_blend_to_experiment",
        ],
    }


def promote_blend_to_experiment(
    *,
    parent_oof_ids: Sequence[str],
    weights: Sequence[float],
    mode: EnsembleMode,
    project_id: str,
    goal_id: str | None = None,
    parent_experiment_ids: Sequence[str] | None = None,
    nested_cv_score: float | None = None,
    fold_scores: Sequence[float] | None = None,
    artifact_repo: Any | None = None,
    require_ready_oofs: bool = True,
) -> dict[str, Any]:
    """Build an ``ensemble_blend`` experiment lineage record.

    When ``artifact_repo`` is provided (or the process default is set), parent
    OOF ids must exist, belong to ``project_id``, and be ``ready`` before
    promote — client-supplied scores alone are never trusted as lineage proof.
    """
    if len(parent_oof_ids) < 2:
        raise EnsembleError(
            "need_two_models",
            "Promote requires at least two parent OOF ids.",
        )
    if len(weights) != len(parent_oof_ids):
        raise EnsembleError(
            "weight_length_mismatch",
            "weights length must match parent_oof_ids.",
        )
    if require_ready_oofs:
        _assert_parent_oofs_ready(
            parent_oof_ids,
            project_id=project_id,
            artifact_repo=artifact_repo,
        )
    exp_id = new_experiment_id()
    draft = {
        "_id": exp_id,
        "project_id": project_id,
        "goal_id": goal_id,
        "strategy": "ensemble_blend",
        "variable": f"ensemble_blend:{mode}",
        "parent_oof_ids": list(parent_oof_ids),
        "parent_experiment_ids": list(parent_experiment_ids or []),
        "weights": [float(w) for w in weights],
        "mode": mode,
        "fold_scores": [float(x) for x in (fold_scores or [])],
        "cv_mean": float(nested_cv_score) if nested_cv_score is not None else None,
        "status": "open",
        "band_low": 0.0,
        "band_high": 0.05,
        "lineage_verified": bool(require_ready_oofs and artifact_repo is not None),
    }
    return {
        "status": "created",
        "experiment_id": exp_id,
        "strategy": "ensemble_blend",
        "parent_oof_ids": list(parent_oof_ids),
        "weights": [float(w) for w in weights],
        "mode": mode,
        "experiment": draft,
        "detail": (
            "Lineage verified against ready OOF artifacts."
            if draft["lineage_verified"]
            else (
                "Lineage draft created; blended OOF/test parquet → MinIO and "
                "experiments insert land when artifact promote is wired."
            )
        ),
    }


def _assert_parent_oofs_ready(
    parent_oof_ids: Sequence[str],
    *,
    project_id: str,
    artifact_repo: Any | None,
) -> None:
    """Refuse promote when OOF artifacts are missing, wrong project, or not ready."""
    if artifact_repo is None:
        # No artifact surface in this process — refuse forged promote by default.
        raise EnsembleError(
            "oof_lineage_unverified",
            "Promote requires a ready OOF artifact repo for parent_oof_ids.",
            parent_oof_ids=list(parent_oof_ids),
        )
    for oof_id in parent_oof_ids:
        doc = None
        if hasattr(artifact_repo, "get"):
            doc = artifact_repo.get(oof_id)
        elif hasattr(artifact_repo, "repo") and hasattr(artifact_repo.repo, "get"):
            doc = artifact_repo.repo.get(oof_id)
        if doc is None:
            raise EnsembleError(
                "oof_not_found",
                f"Unknown parent OOF id {oof_id}.",
                oof_id=oof_id,
            )
        if str(doc.get("project_id") or "") != str(project_id):
            raise EnsembleError(
                "oof_wrong_project",
                f"OOF {oof_id} does not belong to project {project_id}.",
                oof_id=oof_id,
            )
        status = str(doc.get("status") or "")
        if status != "ready":
            raise EnsembleError(
                "oof_not_ready",
                f"OOF {oof_id} status={status}; confirm HEAD before promote.",
                oof_id=oof_id,
                status=status,
            )


def promote_blend_to_experiment_stub(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Back-compat alias from the Phase C starter stub."""
    return promote_blend_to_experiment(*args, **kwargs)
