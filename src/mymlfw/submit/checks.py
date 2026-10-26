"""Submission column contracts."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mymlfw.errors import DuplicateCandidateError, MymlfwError


def check_id_label(frame: pd.DataFrame, label_col: str, classes) -> pd.DataFrame:
    if "id" not in frame.columns or label_col not in frame.columns:
        raise MymlfwError(
            "BAD_COLUMNS",
            "The submission needs an id column and one label column.",
            columns=list(frame.columns),
        )
    if frame.columns.tolist().count("id") != 1:
        raise MymlfwError("BAD_COLUMNS", "The id column must appear once.")
    ids = frame["id"].astype(str)
    if ids.duplicated().any() or frame["id"].isna().any():
        raise MymlfwError("ID_MISMATCH", "Submission ids must be unique and non-null.")
    allowed = [str(label) for label in classes]
    if allowed != sorted(allowed):
        raise MymlfwError("CLASS_ORDER_MISMATCH", "Pass classes as a fixed sorted tuple.", expected=sorted(allowed), got=allowed)
    labels = frame[label_col].astype(str)
    if not labels.isin(allowed).all() or frame[label_col].isna().any():
        raise MymlfwError("BAD_LABEL", "Every label must belong to the class list.", label_col=label_col)
    return frame


def check_ranked_topk(frame: pd.DataFrame, cand_col: str = "candidates", max_k: int = 25, sep: str = ";") -> pd.DataFrame:
    if "id" not in frame.columns or cand_col not in frame.columns:
        raise MymlfwError("BAD_COLUMNS", "Ranked submissions need id and a candidate column.")
    if frame["id"].astype(str).duplicated().any():
        raise MymlfwError("ID_MISMATCH", "Submission ids must be unique.")
    for raw in frame[cand_col].astype(str):
        parts = [part for part in raw.split(sep) if part != ""]
        if len(parts) > max_k:
            raise MymlfwError("RANK_TOO_LONG", f"At most {max_k} candidates are allowed.", max_k=max_k)
        if len(parts) != len(set(parts)):
            raise DuplicateCandidateError(ranked=parts)
    return frame


def check_scale_report(report: dict, min_rows_per_sec: float | None = None) -> dict:
    projected = float(report["projected_seconds"])
    limit = 8.5 * 3600
    if projected > limit:
        raise MymlfwError(
            "SCALE_TOO_SLOW",
            "The projected hidden-test runtime exceeds 8.5 hours.",
            projected_seconds=projected,
            limit_seconds=limit,
        )
    rows_per_sec = float(report.get("rows_per_sec", 0.0))
    if min_rows_per_sec is not None and rows_per_sec < float(min_rows_per_sec):
        raise MymlfwError(
            "SCALE_TOO_SLOW",
            "Throughput is below the caller's minimum.",
            rows_per_sec=rows_per_sec,
            min_rows_per_sec=float(min_rows_per_sec),
        )
    return report


def uniform_log_prior(n_classes: int) -> np.ndarray:
    return np.full(n_classes, np.log(1.0 / n_classes))
