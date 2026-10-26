"""Section 5: advise writes a worktree and leaves the checkout alone."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from mymlfw.errors import MymlfwError
from mymlfw.paths import repo_root, resolve_data_dir
from mymlfw.rag.advise import ENGINE_NAMES, advise, clean
from mymlfw.rag.ingest import ingest
from mymlfw.rag.store import Store
from mymlfw.scaffold import token_count

LOSS = '''
class FocalCosineLoss:
    """handles extreme class imbalance"""

    def __init__(self, gamma=2.0):
        self.gamma = gamma
'''


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _commit(cwd, message="initial"):
    _git(
        cwd,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "--allow-empty",
        "-m",
        message,
    )


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    (path / "README.md").write_text("# contest\n")
    (path / "bin").mkdir()
    (path / "bin" / "keep").write_text("ok\n")
    _git(path, "add", "README.md", "bin/keep")
    _commit(path)
    return path


def _parquet(path: Path) -> None:
    frame = pd.DataFrame({"id": [1]})
    holdout = pd.DataFrame({"id": [2]})
    data = path / "data"
    data.mkdir()
    frame.to_parquet(data / "train.parquet")
    holdout.to_parquet(data / "test.parquet")


def test_git_guards(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(MymlfwError) as missing:
        advise(plain, db=tmp_path / "memory.db")
    assert missing.value.error_code == "GIT_REQUIRED"
    assert not list(tmp_path.glob("plain-advise-*"))

    unborn = tmp_path / "unborn"
    unborn.mkdir()
    _git(unborn, "init")
    with pytest.raises(MymlfwError) as empty:
        advise(unborn, db=tmp_path / "empty.db")
    assert empty.value.error_code == "GIT_NO_COMMITS"
    assert empty.value.suggested_fix == "git commit -m 'initial'"

    dirty = _repo(tmp_path / "dirty")
    (dirty / "README.md").write_text("# edited\n")
    with pytest.raises(MymlfwError) as edited:
        advise(dirty, db=tmp_path / "dirty.db")
    assert edited.value.error_code == "DIRTY_TREE"

    fresh = _repo(tmp_path / "fresh")
    _parquet(fresh)
    result = advise(fresh, db=tmp_path / "fresh.db", task="ranking id")
    assert result["status"] == "ok"


def test_advice_brief_and_engine(tmp_path):
    repo = _repo(tmp_path / "casmi")
    _parquet(repo)
    external = tmp_path / "other"
    external.mkdir()
    (external / "loss.py").write_text(LOSS)
    db = tmp_path / "memory.db"
    ingest(external, mode="repo", db=db)
    before = Store(db)
    try:
        episode_count = before.conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    finally:
        before.close()
    result = advise(repo, db=db, task="FocalCosineLoss extreme class imbalance")
    payload = json.loads(json.dumps(result))
    assert payload["engine_class"] in ENGINE_NAMES
    assert payload["top_recipe"] == "ranking"
    text = (Path(payload["worktree_dir"]) / "docs" / "MYMLFW_ADVICE.md").read_text()
    for heading in (
        "# MYMLFW RAG Advice Brief",
        "## 1. DO NOT REPEAT (Retrieved Traps & Failed Episodes)",
        "## 2. RECOMMENDED PLAYBOOK (Retrieved Wins & Recipes)",
        "## 3. LEARNED PATTERNS FROM OTHER PROJECTS",
        "## 4. CANDIDATE FILES TO INSPECT (Untouched by Advise)",
    ):
        assert heading in text
    assert "<retrieved_note" in text and "</retrieved_note>" in text
    assert "episode add" in text
    assert "advise run worked" not in text
    assert "Adapt this pattern in the contest; do not copy the external file." in text
    assert "FocalCosineLoss" in text
    after = Store(db)
    try:
        assert after.conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == episode_count
    finally:
        after.close()
    assert not (Path(payload["worktree_dir"]) / "recipes" / "memory.db").exists()


def test_second_advise_and_clean(tmp_path):
    repo = _repo(tmp_path / "casmi")
    db = tmp_path / "memory.db"
    first = advise(repo, db=db, task="ranking")
    second = advise(repo, db=db, task="ranking")
    assert first["branch"] != second["branch"]
    assert Path(first["worktree_dir"]).is_dir()
    store = Store(db)
    try:
        sources = " ".join(chunk["source_path"] for chunk in store.chunks())
    finally:
        store.close()
    assert "advise-" not in sources
    short = first["branch"].rsplit("-", 1)[-1]
    clean(repo, short)
    assert not Path(first["worktree_dir"]).exists()
    branches = subprocess.check_output(["git", "branch"], cwd=repo, text=True)
    assert first["branch"] not in branches
    current = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, text=True).strip()
    assert current == "main"


def test_failed_write_rolls_back(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "casmi")

    def fail(*args, **kwargs):
        raise MymlfwError("WRITE_FAILED", "disk full")

    monkeypatch.setattr("mymlfw.rag.advise.write_tree", fail)
    with pytest.raises(MymlfwError):
        advise(repo, db=tmp_path / "memory.db")
    listed = subprocess.check_output(["git", "worktree", "list"], cwd=repo, text=True)
    assert str(repo) in listed
    assert "advise-" not in listed
    assert not list(tmp_path.glob("casmi-advise-*"))


def test_data_symlink_is_the_same_inode(tmp_path):
    repo = _repo(tmp_path / "casmi")
    _parquet(repo)
    original = repo / "data" / "train.parquet"
    mode = (repo / "data").stat().st_mode
    result = advise(repo, db=tmp_path / "memory.db", task="ranking")
    worktree = Path(result["worktree_dir"])
    resolved = resolve_data_dir(worktree)
    assert resolved == (repo / "data").resolve()
    linked = worktree / "data" / "train.parquet"
    assert original.stat().st_ino == linked.stat().st_ino
    assert (repo / "data").stat().st_mode == mode


def test_pyproject_edit_stays_valid(tmp_path):
    present = _repo(tmp_path / "present")
    (present / "pyproject.toml").write_text('[project]\nname = "demo"\ndependencies = ["mymlfw"]\n')
    _git(present, "add", "pyproject.toml")
    _commit(present, "deps")
    result = advise(present, db=tmp_path / "present.db", task="ranking")
    text = (Path(result["worktree_dir"]) / "pyproject.toml").read_text()
    assert text.count("mymlfw") == 1
    import tomllib

    tomllib.loads(text)

    missing = _repo(tmp_path / "missing")
    (missing / "pyproject.toml").write_text('[project]\nname = "demo"\ndependencies = ["numpy"]\n')
    _git(missing, "add", "pyproject.toml")
    _commit(missing, "deps")
    result = advise(missing, db=tmp_path / "missing.db", task="ranking")
    edited = (Path(result["worktree_dir"]) / "pyproject.toml").read_text()
    loaded = tomllib.loads(edited)
    assert loaded["project"]["dependencies"].count("mymlfw") == 1
    assert "numpy" in loaded["project"]["dependencies"]


def test_import_and_llms():
    script = (
        "import sys, mymlfw.rag; "
        "assert 'mymlfw.train.lora' not in sys.modules; "
        "assert 'mymlfw.engines' not in sys.modules"
    )
    subprocess.check_call([sys.executable, "-c", script])
    text = (repo_root() / "llms.txt").read_text()
    packaged = (Path(__file__).resolve().parents[1] / "src" / "mymlfw" / "resources" / "llms.txt").read_text()
    assert "python -m mymlfw advise" in text
    assert "from mymlfw.rag.advise import advise" in text
    assert "python -m mymlfw episode add" in text
    assert "python -m mymlfw ingest" in text
    assert token_count(text) <= 1500
    assert "DO NOT write custom GroupKFold loops; call mymlfw.cv.run_oof." in text
    assert text == packaged
