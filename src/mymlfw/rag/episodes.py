"""Episode log on top of the SQLite store."""

from __future__ import annotations

import json
from pathlib import Path

from mymlfw.errors import MymlfwError
from mymlfw.rag.analyze import load_frames
from mymlfw.rag.index import episode_chunk, expand_query, retrieve
from mymlfw.rag.store import Store
from mymlfw.scaffold import _normalize_tags


def parse_supersedes(value) -> int | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if text.startswith("ep_"):
        text = text[3:]
    if not text.isdigit():
        raise MymlfwError("BAD_EPISODE", "Pass --supersedes as an episode id.", value=str(value))
    return int(text)


def add_episode(
    contest: str,
    task: str,
    actions: str,
    outcome: str,
    lesson: str,
    evidence: str = "",
    tags: str = "",
    supersedes=None,
    db=None,
) -> dict:
    store = Store(db)
    try:
        result = store.add_episode(
            contest=contest,
            task=task,
            actions=actions,
            outcome=outcome,
            lesson=lesson,
            evidence=evidence,
            tags=",".join(_normalize_tags(tags)),
            source="agent",
            supersedes=parse_supersedes(supersedes),
        )
        if result["status"] == "added":
            row = next(item for item in store.episodes() if item["id"] == result["id"])
            store.upsert_chunk(episode_chunk(row, "recipes/EPISODES.jsonl"))
            for older in store.episodes():
                if older.get("superseded_by"):
                    store.upsert_chunk(episode_chunk(older, "recipes/EPISODES.jsonl"))
        return result
    finally:
        store.close()


def recall(task: str, db=None, data_dir=None) -> dict:
    store = Store(db) if db else Store()
    try:
        train = None
        if data_dir:
            train, _test = load_frames(Path(data_dir))
        query = expand_query(task, train) if train is not None else task
        found = retrieve(store, query)
        episodes = [
            item
            for item in list(found["negative"]) + list(found["positive"])
            if item["chunk_type"] == "episode"
        ]
        episodes.sort(key=lambda item: (-float(item["score"]), str(item["chunk_id"])))
        return {"query": found["query"], "episodes": episodes}
    finally:
        store.close()


def recall_text(task: str, db=None, data_dir=None) -> str:
    found = recall(task, db=db, data_dir=data_dir)
    payload = []
    for item in found["episodes"]:
        episode_id = str(item["chunk_id"]).split(":", 1)[-1]
        payload.append(
            {
                "id": int(episode_id) if episode_id.isdigit() else episode_id,
                "lesson": item["body_text"],
                "score": item["score"],
            }
        )
    return json.dumps({"episodes": payload})
