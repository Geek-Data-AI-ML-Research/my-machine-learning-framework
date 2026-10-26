"""Ranked candidate lists scored with MRR."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mymlfw.metrics import mrr_at_k
from mymlfw.sanitize import prepare_frame


class RankedCandidateEngine:
    def __init__(self, max_k: int = 25):
        self.max_k = max_k

    def prepare(self, frame: pd.DataFrame, text_col: str = "text") -> pd.DataFrame:
        if text_col in frame.columns:
            return prepare_frame(frame, text_col=text_col)
        return frame.copy()

    def rank(self, candidate_scores: dict[str, float]) -> list[str]:
        ordered = sorted(candidate_scores, key=lambda name: (-candidate_scores[name], name))
        unique = []
        for name in ordered:
            if name not in unique:
                unique.append(name)
        return unique[: self.max_k]

    def run(self, rows: list[dict]) -> pd.DataFrame:
        records = []
        for row in rows:
            ranked = self.rank(row["scores"])
            records.append({"id": str(row["id"]), "candidates": ";".join(ranked)})
        return pd.DataFrame(records)

    def score(self, frame: pd.DataFrame, truths: list[str]) -> float:
        lists = [row.split(";") for row in frame["candidates"].tolist()]
        return mrr_at_k(lists, truths)
