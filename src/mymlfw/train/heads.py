"""Sklearn heads, shrunk group centering, and optional torch twins."""

from __future__ import annotations

import numpy as np
from scipy.special import log_softmax
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from mymlfw.blend.bundle import PredictionBundle
from mymlfw.blend.pool import blend
from mymlfw.errors import MymlfwError


def shrunk_center(features, group_ids, alpha: float = 4.0) -> np.ndarray:
    features = np.asarray(features, dtype=float)
    group_ids = np.asarray(group_ids)
    global_mean = features.mean(axis=0)
    centered = np.empty_like(features)
    for group in np.unique(group_ids):
        mask = group_ids == group
        count = int(mask.sum())
        group_mean = features[mask].mean(axis=0)
        shrunk = (count * group_mean + alpha * global_mean) / (count + alpha)
        centered[mask] = features[mask] - shrunk
    return centered


class SklearnHead:
    def __init__(self, alpha: float = 4.0):
        self.alpha = alpha
        self.scaler = None
        self.clf = None
        self.twin = None
        self.classes_ = None
        self.W_ = None
        self.b_ = None
        self.mode = "hard"

    def fit(self, X, y, groups=None, soft_targets=None, kl_alpha: float = 0.5):
        if not 0.0 <= float(kl_alpha) <= 1.0:
            raise MymlfwError("BAD_KL_ALPHA", "kl_alpha must lie in [0, 1].", kl_alpha=kl_alpha)
        X = np.asarray(X, dtype=float)
        y = np.asarray(y)
        self.scaler = StandardScaler().fit(X)
        scaled = self.scaler.transform(X)
        if soft_targets is None:
            self.mode = "hard"
            self.clf = LogisticRegression(max_iter=400)
            self.clf.fit(scaled, y)
            self.classes_ = np.asarray(self.clf.classes_)
            self.W_ = np.asarray(self.clf.coef_, dtype=float).T
            if self.W_.ndim == 1:
                self.W_ = self.W_.reshape(-1, 1)
            if self.W_.shape[1] == 1 and len(self.classes_) == 2:
                # sklearn stores a single hyperplane for binary problems
                full = np.concatenate([-self.W_, self.W_], axis=1)
                intercept = np.asarray(self.clf.intercept_, dtype=float).reshape(-1)
                self.W_ = full
                self.b_ = np.concatenate([-intercept, intercept])
            else:
                self.b_ = np.asarray(self.clf.intercept_, dtype=float)
        else:
            self.mode = "soft"
            log_soft, classes = _soft_matrix(soft_targets, y)
            self.classes_ = classes
            self._fit_soft(scaled, y, log_soft, float(kl_alpha))
        if groups is not None:
            centered = shrunk_center(scaled, groups, alpha=self.alpha)
            self.twin = LogisticRegression(max_iter=400)
            self.twin.fit(centered, y)
        return self

    def _fit_soft(self, X, y, log_soft, kl_alpha: float):
        import scipy.optimize

        n_rows, n_features = X.shape
        n_classes = log_soft.shape[1]
        soft = np.exp(log_soft)
        soft = soft / soft.sum(axis=1, keepdims=True)
        class_index = {str(label): index for index, label in enumerate(self.classes_.tolist())}
        y_index = np.array([class_index[str(label)] for label in np.asarray(y).tolist()])

        def objective(theta):
            weight = theta[: n_features * n_classes].reshape(n_features, n_classes)
            bias = theta[n_features * n_classes :]
            logits = X @ weight + bias
            logp = log_softmax(logits, axis=1)
            ce = -float(np.mean(logp[np.arange(n_rows), y_index]))
            kl = float(np.mean(np.sum(soft * (np.log(np.clip(soft, 1e-12, 1.0)) - logp), axis=1)))
            return (1.0 - kl_alpha) * ce + kl_alpha * kl

        result = scipy.optimize.minimize(objective, np.zeros(n_features * n_classes + n_classes), method="L-BFGS-B")
        self.W_ = result.x[: n_features * n_classes].reshape(n_features, n_classes)
        self.b_ = result.x[n_features * n_classes :]

    def decision_function(self, X) -> np.ndarray:
        scaled = self.scaler.transform(np.asarray(X, dtype=float))
        return scaled @ self.W_ + self.b_

    def predict_proba(self, X) -> np.ndarray:
        return np.exp(log_softmax(self.decision_function(X), axis=1))

    def blend_with_twin(self, X, groups, ids, pool: str = "log_linear"):
        scaled = self.scaler.transform(np.asarray(X, dtype=float))
        plain = self.predict_proba(X)
        centered = shrunk_center(scaled, groups, alpha=self.alpha)
        twin_logits = centered @ np.asarray(self.twin.coef_).T + np.asarray(self.twin.intercept_)
        if twin_logits.ndim == 1:
            twin_logits = twin_logits.reshape(-1, 1)
        if twin_logits.shape[1] == 1 and len(self.classes_) == 2:
            twin_logits = np.concatenate([-twin_logits, twin_logits], axis=1)
        twin = np.exp(log_softmax(twin_logits, axis=1))
        classes = np.asarray(self.classes_).astype(str)
        row_ids = np.asarray(ids).astype(str)
        left = PredictionBundle(row_ids, classes, np.log(np.clip(plain, 1e-12, 1)), "log_probs", "plain")
        right = PredictionBundle(row_ids, classes, np.log(np.clip(twin, 1e-12, 1)), "log_probs", "twin")
        return blend([left, right], [0.5, 0.5], pool=pool), centered


