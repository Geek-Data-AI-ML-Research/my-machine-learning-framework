"""Section 6: read-only analyzer."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pandas as pd

from mymlfw.paths import repo_root
from mymlfw.rag.advise import advise
from mymlfw.rag.analyze import analyze
from mymlfw.rag.episodes import add_episode
from mymlfw.rag.ingest import ingest
from mymlfw.rag.store import Store
from mymlfw.scaffold import token_count

LOSS = '''
class FocalCosineLoss:
    """handles extreme class imbalance"""

    def __init__(self, gamma=2.0):
        self.gamma = gamma
'''

HEADER = [
    "date",
    "experiment_id",
    "baseline_id",
    "variable",
    "change_count",
    "cv_mean",
    "cv_std",
    "cv_delta",
    "expected_band_low",
    "expected_band_high",
    "public_score",
    "cv_lb_gap",
    "artifact_sha256",
    "verdict",
    "note",
]


def _ledger(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        for row in rows:
            full = {name: "" for name in HEADER}
            full.update(row)
            writer.writerow(full)


def _kill(index: int, variable: str, note: str) -> dict:
    return {
        "date": f"2026-01-{index:02d}",
        "experiment_id": f"exp_{index}",
        "baseline_id": "base",
        "variable": variable,
        "change_count": "1",
        "cv_mean": "0.40",
        "cv_delta": "-0.01",
        "verdict": "kill",
        "note": note,
    }


def _train(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "id,text,group,label\n"
        "1,hello there friend,a,yes\n"
        "2,another note here,a,no\n"
        "3,third sample text,b,yes\n"
        "4,fourth sample text,b,no\n"
    )


def _engine(path: Path, class_name: str) -> None:
    path.write_text(
        f"from mymlfw.engines import {class_name}\n\n"
        f"class ContestEngine({class_name}):\n"
        "    pass\n"
    )


def _focal(db: Path, root: Path) -> None:
    external = root / "external"
    external.mkdir()
    (external / "loss.py").write_text(LOSS)
    ingest(external, mode="repo", db=db)


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_eight_kills_keep_one_warning_and_focal(tmp_path):
    contest = tmp_path / "casmi"
    rows = [_kill(index, f"var_{index}", f"stop {index}") for index in range(1, 9)]
    _ledger(contest / "ledger" / "experiments.csv", rows)
    _train(contest / "data" / "train.csv")
    _engine(contest / "engine.py", "PortfolioEngine")
    db = tmp_path / "memory.db"
    _focal(db, tmp_path)
    add_episode("casmi", "old blend", "pool", "failed", "the blend leaked the fold", db=db)
    add_episode("casmi", "new head", "swap", "worked", "raise the head", evidence="fresh_head", tags="fresh_head", db=db)
    report = analyze(contest, db=db, task="imbalance fresh_head")
    texts = [step["text"] for step in report["next_steps"]]
    assert len(texts) == 5
    assert texts[0] == "Do not repeat var_8. stop 8"
    assert "var_1" not in " ".join(texts)
    assert "Do not repeat this task. the blend leaked the fold" in texts
    assert "The profile matches grouped-text. The tree engine does not." in texts
    assert any("FocalCosineLoss" in text and "Do not copy the external file." in text for text in texts)
    assert "A previous task that worked: raise the head" in texts


def test_missing_ledger_does_not_invent_a_kill(tmp_path):
    contest = tmp_path / "casmi"
    contest.mkdir()
    report = analyze(contest, db=tmp_path / "memory.db")
    texts = [step["text"] for step in report["next_steps"]]
    assert any("probe register" in text for text in texts)
    assert not any(text.startswith("Do not repeat ") for text in texts)


def test_plateau_and_pending_leave_room_for_the_pattern(tmp_path):
    contest = tmp_path / "casmi"
    _ledger(
        contest / "ledger" / "experiments.csv",
        [
            {
                "date": "2026-01-01",
                "experiment_id": "exp_1",
                "variable": "lr",
                "cv_mean": "0.5",
                "cv_delta": "0",
                "verdict": "promote-candidate",
                "note": "flat",
            },
            {
                "date": "2026-01-02",
                "experiment_id": "exp_2",
                "variable": "warmup",
                "cv_mean": "0.5",
                "cv_delta": "0",
                "verdict": "promote-candidate",
                "note": "still flat",
            },
        ],
    )
    db = tmp_path / "memory.db"
    _focal(db, tmp_path)
    report = analyze(contest, db=db, task="FocalCosineLoss imbalance")
    assert report["plateau"] is True
    assert "stagnant score after warmup" in report["query"]
    code = next(step for step in report["next_steps"] if "FocalCosineLoss" in step["text"])
    assert "stagnant score after warmup" in code["why"]

    pending = tmp_path / "pending"
    rows = [_kill(index, f"var_{index}", f"stop {index}") for index in range(1, 9)]
    rows.append(
        {
            "date": "2026-02-01",
            "experiment_id": "exp_9",
            "variable": "still_open",
            "verdict": "pending",
            "note": "running",
        }
    )
    _ledger(pending / "ledger" / "experiments.csv", rows)
    _train(pending / "data" / "train.csv")
    _engine(pending / "engine.py", "PortfolioEngine")
    add_episode("pending", "old blend", "pool", "failed", "the blend leaked the fold", db=db)
    add_episode("pending", "new head", "swap", "worked", "raise the head", evidence="fresh_head", tags="fresh_head", db=db)
    held = analyze(pending, db=db, task="imbalance")
    joined = " ".join(step["text"] for step in held["next_steps"])
    assert any("pending" in gap for gap in held["gaps"])
    assert "FocalCosineLoss" in joined
    assert "Finish the pending probe" not in joined


def test_parquet_kernel_and_engine_paths(tmp_path):
    contest = tmp_path / "casmi"
    data = contest / "data"
    data.mkdir(parents=True)
    pd.DataFrame({"id": [1, 2], "label": ["a", "b"]}).to_parquet(data / "train.parquet")
    (contest / "kernel").mkdir()
    (contest / "kernel" / "kernel-metadata.json").write_text("{}\n")
    _engine(contest / "engine_mymlfw.py", "TextBlendEngine")
    report = analyze(contest, db=tmp_path / "memory.db")
    assert report["structure"]["train"].endswith("data/train.parquet")
    assert report["structure"]["features"]["has_label"] is True
    assert report["structure"]["kernel"].endswith("kernel/kernel-metadata.json")
    assert report["structure"]["engine"].endswith("engine_mymlfw.py")


def test_ast_does_not_import_engines(tmp_path):
    path = tmp_path / "engine.py"
    _engine(path, "RankedCandidateEngine")
    script = (
        "import sys\n"
        "from mymlfw.rag.analyze import engine_classes\n"
        "assert 'mymlfw.engines' not in sys.modules\n"
        "assert 'mymlfw.train.lora' not in sys.modules\n"
        f"names = engine_classes(__import__('pathlib').Path({str(path)!r}))\n"
        "assert 'RankedCandidateEngine' in names\n"
        "assert 'mymlfw.engines' not in sys.modules\n"
    )
    subprocess.check_call([sys.executable, "-c", script])


def test_grouped_text_mismatch(tmp_path):
    contest = tmp_path / "casmi"
    _train(contest / "data" / "train.csv")
    _engine(contest / "engine.py", "PortfolioEngine")
    report = analyze(contest, db=tmp_path / "memory.db")
    assert any(step["text"] == "The profile matches grouped-text. The tree engine does not." for step in report["next_steps"])


def test_known_variable_is_dropped(tmp_path):
    contest = tmp_path / "casmi"
    _ledger(
        contest / "ledger" / "experiments.csv",
        [_kill(1, "bc_shape", "already tried")],
    )
    db = tmp_path / "memory.db"
    store = Store(db)
    try:
        store.add_field_note("bc_shape", "keep the bc_shape penalty", evidence="bc_shape")
    finally:
        store.close()
    add_episode("casmi", "new head", "swap", "worked", "raise the head", evidence="fresh_head", tags="fresh_head", db=db)
    add_episode("other", "launch", "wait", "worked", "orbital chemistry boilerplate", evidence="", tags="", db=db)
    report = analyze(contest, db=db, task="fresh_head raise the head")
    joined = " ".join(step["text"] for step in report["next_steps"])
    assert "bc_shape penalty" not in joined
    assert "raise the head" in joined
    assert "orbital chemistry boilerplate" not in joined


def test_assignment_variables_and_schema_diff(tmp_path):
    contest = tmp_path / "casmi"
    _ledger(
        contest / "ledger" / "experiments.csv",
        [_kill(1, "lora_r=64", "already tried")],
    )
    (contest / "data").mkdir(parents=True)
    (contest / "data" / "train.csv").write_text("id,text,label\n1,hello there friend,a\n2,another note here,b\n")
    (contest / "data" / "test.csv").write_text("id,text\n3,hello there friend\n")
    db = tmp_path / "memory.db"
    store = Store(db)
    try:
        store.add_field_note("lora_r=64", "do not raise lora_r again", evidence="lora_r=64")
    finally:
        store.close()
    add_episode("casmi", "new head", "swap", "worked", "raise the head", evidence="fresh_head", tags="fresh_head", db=db)
    report = analyze(contest, db=db, task="fresh_head raise the head")
    joined = " ".join(step["text"] for step in report["next_steps"])
    assert "do not raise lora_r again" not in joined
    assert "raise the head" in joined
    assert "check_shift" in report["query"]


def test_analyze_writes_nothing_in_the_contest(tmp_path):
    contest = tmp_path / "casmi"
    contest.mkdir()
    (contest / "README.md").write_text("stay\n")
    db = tmp_path / "memory.db"
    before_files = sorted(path.relative_to(contest).as_posix() for path in contest.rglob("*"))
    store = Store(db)
    try:
        before_episodes = len(store.episodes())
    finally:
        store.close()
    out = tmp_path / "steps.md"
    analyze(contest, db=db, out=out)
    after_files = sorted(path.relative_to(contest).as_posix() for path in contest.rglob("*"))
    assert after_files == before_files
    assert not (contest / ".git").exists()
    assert out.read_text().startswith("# NEXT STEPS")
    store = Store(db)
    try:
        assert len(store.episodes()) == before_episodes
    finally:
        store.close()


def test_advise_next_steps_see_source_data(tmp_path):
    repo = tmp_path / "casmi"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "README.md").write_text("# contest\n")
    _git(repo, "add", "README.md")
    _git(repo, "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-m", "initial")
    data = repo / "data"
    data.mkdir()
    pd.DataFrame({"id": [1]}).to_parquet(data / "train.parquet")
    pd.DataFrame({"id": [2]}).to_parquet(data / "test.parquet")
    db = tmp_path / "memory.db"
    store = Store(db)
    try:
        before = len(store.episodes())
    finally:
        store.close()
    result = advise(repo, db=db, task="ranking")
    text = (Path(result["worktree_dir"]) / "docs" / "MYMLFW_ADVICE.md").read_text()
    assert "# NEXT STEPS" in text
    assert "engine file is missing" not in text
    assert "data/train.parquet is missing" not in text
    assert text.index("# NEXT STEPS") < text.index("episode add")
    store = Store(db)
    try:
        assert len(store.episodes()) == before
    finally:
        store.close()


def test_llms_lists_analyze():
    text = (repo_root() / "llms.txt").read_text()
    packaged = (Path(__file__).resolve().parents[1] / "src" / "mymlfw" / "resources" / "llms.txt").read_text()
    assert "python -m mymlfw analyze" in text
    assert "from mymlfw.rag.analyze import analyze" in text
    assert token_count(text) <= 1500
    assert "DO NOT write custom GroupKFold loops; call mymlfw.cv.run_oof." in text
    assert text == packaged
