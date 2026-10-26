import hashlib
import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from mymlfw.engines import (
    AgentZipEngine,
    BenchmarkEngine,
    PortfolioEngine,
    RankedCandidateEngine,
    TextBlendEngine,
)
from mymlfw.errors import MymlfwError


def test_text_engine_keeps_ids_and_sorts_by_length(tmp_path):
    engine = TextBlendEngine()
    frame = pd.DataFrame({"id": ["a", "b", "c"], "text": ["hi", np.nan, "z"]})

    def predict(row):
        if row["text"] == "[empty]":
            raise RuntimeError("bad row")
        return np.log([0.2, 0.8])

    bundle = engine.run(frame, predict, ["no", "yes"], record_path=tmp_path / "sanitized_rows.json")
    assert bundle.ids.tolist() == ["a", "b", "c"]
    assert engine.call_order_ == ["c", "a", "b"]
    assert json.loads((tmp_path / "sanitized_rows.json").read_text())["ids"] == ["b"]


def test_ranked_engine_scores_mrr():
    engine = RankedCandidateEngine(max_k=3)
    frame = engine.run([
        {"id": "1", "scores": {"good": 0.2, "best": 0.9, "mid": 0.4}},
    ])
    assert frame.loc[0, "candidates"].split(";")[0] == "best"
    assert engine.score(frame, ["best"]) == 1.0


def test_agent_zip_refuses_host_code(tmp_path):
    directory = tmp_path / "agent"
    directory.mkdir()
    (directory / "run.py").write_text("print(1)\n")
    try:
        AgentZipEngine().package(directory, tmp_path / "bad.zip")
    except MymlfwError as exc:
        assert exc.error_code == "HOST_CODE"
    else:
        raise AssertionError("host code was packed")
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "model_pin.txt").write_text("gemma\n")
    (clean / "agent.yaml").write_text("name: agent\n")
    packed = AgentZipEngine().package(clean, tmp_path / "ok.zip", model_pin="gemma")
    assert "agent.yaml" in packed["members"]


def test_portfolio_requires_a_matching_receipt(tmp_path):
    good = tmp_path / "good.txt"
    bad = tmp_path / "bad.txt"
    good.write_text("pass")
    bad.write_text("fail")
    digest = hashlib.sha256(good.read_bytes()).hexdigest()
    packed = PortfolioEngine().package(
        [
            {"path": good, "receipt_sha256": digest},
            {"path": bad, "receipt_sha256": "0" * 64},
        ],
        tmp_path / "portfolio.zip",
    )
    assert packed["members"] == ["good.txt"]
    first = tmp_path / "a" / "good.txt"
    second = tmp_path / "b" / "good.txt"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("one")
    second.write_text("two")
    members = [
        {"path": path, "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (first, second)
    ]
    with pytest.raises(MymlfwError) as error:
        PortfolioEngine().package(members, tmp_path / "collide.zip")
    assert error.value.error_code == "DUPLICATE_MEMBER"


def test_benchmark_engine_applies_the_scorer(tmp_path):
    path = tmp_path / "items.jsonl"
    path.write_text('{"id": 1}\n{"id": 2}\n')
    scores = BenchmarkEngine().run(path, lambda item: item["id"] * 2)
    assert scores == [2, 4]


def test_importing_engines_does_not_import_lora():
    script = "import sys, mymlfw.engines; assert 'mymlfw.train.lora' not in sys.modules"
    subprocess.check_call([sys.executable, "-c", script])
