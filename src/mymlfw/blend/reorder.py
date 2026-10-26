"""Permute a branch onto a target class order and id order."""

from __future__ import annotations

import numpy as np

from mymlfw.blend.bundle import PredictionBundle, load_npz, save_npz
from mymlfw.errors import AlignmentError, ClassOrderError


def reorder_classes(target_path, source_path, out_path) -> PredictionBundle:
    target = load_npz(target_path, name="target")
    source = load_npz(source_path, name=str(source_path))
    src_cols = {label: index for index, label in enumerate(source.classes.tolist())}
    missing_cols = [label for label in target.classes.tolist() if label not in src_cols]
    if missing_cols:
        raise ClassOrderError(target.classes.tolist(), source.classes.tolist(), file=str(source_path), target=str(target_path))
    src_rows = {row_id: index for index, row_id in enumerate(source.ids.tolist())}
    missing_rows = [row_id for row_id in target.ids.tolist() if row_id not in src_rows]
    if missing_rows:
        raise AlignmentError("Source is missing target ids.", file=str(source_path), missing=missing_rows)
    columns = [src_cols[label] for label in target.classes.tolist()]
    rows = [src_rows[row_id] for row_id in target.ids.tolist()]
    values = source.values[np.ix_(rows, columns)]
    bundle = PredictionBundle(target.ids, target.classes, values, source.kind, source.name)
    save_npz(out_path, bundle)
    return bundle