def _soft_matrix(soft_targets, y):
    if isinstance(soft_targets, PredictionBundle):
        log_soft = soft_targets.values if soft_targets.kind == "log_probs" else np.log(np.clip(soft_targets.values, 1e-12, 1))
        classes = soft_targets.classes
        return log_soft, classes
    array = np.asarray(soft_targets, dtype=float)
    if array.ndim != 2:
        raise MymlfwError("BAD_SOFT_TARGETS", "soft_targets must be a bundle or a 2-d array.")
    classes = np.unique(y)
    if array.shape[1] != len(classes) and array.min() < 0:
        return array, classes
    if array.min() < 0:
        return array, np.asarray([str(index) for index in range(array.shape[1])])
    return np.log(np.clip(array, 1e-12, 1.0)), np.asarray(classes).astype(str) if array.shape[1] == len(np.unique(y)) else np.arange(array.shape[1]).astype(str)


class TwinHead:
    """NumPy twin head. A torch module is built by torch_twin_head when torch is installed."""

    def __init__(self, n_features: int, n_classes: int, alpha: float = 4.0, seed: int = 0):
        rng = np.random.default_rng(seed)
        scale = 0.05
        self.W = rng.normal(scale=scale, size=(n_features, n_classes))
        self.b = np.zeros(n_classes)
        self.Wc = rng.normal(scale=scale, size=(n_features, n_classes))
        self.bc = np.zeros(n_classes)
        self.alpha = alpha

    def forward(self, pooled, y, group_ids):
        features = _as_features(pooled)
        y = np.asarray(y)
        group_ids = np.asarray(group_ids)
        centered = shrunk_center(features, group_ids, alpha=self.alpha)
        logits = features @ self.W + self.b
        logits_c = centered @ self.Wc + self.bc
        n_classes = logits.shape[1]
        y_index = y.astype(int) if np.issubdtype(y.dtype, np.number) else np.array([i for i in y])
        loss = _ce(logits, y_index) + _ce(logits_c, y_index)
        return float(loss), centered


class DualRegionCosineHead:
    def __init__(self, n_features: int, n_classes: int, alpha: float = 4.0, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.left = rng.normal(scale=0.05, size=(n_features, n_classes))
        self.right = rng.normal(scale=0.05, size=(n_features, n_classes))
        self.alpha = alpha

    def forward(self, pooled, y, group_ids):
        features = _as_features(pooled)
        centered = shrunk_center(features, np.asarray(group_ids), alpha=self.alpha)
        left = _cosine_logits(features, self.left)
        right = _cosine_logits(centered, self.right)
        y_index = np.asarray(y).astype(int)
        loss = 0.5 * _ce(left, y_index) + 0.5 * _ce(right, y_index)
        return float(loss), centered


class GroupAwareBatchSampler:
    def __init__(self, group_ids, min_per_group: int = 4):
        self.group_ids = np.asarray(group_ids)
        self.min_per_group = min_per_group

    def __iter__(self):
        buckets: dict = {}
        for index, group in enumerate(self.group_ids.tolist()):
            buckets.setdefault(group, []).append(index)
        for indexes in buckets.values():
            if len(indexes) >= self.min_per_group:
                yield np.asarray(indexes[: max(self.min_per_group, len(indexes))])
            else:
                yield np.asarray(indexes)


def torch_twin_head(n_layers: int, hidden: int, n_classes: int, alpha: float = 4.0):
    import torch
    from torch import nn

    def _center(features, group_ids):
        groups = group_ids if hasattr(group_ids, "detach") else torch.as_tensor(group_ids)
        groups = groups.to(device=features.device)
        global_mean = features.mean(dim=0)
        centered = torch.zeros_like(features)
        mask_dtype = features.dtype
        for group in torch.unique(groups):
            mask = (groups == group).to(dtype=mask_dtype).unsqueeze(-1)
            count = mask.sum()
            group_mean = (features * mask).sum(dim=0) / count.clamp_min(1.0)
            shrunk = (count * group_mean + alpha * global_mean) / (count + alpha)
            centered = centered + (features - shrunk) * mask
        return centered

    class _TorchTwin(nn.Module):
        def __init__(self):
            super().__init__()
            width = hidden * n_layers
            self.norms = nn.ModuleList([nn.LayerNorm(hidden) for _ in range(n_layers)])
            self.proj = nn.Linear(width, n_classes)
            self.centered = nn.Linear(width, n_classes)
            self.alpha = alpha

        def forward(self, pooled_layers, y, group_ids):
            encoded = torch.cat([norm(layer) for norm, layer in zip(self.norms, pooled_layers)], dim=-1)
            loss_plain = nn.functional.cross_entropy(self.proj(encoded), y)
            centered = _center(encoded, group_ids)
            loss_centered = nn.functional.cross_entropy(self.centered(centered), y)
            return loss_plain + loss_centered, centered

    return _TorchTwin()


def _as_features(pooled) -> np.ndarray:
    if isinstance(pooled, (list, tuple)):
        arrays = [np.asarray(layer, dtype=float) for layer in pooled]
        return np.concatenate(arrays, axis=-1)
    if hasattr(pooled, "detach"):
        return pooled.detach().cpu().numpy()
    return np.asarray(pooled, dtype=float)


def _ce(logits, y_index) -> float:
    logp = log_softmax(logits, axis=1)
    return float(-np.mean(logp[np.arange(len(y_index)), y_index]))


def _cosine_logits(features, weight) -> np.ndarray:
    feat = features / (np.linalg.norm(features, axis=1, keepdims=True) + 1e-8)
    bank = weight / (np.linalg.norm(weight, axis=0, keepdims=True) + 1e-8)
    return feat @ bank
