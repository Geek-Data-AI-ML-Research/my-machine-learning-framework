"""Text blend engine. Length-sorts, then restores the caller's id order."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from mymlfw.blend.bundle import PredictionBundle
from mymlfw.blend.pool import blend
from mymlfw.blend.prior import apply_class_bias, fit_class_bias
from mymlfw.kernel.run import length_sort, unsort
from mymlfw.sanitize import guard_row, prepare_frame
from mymlfw.train.heads import SklearnHead


class TextBlendEngine:
    def __init__(self, text_col: str = "text", id_col: str = "id", fallback: str = "[empty]"):
        self.text_col = text_col
        self.id_col = id_col
        self.fallback = fallback
        self.head = SklearnHead()
        self.call_order_: list[str] = []

    def prepare(self, frame: pd.DataFrame, max_len: int = 10_000) -> pd.DataFrame:
        return prepare_frame(frame, text_col=self.text_col, max_len=max_len, fallback=self.fallback)

    def run(self, frame: pd.DataFrame, predict_row, classes, record_path=None) -> PredictionBundle:
        prepared = self.prepare(frame)
        ids = prepared[self.id_col].astype(str).to_numpy()
        lengths = prepared[self.text_col].astype(str).str.len().to_numpy()
        sorted_ids, order, restore = length_sort(ids, lengths)
        rows = [prepared.iloc[int(index)] for index in order]
        self.call_order_ = [str(row_id) for row_id in sorted_ids]
        values, _crashed = guard_row(sorted_ids, classes, rows, predict_row, record_path=record_path)
        restored = unsort(values, restore)
        return PredictionBundle(ids, np.asarray(classes).astype(str), restored, "log_probs", "text")

    def fit_head(self, features, y, groups=None):
        return self.head.fit(features, y, groups=groups)

    def blend_channels(self, bundles, weights, pool: str = "log_linear", prior=None):
        blended = blend(bundles, weights, pool=pool)
        if prior is None or blended.kind == "scores":
            return blended
        from mymlfw.blend.bundle import as_log_probs

        bias = fit_class_bias(as_log_probs(blended), prior)
        shifted = apply_class_bias(as_log_probs(blended), bias)
        return PredictionBundle(blended.ids, blended.classes, shifted, "log_probs", blended.name + "+bias")


def write_record(path: Path, ids) -> None:
    path.write_text("\n".join(ids))
