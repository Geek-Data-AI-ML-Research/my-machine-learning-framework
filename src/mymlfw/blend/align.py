"""Align branches on ids. Class permutations raise unless the caller opts into a drop."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from mymlfw.blend.bundle import PredictionBundle
from mymlfw.errors import AlignmentError, ClassOrderError, MymlfwError


@dataclass
class AlignResult:
    bundles: list
    weights: np.ndarray
    warnings: list = field(default_factory=list)


def _reorder(reference: PredictionBundle, bundle: PredictionBundle) -> PredictionBundle:
    if len(bundle.ids) != len(set(bundle.ids.tolist())):
        raise AlignmentError("Ids must be unique.", file=bundle.name)
    if not np.array_equal(reference.classes, bundle.classes):
        if set(reference.classes.tolist()) == set(bundle.classes.tolist()):
            raise ClassOrderError(
                expected=reference.classes.tolist(),
                got=bundle.classes.tolist(),
                file=bundle.name,
                target=reference.name,
            )
        raise ClassOrderError(
            expected=reference.classes.tolist(),
            got=bundle.classes.tolist(),
            file=bundle.name,
            target=reference.name,
        )
    index = {row_id: i for i, row_id in enumerate(bundle.ids.tolist())}
    missing = [row_id for row_id in reference.ids.tolist() if row_id not in index]
    extra = [row_id for row_id in bundle.ids.tolist() if row_id not in set(reference.ids.tolist())]
    if missing or extra:
        raise AlignmentError(
            "Every branch must contain the same ids.",
            file=bundle.name,
            missing=missing,
            extra=extra,
        )
    order = [index[row_id] for row_id in reference.ids.tolist()]
    return PredictionBundle(
        ids=reference.ids,
        classes=bundle.classes,
        values=bundle.values[order],
        kind=bundle.kind,
        name=bundle.name,
    )


def align(bundles, weights=None, on_mismatch: str = "raise") -> AlignResult:
    if on_mismatch not in {"raise", "drop_and_warn"}:
        raise MymlfwError(
            "BAD_MISMATCH_MODE",
            "Use on_mismatch='raise' or on_mismatch='drop_and_warn'.",
            on_mismatch=on_mismatch,
        )
    if not bundles:
        raise MymlfwError("EMPTY_BLEND", "Pass at least one prediction bundle.")
    if weights is None:
        weights = np.ones(len(bundles), dtype=float)
    weights = np.asarray(weights, dtype=float)
    reference = bundles[0]
    if len(reference.ids) != len(set(reference.ids.tolist())):
        raise AlignmentError("Ids must be unique.", file=reference.name)
    kept = [reference]
    kept_w = [float(weights[0])]
    warnings = []
    for bundle, weight in zip(bundles[1:], weights[1:]):
        try:
            kept.append(_reorder(reference, bundle))
            kept_w.append(float(weight))
        except (AlignmentError, ClassOrderError) as exc:
            if on_mismatch == "raise":
                raise
            warnings.append(
                {
                    "error_code": exc.error_code,
                    "branch": bundle.name,
                    "suggested_fix": exc.suggested_fix,
                }
            )
    total = float(sum(kept_w))
    normalized = np.asarray(kept_w, dtype=float) / total
    return AlignResult(kept, normalized, warnings)
