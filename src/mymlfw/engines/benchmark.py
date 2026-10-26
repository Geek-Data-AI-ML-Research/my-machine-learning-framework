"""Score a JSONL benchmark with a caller-supplied function."""

from __future__ import annotations

import json
from pathlib import Path


class BenchmarkEngine:
    def prepare(self, frame):
        return frame

    def load_items(self, path) -> list[dict]:
        rows = []
        for line in Path(path).read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def run(self, path, scorer) -> list:
        return [scorer(item) for item in self.load_items(path)]
