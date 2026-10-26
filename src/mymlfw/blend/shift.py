"""Train-versus-test shift check using histogram gradient boosting."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

from mymlfw.errors import MymlfwError


def _matrix(train: pd.DataFrame, test: pd.DataFrame, numeric_cols, text_col: str | None):
    frames = []
    names = list(numeric_cols)
    for frame in (train, test):
        cols = [frame[col].astype(float).to_numpy() for col in numeric_cols]
        if text_col and text_col in frame.columns:
            cols.append(frame[text_col].fillna("").astype(str).str.len().to_numpy().astype(float))
        frames.append(np.column_stack(cols))
    if text_col:
        names.append(text_col + "_length")
    matrix = np.vstack(frames)
    labels = np.concatenate([np.zeros(len(train)), np.ones(len(test))])
    return matrix, labels, names


def _oof_scores(matrix: np.ndarray, labels: np.ndarray) -> np.ndarray:
    labels = np.asarray(labels).astype(int)
    counts = np.bincount(labels)
    present = counts[counts > 0]
    minority = int(present.min()) if len(present) else 0
    n_splits = min(5, minority)
    if n_splits < 2:
        raise MymlfwError(
            "SHIFT_SAMPLE",
            "Need at least two rows on each side of the shift check.",
            minority=minority,
        )
    scores = np.zeros(len(labels), dtype=float)
    splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
    for train_idx, val_idx in splitter.split(matrix, labels):
        model = HistGradientBoostingClassifier(max_depth=2, max_iter=20, learning_rate=0.1, random_state=0)
        model.fit(matrix[train_idx], labels[train_idx])
        scores[val_idx] = model.predict_proba(matrix[val_idx])[:, 1]
    return scores


def check_shift(train, test, numeric_cols, text_col: str | None = None, threshold: float = 0.65) -> dict:
    train = train if isinstance(train, pd.DataFrame) else pd.read_csv(train)
    test = test if isinstance(test, pd.DataFrame) else pd.read_csv(test)
    matrix, labels, names = _matrix(train, test, numeric_cols, text_col)
    scores = _oof_scores(matrix, labels)
    auc = float(roc_auc_score(labels, scores))
    n_train = len(train)
    drift = np.abs(matrix[:n_train].mean(axis=0) - matrix[n_train:].mean(axis=0))
    order = np.argsort(-drift)
    top = [names[int(index)] for index in order[:5]]
    if auc > threshold:
        raise MymlfwError(
            "SHIFT_DETECTED",
            "Weight or group folds toward the test distribution.",
            auc=auc,
            top_features=top,
        )
    return {"auc": auc, "top_features": top}
