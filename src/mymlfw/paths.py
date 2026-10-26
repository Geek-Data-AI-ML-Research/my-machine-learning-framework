"""Resolve Kaggle input trees, local contest directories, and the checkout root."""

from __future__ import annotations

import os
from pathlib import Path

from mymlfw.errors import MymlfwError


def checkout_root() -> Path | None:
    """Source checkout, when this file lives inside one."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").exists() and (candidate / "llms.txt").exists():
            return candidate
    return None


def packaged_root() -> Path | None:
    """Recipes and llms.txt shipped inside the installed package."""
    root = Path(__file__).resolve().parent / "resources"
    if (root / "llms.txt").is_file() and (root / "recipes").is_dir():
        return root
    return None


def repo_root() -> Path:
    found = checkout_root()
    if found is not None:
        return found
    packaged = packaged_root()
    if packaged is not None:
        return packaged
    raise MymlfwError(
        "REPO_ROOT",
        "Run this from an editable checkout that contains llms.txt.",
    )


def _data_file(path: Path, name: str) -> bool:
    if (path / name).exists():
        return True
    stem = Path(name).stem
    return (path / f"{stem}.parquet").exists()


def find_data_dir(candidates, required=("train.csv", "test.csv")) -> Path:
    for candidate in candidates:
        path = Path(candidate)
        if path.is_dir() and all(_data_file(path, name) for name in required):
            return path
    raise MymlfwError(
        "DATA_DIR_NOT_FOUND",
        "Pass a directory that contains the expected files.",
        required=list(required),
    )


def resolve_data_dir(local, required=("train.csv", "test.csv")) -> Path:
    local = Path(local)
    candidates = []
    override = os.environ.get("MYMLFW_DATA_DIR")
    if override:
        candidates.append(Path(override))
    marker = local / ".mymlfw" / "data_dir"
    if marker.is_file():
        recorded = marker.read_text().strip()
        if recorded:
            candidates.append(Path(recorded))
    candidates.append(local / "data")
    kaggle = Path("/kaggle/input")
    if kaggle.is_dir():
        candidates.append(kaggle)
        candidates.extend(sorted(path for path in kaggle.iterdir() if path.is_dir()))
    candidates.append(local)
    return find_data_dir(candidates, required)
