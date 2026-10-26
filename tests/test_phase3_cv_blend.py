import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

from mymlfw.blend import (
    PredictionBundle,
    align,
    blend,
    check_shift,
    diagnose_oof,
    diversity_matrix,
    fit_class_bias,
    optimize_weights,
    save_npz,
)
from mymlfw.blend.prior import apply_class_bias
from mymlfw.cv import FoldLocalDecision, fit_unsupervised, nested_temperature, run_oof
from mymlfw.errors import ClassOrderError, MymlfwError
from scipy.special import softmax


def _bundle(name, ids, classes, values, kind="log_probs"):
    return PredictionBundle(np.asarray(ids), np.asarray(classes), np.asarray(values, dtype=float), kind, name)


def test_train_fold_fit_and_decision_refusal():
    class Spy:
        def fit(self, X, y=None):
            self.n_ = len(X)
            return self

        def transform(self, X):
            return X

    X = np.arange(20, dtype=float).reshape(10, 2)
    train_idx = np.arange(5)
    val_idx = np.arange(5, 10)
    spy = Spy()
    transformed = fit_unsupervised(spy, X, train_idx, val_idx)
    assert spy.n_ == 5
    assert transformed.shape == (5, 2)
    with pytest.raises(MymlfwError) as held_out:
        fit_unsupervised(StandardScaler(), X, val_idx, train_idx, on="held_out")
    assert held_out.value.error_code == "VAL_FOLD_FIT"
    with pytest.raises(MymlfwError) as decision:
        fit_unsupervised(StandardScaler(), FoldLocalDecision(np.zeros(5)), train_idx, val_idx)
    assert decision.value.error_code == "DECISION_AS_FEATURE"


def test_nested_temperature_does_not_score_the_fit_fold():
    logits = np.array([[8.0, 0.0], [8.0, 0.0], [0.0, 8.0], [0.0, 8.0]])
    y = np.array([0, 0, 1, 1])
    folds = [np.array([0, 1]), np.array([2, 3])]
    with pytest.raises(MymlfwError) as same:
        nested_temperature(logits, y, folds, same_fold=True)
    assert same.value.error_code == "SAME_FOLD_TEMPERATURE"
    result = nested_temperature(logits, y, folds, frozen=True)
    assert np.allclose(result["selection_logits"], logits)
    assert result["global_t"] is not None
    assert result["calibrated"].shape == logits.shape


def test_fold0_reject_does_not_fit_later_folds():
    calls = {"n": 0}

    def fit_predict(train_idx, val_idx):
        calls["n"] += 1
        return np.zeros(len(val_idx))

    X = np.zeros((10, 1))
    y = np.array([0, 1] * 5)
    groups = np.arange(10)
    result = run_oof(
        X, y, groups, fit_predict,
        n_splits=5, metric=lambda truth, pred: 0.0,
        fold0_only=True, baseline_fold0=0.5, min_delta=0.01,
    )
    assert result.status == "fold0_reject"
    assert calls["n"] == 1
    assert np.isnan(result.oof).any()
    finite = result.oof[np.isfinite(result.oof)]
    assert finite.size > 0
    assert np.all(finite == 0.0)


def test_align_reorders_rows_and_raises_on_class_permutation():
    reference = _bundle("branch_a", ["b", "a"], ["A", "B"], [[0.1, 0.9], [0.8, 0.2]])
    flipped_rows = _bundle("branch_b", ["a", "b"], ["A", "B"], [[0.8, 0.2], [0.1, 0.9]])
    aligned = align([reference, flipped_rows])
    assert aligned.bundles[1].ids.tolist() == ["b", "a"]
    assert np.allclose(aligned.bundles[1].values[0], [0.1, 0.9])
    permuted = _bundle("branch_b", ["b", "a"], ["B", "A"], [[0.9, 0.1], [0.2, 0.8]])
    with pytest.raises(ClassOrderError) as error:
        align([reference, permuted])
    assert error.value.error_code == "CLASS_ORDER_MISMATCH"
    assert "reorder-classes" in error.value.suggested_fix
    dropped = align([reference, permuted], weights=[0.2, 0.8], on_mismatch="drop_and_warn")
    assert dropped.warnings[0]["branch"] == "branch_b"
    assert dropped.weights.tolist() == pytest.approx([1.0])


def test_log_linear_does_not_use_a_hard_floor_and_differs_from_linear():
    balanced = _bundle("balanced", ["1"], ["A", "B"], [[np.log(0.6), np.log(0.4)]])
    sharp = _bundle("sharp", ["1"], ["A", "B"], [[np.log(1 - 1e-6), np.log(1e-6)]])
    with pytest.raises(MymlfwError):
        blend([balanced, sharp], [0.8, 0.2], eps=1e-9)
    log_linear = blend([balanced, sharp], [0.8, 0.2], pool="log_linear")
    linear = blend([balanced, sharp], [0.8, 0.2], pool="linear")
    assert log_linear.kind == "log_probs"
    assert linear.kind == "log_probs"
    assert np.exp(log_linear.values)[0, 1] > 0.01
    assert not np.allclose(log_linear.values, linear.values)
    cool = blend([balanced, balanced], [0.5, 0.5], temperatures=[1.0, 1.0])
    flat = blend([balanced, balanced], [0.5, 0.5], temperatures=[8.0, 8.0])
    assert not np.allclose(cool.values, flat.values)
    left = _bundle("left", ["b", "a"], ["A", "B"], np.log([[0.2, 0.8], [0.7, 0.3]]))
    right = _bundle("right", ["a", "b"], ["A", "B"], np.log([[0.7, 0.3], [0.2, 0.8]]))
    mixed = blend([left, right], [0.5, 0.5])
    same = blend([left, left], [0.5, 0.5])
    assert mixed.ids.tolist() == ["b", "a"]
    assert np.allclose(mixed.values, same.values)
    with pytest.raises(MymlfwError) as weights:
        blend([left, right], [1.0])
    assert weights.value.error_code == "WEIGHT_COUNT"


