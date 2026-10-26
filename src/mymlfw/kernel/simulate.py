"""Project hidden-test runtime from a 1% timing hook. Tests pass the hook."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def simulate_test(train, rows: int, timing_hook, out_path, sample_fraction: float = 0.01) -> dict:
    frame = train if isinstance(train, pd.DataFrame) else pd.read_csv(train)
    n_sample = max(1, int(round(rows * sample_fraction)))
    sample_seconds, peak = timing_hook(n_sample, frame)
    projected = float(sample_seconds) / float(sample_fraction)
    report = {
        "peak_memory_gb": float(peak) if peak is not None else None,
        "projected_seconds": projected,
        "rows": int(rows),
        "rows_per_sec": float(rows) / projected if projected else 0.0,
        "sample_rows": n_sample,
        "sample_seconds": float(sample_seconds),
    }
    Path(out_path).write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return report
