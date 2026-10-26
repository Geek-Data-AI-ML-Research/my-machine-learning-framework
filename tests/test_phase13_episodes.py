"""Section 3: episode add and recall."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mymlfw.paths import repo_root
from mymlfw.rag.episodes import add_episode, recall_text
from mymlfw.rag.store import Store
from mymlfw.scaffold import token_count


def _add(db, outcome, lesson, supersedes=None, evidence="exp_014"):
    return add_episode(
        "casmi",
        "temperature scaling on the scored fold",
        "fit T",
        outcome,
        lesson,
        evidence=evidence,
        tags="blend,cv",
        supersedes=supersedes,
        db=db,
    )


def test_add_dumps_one_line_and_duplicate_does_not_grow(tmp_path):
    db = tmp_path / "memory.db"
    first = _add(db, "failed", "fitting T on the scored fold leaked")
    assert first["status"] == "added"
    dump = (tmp_path / "memory_dump.jsonl").read_text().splitlines()
    assert len(dump) == 1
    again = _add(db, "failed", "fitting T on the scored fold leaked")
    assert again["status"] == "duplicate"
    store = Store(db)
    try:
        assert len(store.episodes()) == 1
    finally:
        store.close()
    assert len((tmp_path / "memory_dump.jsonl").read_text().splitlines()) == 1


def test_supersede_ranks_the_worked_episode_first(tmp_path):
    db = tmp_path / "memory.db"
    failed = _add(db, "failed", "fitting T on the scored fold leaked")
    worked = _add(db, "worked", "nested temperature held the score", supersedes=failed["id"], evidence="exp_020")
    text = recall_text("temperature scaling on the scored fold", db=db)
    payload = json.loads(text)
    ids = [item["id"] for item in payload["episodes"]]
    assert ids.index(worked["id"]) < ids.index(failed["id"])


def test_recall_does_not_create_a_branch(tmp_path):
    db = tmp_path / "memory.db"
    _add(db, "failed", "fitting T on the scored fold leaked")
    text = recall_text("temperature scaling", db=db)
    assert "fitting T on the scored fold leaked" in text
    assert not (tmp_path / ".git").exists()


def test_reopen_restores_the_episode(tmp_path):
    db = tmp_path / "memory.db"
    _add(db, "failed", "fitting T on the scored fold leaked")
    db.unlink()
    for suffix in ("-wal", "-shm"):
        extra = Path(str(db) + suffix)
        if extra.exists():
            extra.unlink()
    store = Store(db)
    try:
        rows = store.episodes()
        chunks = store.chunks()
    finally:
        store.close()
    assert len(rows) == 1
    assert rows[0]["lesson"] == "fitting T on the scored fold leaked"
    assert any(rows[0]["lesson"] in chunk["body_text"] for chunk in chunks)


def test_llms_lists_episode_commands():
    text = (repo_root() / "llms.txt").read_text()
    assert "python -m mymlfw episode add" in text
    assert "python -m mymlfw episode recall" in text
    assert "from mymlfw.rag.episodes import add_episode" in text
    assert "from mymlfw.rag.episodes import recall" in text
    assert token_count(text) <= 1500
    assert "DO NOT write custom GroupKFold loops; call mymlfw.cv.run_oof." in text


def test_episode_cli_duplicate(tmp_path):
    db = tmp_path / "memory.db"
    command = [
        sys.executable, "-m", "mymlfw", "episode", "add",
        "--contest", "casmi", "--task", "blend", "--actions", "pool",
        "--outcome", "worked", "--lesson", "log probs", "--db", str(db),
    ]
    first = subprocess.run(command, check=False, capture_output=True, text=True)
    second = subprocess.run(command, check=False, capture_output=True, text=True)
    assert first.returncode == 0
    assert second.returncode == 0
    assert second.stdout.strip() == "duplicate"
