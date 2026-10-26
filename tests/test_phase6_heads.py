import numpy as np
import pytest
import scipy.optimize
from sklearn.linear_model import LogisticRegression

from mymlfw.blend import PredictionBundle
from mymlfw.errors import MymlfwError
from mymlfw.train import DualRegionCosineHead, GroupAwareBatchSampler, SklearnHead, TwinHead, shrunk_center


def test_singleton_group_is_finite_and_not_zero():
    features = np.array([[3.0, 0.0], [0.0, 1.0], [0.0, 2.0], [0.0, 3.0], [0.0, 4.0]])
    groups = np.array([0, 1, 1, 1, 1])
    centered = shrunk_center(features, groups)
    assert np.isfinite(centered[0]).all()
    assert not np.allclose(centered[0], 0)


def test_twin_head_requires_group_ids_and_a_large_group_is_finite():
    head = TwinHead(n_features=4, n_classes=2, seed=0)
    features = np.random.default_rng(0).normal(size=(8, 4))
    labels = np.array([0, 1, 0, 1, 0, 1, 0, 1])
    groups = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    with pytest.raises(TypeError):
        head.forward(features, labels)
    loss, centered = head.forward(features, labels, groups)
    assert np.isfinite(loss)
    assert centered.shape[0] == 8
    singleton = TwinHead(n_features=2, n_classes=2, seed=1)
    small = np.array([[3.0, 0.0], [0.0, 1.0], [0.0, 2.0], [0.0, 3.0], [0.0, 4.0]])
    _loss, small_centered = singleton.forward(small, np.array([0, 1, 0, 1, 0]), np.array([0, 1, 1, 1, 1]))
    assert np.isfinite(_loss)
    assert not np.allclose(small_centered[0], 0)


def test_dual_region_loss_is_finite():
    head = DualRegionCosineHead(n_features=4, n_classes=2)
    features = np.random.default_rng(1).normal(size=(8, 4))
    loss, _centered = head.forward(features, np.array([0, 1, 0, 1, 0, 1, 0, 1]), np.array([0, 0, 0, 0, 1, 1, 1, 1]))
    assert np.isfinite(loss)


def test_soft_targets_use_lbfgs_and_not_logistic_regression(monkeypatch):
    def fail_fit(self, *args, **kwargs):
        raise AssertionError("LogisticRegression.fit was called")

    monkeypatch.setattr(LogisticRegression, "fit", fail_fit)
    calls = {}
    real = scipy.optimize.minimize

    def wrapped(fun, x0, **kwargs):
        calls["method"] = kwargs.get("method")
        return real(fun, x0, **kwargs)

    monkeypatch.setattr(scipy.optimize, "minimize", wrapped)
    rng = np.random.default_rng(0)
    features = rng.normal(size=(30, 3))
    labels = np.array([0] * 20 + [1] * 10)
    soft = np.full((30, 2), 0.5)
    SklearnHead().fit(features, labels, soft_targets=soft, kl_alpha=0.5)
    assert calls["method"] == "L-BFGS-B"


def test_uniform_soft_targets_move_predictions_toward_uniform():
    rng = np.random.default_rng(1)
    features = rng.normal(size=(80, 3))
    labels = np.array([0] * 70 + [1] * 10)
    hard = SklearnHead().fit(features, labels)
    soft = SklearnHead().fit(features, labels, soft_targets=np.full((80, 2), 0.5), kl_alpha=0.8)
    hard_mean = hard.predict_proba(features)[:, 0].mean()
    soft_mean = soft.predict_proba(features)[:, 0].mean()
    assert abs(soft_mean - 0.5) < abs(hard_mean - 0.5)


def test_bad_kl_alpha_raises():
    with pytest.raises(MymlfwError):
        SklearnHead().fit(np.ones((4, 2)), np.array([0, 1, 0, 1]), kl_alpha=2)


def test_group_sampler_keeps_at_least_four_when_possible():
    groups = np.array([0, 0, 0, 0, 0, 0, 1])
    batches = list(GroupAwareBatchSampler(groups, min_per_group=4))
    large = next(batch for batch in batches if np.all(groups[batch] == 0))
    assert len(large) >= 4


def test_torch_twin_skips_without_the_extra():
    torch = pytest.importorskip("torch")
    from mymlfw.train.heads import torch_twin_head

    head = torch_twin_head(n_layers=1, hidden=4, n_classes=2)
    pooled = [torch.randn(4, 4)]
    labels = torch.tensor([0, 1, 0, 1])
    groups = torch.tensor([0, 0, 0, 0])
    with pytest.raises(TypeError):
        head.forward(pooled, labels)
    loss, _centered = head.forward(pooled, labels, groups)
    assert torch.isfinite(loss)
    loss.backward()
    assert head.proj.weight.grad is not None
    assert torch.isfinite(head.proj.weight.grad).all()
    assert float(head.proj.weight.grad.abs().sum()) > 0
