"""Compact data briefing for a contest directory."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from mymlfw.campaign.match import recommend_recipes

HEADINGS = [
    "rows",
    "columns",
    "id_candidates",
    "group_candidates",
    "target_balance",
    "text_length",
    "schema_diff",
]
TARGET_NAMES = ("target", "label", "model")
TEXT_NAMES = {"text", "code", "prompt", "content", "body", "query"}


def _read(directory: Path, name: str) -> pd.DataFrame | None:
    path = directory / name
    if not path.exists():
        return None
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _target_column(train: pd.DataFrame):
    return next((col for col in TARGET_NAMES if col in train.columns), None)


def _text_column(train: pd.DataFrame, column, target_col) -> bool:
    if column == target_col:
        return False
    series = train[column]
    if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
        return False
    name = str(column).lower()
    if name in TEXT_NAMES or name.endswith("_text"):
        return True
    lengths = series.fillna("").astype(str).str.len()
    return bool(len(lengths)) and float(lengths.median()) >= 8


def profile_features(train: pd.DataFrame) -> dict:
    """Fingerprint used by ``recommend_recipes``."""

    n = len(train)
    upper = n // 2
    id_cols = [col for col in train.columns if n > 0 and int(train[col].nunique(dropna=False)) == n]
    target_col = _target_column(train)
    group_cols = []
    for col in train.columns:
        if col in id_cols or col == target_col:
            continue
        cardinality = int(train[col].nunique(dropna=False))
        if 2 <= cardinality <= upper:
            group_cols.append(col)
    n_classes = None
    if target_col is not None and len(train):
        n_classes = int(train[target_col].nunique(dropna=False))
    return {
        "has_text_col": any(_text_column(train, col, target_col) for col in train.columns),
        "has_group_col": bool(group_cols),
        "n_classes": n_classes,
        "has_label": target_col is not None,
        "has_id_col": bool(id_cols),
        "id_cols": id_cols,
        "group_cols": group_cols,
        "target_col": target_col,
    }


def _clip_name(name) -> str:
    text = str(name)
    return text if len(text) <= 64 else text[:64]


def profile_frames(train: pd.DataFrame, test: pd.DataFrame | None = None) -> str:
    features = profile_features(train)
    n = len(train)
    id_cols = features["id_cols"]
    group_cols = [f"{_clip_name(col)} ({int(train[col].nunique(dropna=False))})" for col in features["group_cols"]]
    target_col = features["target_col"]
    balance = "none"
    if target_col is not None and len(train):
        counts = train[target_col].value_counts(dropna=False)
        ratio = float(counts.max() / max(int(counts.min()), 1))
        balance = f"{target_col} max/min={ratio:.4g} classes={len(counts)}"
    text_lines = []
    for col in train.columns:
        if col in id_cols:
            continue
        if not pd.api.types.is_object_dtype(train[col]) and not pd.api.types.is_string_dtype(train[col]):
            continue
        lengths = train[col].fillna("").astype(str).str.len()
        if lengths.max() == 0:
            continue
        quantiles = np.quantile(lengths.to_numpy(), [0.5, 0.95, 0.99])
        text_lines.append(
            f"{_clip_name(col)} p50={quantiles[0]:.4g} p95={quantiles[1]:.4g} p99={quantiles[2]:.4g}"
        )
    only_train, only_test = [], []
    if test is not None:
        only_train = sorted(_clip_name(col) for col in (set(train.columns) - set(test.columns)))
        only_test = sorted(_clip_name(col) for col in (set(test.columns) - set(train.columns)))
    sections = {
        "rows": f"train={n}" + (f" test={len(test)}" if test is not None else ""),
        "columns": ", ".join(_clip_name(col) for col in train.columns),
        "id_candidates": ", ".join(_clip_name(col) for col in id_cols) or "none",
        "group_candidates": ", ".join(group_cols) or "none",
        "target_balance": balance,
        "text_length": "\n".join(text_lines) or "none",
        "schema_diff": f"only_train={only_train} only_test={only_test}",
    }
    cards = recommend_recipes(features)
    if cards:
        recommended = "\n".join(f"- {card['id']}: {card['summary']}" for card in cards)
    else:
        recommended = "none"
    parts = ["# DATA_PROFILE\n", f"## recommended\n{recommended}\n"]
    for heading in HEADINGS:
        parts.append(f"## {heading}\n{sections[heading]}\n")
    return "\n".join(parts)


def profile_dir(directory, out=None) -> Path:
    directory = Path(directory)
    if not (directory / "train.csv").exists() and not (directory / "train.parquet").exists():
        from mymlfw.paths import resolve_data_dir

        directory = resolve_data_dir(directory)
    train = _read(directory, "train.csv")
    if train is None:
        train = _read(directory, "train.parquet")
        if train is None:
            raise FileNotFoundError(f"no train.csv in {directory}")
    test = _read(directory, "test.csv")
    text = profile_frames(train, test)
    destination = Path(out) if out else directory / "DATA_PROFILE.md"
    destination.write_text(text)
    return destination