def test_rank_and_power_return_scores():
    left = _bundle("left", ["1", "2"], ["A", "B"], [[0.9, 0.1], [0.2, 0.8]])
    right = _bundle("right", ["1", "2"], ["A", "B"], [[0.6, 0.4], [0.4, 0.6]])
    ranked = blend([left, right], [0.5, 0.5], pool="rank")
    powered = blend([left, right], [0.5, 0.5], pool="power", power=2)
    assert ranked.kind == "scores"
    assert powered.kind == "scores"
    assert ranked.values.shape == (2, 2)


def test_optimize_weights_stays_on_the_simplex_and_l2_pulls_toward_uniform():
    classes = ["0", "1"]
    ids = ["a", "b", "c", "d"]
    perfect = np.log([[0.9, 0.1], [0.1, 0.9], [0.8, 0.2], [0.2, 0.8]])
    wrong = np.log([[0.1, 0.9], [0.9, 0.1], [0.2, 0.8], [0.8, 0.2]])
    bundles = [
        _bundle("perfect", ids, classes, perfect),
        _bundle("wrong", ids, classes, wrong),
    ]
    y = np.array(["0", "1", "0", "1"])

    def metric(truth, bundle):
        index = {label: i for i, label in enumerate(bundle.classes.tolist())}
        pred = bundle.values.argmax(axis=1)
        gold = np.array([index[str(value)] for value in truth])
        return float(np.mean(pred == gold))

    loose = optimize_weights(bundles, y, metric, l2=0.001)
    tight = optimize_weights(bundles, y, metric, l2=10.0)
    assert loose.sum() == pytest.approx(1.0)
    assert loose.min() >= -1e-8
    assert loose[0] > loose[1]
    assert abs(tight[0] - 0.5) < abs(loose[0] - 0.5)


def test_diversity_warns_on_a_redundant_weaker_branch():
    values = np.log([[0.7, 0.3], [0.2, 0.8], [0.6, 0.4], [0.4, 0.6]])
    bundles = [
        _bundle("kept", ["a", "b", "c", "d"], ["0", "1"], values),
        _bundle("copy", ["a", "b", "c", "d"], ["0", "1"], values),
    ]
    report = diversity_matrix(bundles, standalone_cv=[0.9, 0.4])
    assert report["warnings"][0]["error_code"] == "HIGH_REDUNDANCY"
    assert report["warnings"][0]["branch"] == "copy"
    constant = np.full((4, 2), np.log(0.5))
    copies = [
        _bundle("kept", ["a", "b", "c", "d"], ["0", "1"], constant),
        _bundle("copy", ["a", "b", "c", "d"], ["0", "1"], constant),
    ]
    constant_report = diversity_matrix(copies, standalone_cv=[0.9, 0.4])
    assert constant_report["warnings"][0]["branch"] == "copy"


def test_class_bias_matches_a_uniform_prior():
    logits = np.tile(np.array([5.0, 0.0]), (200, 1))
    bias = fit_class_bias(logits, [0.5, 0.5])
    mean = softmax(logits + bias, axis=1).mean(axis=0)
    assert mean == pytest.approx([0.5, 0.5], abs=0.02)
    assert apply_class_bias(logits, bias).shape == logits.shape


def test_diagnose_oof_writes_the_autopsy_headings(tmp_path):
    ids = [f"r{i}" for i in range(8)]
    classes = np.array(["cat", "dog"])
    values = np.log(np.clip(np.array([
        [0.9, 0.1], [0.2, 0.8], [0.4, 0.6], [0.7, 0.3],
        [0.1, 0.9], [0.8, 0.2], [0.3, 0.7], [0.6, 0.4],
    ]), 1e-6, 1))
    path = tmp_path / "oof.npz"
    save_npz(path, PredictionBundle(ids, classes, values, "log_probs", "oof"))
    train = pd.DataFrame({
        "id": ids,
        "label": ["cat", "dog", "cat", "dog", "cat", "dog", "cat", "dog"],
        "text": ["a", "bb", "ccc", "dddd", "eeeee", "ffffff", "ggggggg", "hhhhhhhh"],
        "group": ["g"] * 4 + ["h"] * 4,
    })
    out = diagnose_oof(path, train, tmp_path / "ERROR_AUTOPSY.md")
    text = out.read_text()
    for heading in ("## confusion", "## length_quartile", "## group_size", "## highest_loss"):
        assert heading in text


def test_check_shift_flags_drift_and_accepts_a_matched_pair():
    drifted_train = pd.DataFrame({"drift": np.zeros(50)})
    drifted_test = pd.DataFrame({"drift": np.ones(50)})
    with pytest.raises(MymlfwError) as error:
        check_shift(drifted_train, drifted_test, ["drift"])
    assert error.value.error_code == "SHIFT_DETECTED"
    assert "drift" in error.value.fields["top_features"]
    rng = np.random.default_rng(0)
    features = rng.normal(size=(200, 2))
    matched_train = pd.DataFrame(features, columns=["a", "b"])
    matched_test = pd.DataFrame(features, columns=["a", "b"])
    result = check_shift(matched_train, matched_test, ["a", "b"])
    assert result["auc"] <= 0.65
