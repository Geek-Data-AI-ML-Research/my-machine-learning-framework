"""Section 1: SQLite memory store."""

from __future__ import annotations

import subprocess
import sys

import pytest

from mymlfw.errors import MymlfwError
from mymlfw.rag.store import Store
from mymlfw.scaffold import list_recipes, remember


def test_journal_mode_is_wal_and_fts_keeps_lora_token(tmp_path):
    store = Store(tmp_path / "memory.db")
    try:
        assert store.journal_mode() == "wal"
        store.upsert_chunk(
            {
                "chunk_id": "note:1",
                "source_path": "note",
                "chunk_type": "field_note",
                "outcome_weight": 1.0,
                "meta_text": "try lora_r=64 tonight",
                "body_text": "other words",
            }
        )
        assert store.match_fts('"lora_r=64"') == ["note:1"]
    finally:
        store.close()


def test_remember_dedupes_and_list_recipes_finds_the_note(tmp_path):
    db = tmp_path / "memory.db"
    rule = "Use grad_checkpointing and batch_size=2 when max_len > 1536 on T4"
    first = remember("deberta,vram,kaggle-t4", rule, "exp_014", db=db)
    assert first["status"] == "remembered"
    again = remember("vram,deberta,kaggle-t4", rule, "exp_099", db=db)
    assert again["status"] == "duplicate"
    store = Store(db)
    try:
        rows = store.field_notes()
    finally:
        store.close()
    assert len(rows) == 1
    assert rows[0]["evidence"] == "exp_014"
    assert rows[0]["tags"] == "deberta,kaggle-t4,vram"
    found = list_recipes("deberta", notes_path=db)
    assert any(card["id"] == "field-note" and "grad_checkpointing" in card["summary"] for card in found)


def test_reopen_restores_the_field_note_from_the_dump(tmp_path):
    db = tmp_path / "memory.db"
    remember("cv", "fit temperature out of fold", "exp_001", db=db)
    db.unlink()
    for suffix in ("-wal", "-shm"):
        extra = db.parent / f"{db.name}{suffix}"
        if extra.exists():
            extra.unlink()
    store = Store(db)
    try:
        rows = store.field_notes()
    finally:
        store.close()
    assert len(rows) == 1
    assert rows[0]["rule"] == "fit temperature out of fold"


def test_auto_advise_insert_is_refused(tmp_path):
    store = Store(tmp_path / "memory.db")
    try:
        with pytest.raises(MymlfwError) as error:
            store.add_episode(
                contest="casmi",
                task="advise",
                actions="wired",
                outcome="worked",
                lesson="no",
                source="auto_advise",
            )
        assert error.value.error_code == "AUTO_ADVISE_FORBIDDEN"
        assert store.episodes() == []
    finally:
        store.close()


def test_importing_the_store_does_not_load_train_or_engines():
    script = (
        "import sys, mymlfw.rag.store; "
        "assert 'mymlfw.train.lora' not in sys.modules; "
        "assert 'mymlfw.engines' not in sys.modules"
    )
    subprocess.check_call([sys.executable, "-c", script])
