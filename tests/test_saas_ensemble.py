"""Focused unit tests for saas.ensemble with synthetic OOFs."""

from __future__ import annotations

import numpy as np
import pytest

from mymlfw.saas.ensemble import (
    EnsembleError,
    OofCandidate,
    compute_split_hash,
    diversity_matrix,
    maybe_subsample_indices,
    ncm_product,
    optimize_ensemble,
    plan_ensemble,
    promote_blend_to_experiment,
    render_ensemble_ascii_board,
    select_diverse_candidates,
    validate_oof_alignment,
)


def _make_binary_oofs(
    n: int = 200,
    n_folds: int = 5,
    seed: int = 0,
    *,
    clone: bool = False,
    overfit_noise: bool = False,
):
    rng = np.random.default_rng(seed)
    folds = np.repeat(np.arange(n_folds), n // n_folds)[:n]
    if folds.size < n:
        folds = np.concatenate([folds, np.zeros(n - folds.size, dtype=int)])
    # Latent signal
    z = rng.normal(size=n)
    y = (z + rng.normal(scale=0.5, size=n) > 0).astype(np.int64)
    split = compute_split_hash(folds)

    def _pred(noise: float, shift: float = 0.0) -> np.ndarray:
        raw = z + shift + rng.normal(scale=noise, size=n)
        # Squash to (0, 1)
        return (1.0 / (1.0 + np.exp(-raw))).astype(np.float32)

    p0 = _pred(0.4)
    p1 = _pred(0.55, shift=0.1)
    if clone:
        p2 = p0.copy()
    else:
        p2 = _pred(0.7, shift=-0.05)
    if overfit_noise:
        # Model that memorizes y almost perfectly on full OOF (will overfit weights)
        p_mem = y.astype(np.float32) * 0.95 + 0.025
        p_mem = np.clip(p_mem + rng.normal(scale=0.01, size=n).astype(np.float32), 0.01, 0.99)
        cands = [
            OofCandidate("base", p0, oof_id="oof_base", split_hash=split),
            OofCandidate("alt", p1, oof_id="oof_alt", split_hash=split),
            OofCandidate("mem", p_mem, oof_id="oof_mem", split_hash=split),
        ]
    else:
        cands = [
            OofCandidate("m0", p0, oof_id="oof_m0", split_hash=split),
            OofCandidate("m1", p1, oof_id="oof_m1", split_hash=split),
            OofCandidate("m2", p2, oof_id="oof_m2", split_hash=split),
        ]
    return cands, y, folds, split


def test_validate_alignment_and_split_hash():
    cands, y, folds, split = _make_binary_oofs()
    validate_oof_alignment(cands, y=y, folds=folds, expected_split_hash=split)
    bad = list(cands)
    bad[1] = OofCandidate(
        "bad",
        cands[1].predictions,
        oof_id="oof_bad",
        split_hash="deadbeefdeadbeef",
    )
    with pytest.raises(EnsembleError) as ei:
        validate_oof_alignment(bad, y=y, folds=folds, expected_split_hash=split)
    assert ei.value.code == "split_hash_mismatch"


def test_refuse_single_model_and_constant():
    cands, y, folds, split = _make_binary_oofs()
    with pytest.raises(EnsembleError) as ei:
        validate_oof_alignment(cands[:1], y=y, folds=folds)
    assert ei.value.code == "need_two_models"
    const = OofCandidate(
        "c",
        np.full(y.shape[0], 0.5, dtype=np.float32),
        split_hash=split,
    )
    with pytest.raises(EnsembleError) as ei2:
        validate_oof_alignment([cands[0], const], y=y, folds=folds)
    assert ei2.value.code == "constant_preds"


def test_diversity_prune_drops_clone():
    cands, y, folds, _ = _make_binary_oofs(clone=True)
    corr = diversity_matrix(cands, method="spearman")
    assert corr.shape == (3, 3)
    assert corr[0, 2] > 0.99
    kept, _ = select_diverse_candidates(cands, y=y, corr_threshold=0.99)
    assert 0 in kept or 2 in kept
    assert not (0 in kept and 2 in kept)


def test_optimize_linear_and_auto():
    cands, y, folds, _ = _make_binary_oofs()
    linear = optimize_ensemble(
        cands, y=y, folds=folds, mode="linear", polish=True, prune_diverse=False
    )
    assert linear.weights.shape == (3,)
    assert abs(float(linear.weights.sum()) - 1.0) < 1e-6
    assert linear.nested_cv_score == pytest.approx(np.mean(linear.fold_scores), rel=1e-6)
    auto = optimize_ensemble(cands, y=y, folds=folds, mode="auto", polish=False)
    assert auto.mode in ("linear", "rank", "logit", "geometric")
    assert auto.requested_mode == "auto"
    board = render_ensemble_ascii_board(auto)
    assert "ENSEMBLE SANDBOX" in board
    assert "nested_cv=" in board
    assert all(len(row) == 88 for row in board.splitlines())


def test_nested_score_leq_optimistic_when_overfit_forced():
    """Full-OOF blend can look better than nested CV when a memorizer is present."""
    cands, y, folds, _ = _make_binary_oofs(overfit_noise=True, seed=1)
    result = optimize_ensemble(
        cands,
        y=y,
        folds=folds,
        mode="linear",
        polish=False,
        prune_diverse=False,
    )
    # Optimistic full-fit score should be >= honest nested CV (within float noise).
    assert result.oof_blend_score + 1e-9 >= result.nested_cv_score
    assert "VERDICT" in render_ensemble_ascii_board(result) or result.verdict


def test_blend_modes_rank_logit_geometric():
    cands, y, folds, _ = _make_binary_oofs(n=100, seed=2)
    for mode in ("rank", "logit", "geometric"):
        res = optimize_ensemble(
            cands[:2], y=y, folds=folds, mode=mode, polish=False, prune_diverse=False
        )
        assert res.mode == mode
        assert len(res.weights) == 2


def test_ceiling_subsample_and_offload():
    n, c, m = 1000, 10, 6000  # 6e7 > 5e7
    folds = np.zeros(n, dtype=int)
    folds[n // 2 :] = 1
    idx, hint = maybe_subsample_indices(n, c, m, folds, allow_subsample=True)
    assert hint is not None
    assert idx is not None
    assert len(idx) < n
    idx2, hint2 = maybe_subsample_indices(n, c, m, folds, allow_subsample=False)
    assert idx2 is None
    assert "worker" in (hint2 or "").lower()
    assert ncm_product(n, c, m) > 50_000_000


def test_plan_and_promote_stub():
    from mymlfw.saas.artifacts import InMemoryArtifactRepo

    plan = plan_ensemble(["oof_a", "oof_b"], mode="auto")
    assert plan["status"] == "ready"
    assert plan["ceiling"] == 50_000_000
    project_id = "prj_01HTESTPROJECT000000000000"
    repo = InMemoryArtifactRepo()
    for oid in ("oof_a", "oof_b"):
        repo.insert(
            {
                "_id": oid,
                "project_id": project_id,
                "status": "ready",
            }
        )
    promo = promote_blend_to_experiment(
        parent_oof_ids=["oof_a", "oof_b"],
        weights=[0.6, 0.4],
        mode="linear",
        project_id=project_id,
        artifact_repo=repo,
    )
    assert promo["status"] == "created"
    assert promo["strategy"] == "ensemble_blend"
    assert promo["experiment"]["parent_oof_ids"] == ["oof_a", "oof_b"]
    assert promo["experiment_id"].startswith("exp_")
    assert promo["experiment"]["lineage_verified"] is True


def test_promote_refuses_unready_oofs():
    from mymlfw.saas.ensemble import EnsembleError

    with pytest.raises(EnsembleError) as ei:
        promote_blend_to_experiment(
            parent_oof_ids=["oof_a", "oof_b"],
            weights=[0.6, 0.4],
            mode="linear",
            project_id="prj_01HTESTPROJECT000000000000",
            artifact_repo=None,
        )
    assert ei.value.code == "oof_lineage_unverified"


def test_plan_needs_two():
    plan = plan_ensemble(["oof_only"])
    assert plan["status"] == "error"
    assert plan["error_code"] == "need_two_models"
