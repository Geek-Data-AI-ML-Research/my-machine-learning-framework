"""Coerce broken contest cells and keep one bad row from killing a submit."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from mymlfw.submit.checks import uniform_log_prior


def prepare_frame(frame: pd.DataFrame, text_col: str = "text", max_len: int = 10_000, fallback: str = "[empty]") -> pd.DataFrame:
    out = frame.copy()
    if text_col not in out.columns:
        return out
    values = []
    for value in out[text_col].tolist():
        if value is None or (isinstance(value, float) and np.isnan(value)) or pd.isna(value):
            text = fallback
        else:
            text = str(value)
        if text.strip() == "":
            text = fallback
        text = text.replace("\x00", "")
        if len(text) > max_len:
            text = text[:max_len]
        values.append(text)
    out[text_col] = values
    return out


def guard_row(ids, classes, rows, fn, record_path=None):
    """Call ``fn(row)`` per row. A crash becomes a uniform log-prior for that id."""
    classes = list(classes)
    width = len(classes)
    prior = uniform_log_prior(width)
    values = []
    crashed = []
    id_list = [str(item) for item in ids]
    for row_id, row in zip(id_list, rows):
        try:
            pred = np.asarray(fn(row), dtype=float)
            if pred.shape != (width,) or not np.all(np.isfinite(pred)):
                raise ValueError(f"prediction width {pred.shape} != {width} or non-finite")
            values.append(pred)
        except Exception:
            values.append(prior.copy())
            crashed.append(row_id)
    stacked = np.vstack(values) if values else np.zeros((0, width))
    if record_path is not None:
        Path(record_path).write_text(json.dumps({"ids": crashed}, indent=1) + "\n")
    return stacked, crashed
