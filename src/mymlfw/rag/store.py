"""SQLite memory for episodes, field notes, and retrieved chunks."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mymlfw.errors import MymlfwError
from mymlfw.paths import checkout_root

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    contest TEXT NOT NULL,
    task TEXT NOT NULL,
    actions TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('worked', 'failed', 'partial')),
    lesson TEXT NOT NULL,
    evidence TEXT NOT NULL,
    tags TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'agent' CHECK (source IN ('agent', 'auto_advise')),
    superseded_by INTEGER REFERENCES episodes(id),
    UNIQUE(contest, task, lesson) ON CONFLICT IGNORE
);
CREATE TABLE IF NOT EXISTS field_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    tags TEXT NOT NULL,
    rule TEXT NOT NULL,
    evidence TEXT NOT NULL,
    UNIQUE(tags, rule) ON CONFLICT IGNORE
);
CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    outcome_weight REAL NOT NULL DEFAULT 1.0,
    meta_text TEXT NOT NULL,
    body_text TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    meta_text,
    body_text,
    tokenize = "porter unicode61 tokenchars '_@=-'"
);
CREATE TABLE IF NOT EXISTS ingested_files (
    file_path TEXT PRIMARY KEY,
    repo_root TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    chunk_count INTEGER NOT NULL
);
CREATE TRIGGER IF NOT EXISTS rag_chunks_ai AFTER INSERT ON rag_chunks BEGIN
    INSERT INTO rag_chunks_fts(chunk_id, meta_text, body_text)
    VALUES (new.chunk_id, new.meta_text, new.body_text);
END;
CREATE TRIGGER IF NOT EXISTS rag_chunks_ad AFTER DELETE ON rag_chunks BEGIN
    DELETE FROM rag_chunks_fts WHERE chunk_id = old.chunk_id;
END;
CREATE TRIGGER IF NOT EXISTS rag_chunks_au AFTER UPDATE ON rag_chunks BEGIN
    DELETE FROM rag_chunks_fts WHERE chunk_id = old.chunk_id;
    INSERT INTO rag_chunks_fts(chunk_id, meta_text, body_text)
    VALUES (new.chunk_id, new.meta_text, new.body_text);
END;
"""


def default_db_path() -> Path:
    root = checkout_root() or Path.cwd()
    return root / "recipes" / "memory.db"


def dump_path_for(db_path: Path) -> Path:
    return db_path.parent / "memory_dump.jsonl"


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_db_path()
        self.dump_path = dump_path_for(self.path)
        fresh = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        try:
            mode = self.conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise MymlfwError("FTS5_REQUIRED", "Use a SQLite build with FTS5.") from exc
        if str(mode).lower() != "wal":
            raise MymlfwError("FTS5_REQUIRED", "Use a SQLite build with FTS5.")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        try:
            self.conn.executescript(SCHEMA)
        except sqlite3.OperationalError as exc:
            if "fts5" in str(exc).lower():
                raise MymlfwError("FTS5_REQUIRED", "Use a SQLite build with FTS5.") from exc
            raise
        self.conn.commit()
        if fresh and self.dump_path.exists():
            self._replay()

    def close(self) -> None:
        self.conn.close()

    def journal_mode(self) -> str:
        return str(self.conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def _replay(self) -> None:
        for line in self.dump_path.read_text().splitlines():
            if line.strip():
                self._apply(json.loads(line), dump=False)
        self.conn.commit()

    def _append_dump(self, record: dict) -> None:
        with self.dump_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _apply(self, record: dict, dump: bool) -> dict:
        table = record["table"]
        op = record.get("op", "insert")
        row = record.get("row") or {}
        if table == "field_notes" and op == "insert":
            return self.add_field_note(
                row["tags"], row["rule"], row.get("evidence", ""), dump=dump, timestamp=row.get("timestamp")
            )
        if table == "episodes" and op == "insert":
            return self.add_episode(
                contest=row["contest"],
                task=row["task"],
                actions=row["actions"],
                outcome=row["outcome"],
                lesson=row["lesson"],
                evidence=row.get("evidence", ""),
                tags=row["tags"],
                source=row.get("source", "agent"),
                dump=dump,
                timestamp=row.get("timestamp"),
            )
        if table == "episodes" and op == "supersede":
            self.mark_superseded(int(record["id"]), int(record["by"]), dump=dump)
            return {"status": "superseded"}
        raise MymlfwError("BAD_DUMP", "The memory dump has a record this store cannot replay.", table=table)

    def add_field_note(self, tags: str, rule: str, evidence: str = "", dump: bool = True, timestamp: str | None = None) -> dict:
        stamp = timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO field_notes(timestamp, tags, rule, evidence) VALUES (?, ?, ?, ?)",
            (stamp, tags, rule, evidence),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            return {"status": "duplicate", "path": str(self.path)}
        if dump:
            self._append_dump(
                {
                    "op": "insert",
                    "row": {"evidence": evidence, "rule": rule, "tags": tags, "timestamp": stamp},
                    "table": "field_notes",
                }
            )
        self._index_note(int(cur.lastrowid))
        return {"status": "remembered", "path": str(self.path)}

    def field_notes(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, timestamp, tags, rule, evidence FROM field_notes ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

    def add_episode(
        self,
        contest: str,
        task: str,
        actions: str,
        outcome: str,
        lesson: str,
        evidence: str = "",
        tags: str = "",
        source: str = "agent",
        supersedes: int | None = None,
        dump: bool = True,
        timestamp: str | None = None,
    ) -> dict:
        if source == "auto_advise":
            raise MymlfwError(
                "AUTO_ADVISE_FORBIDDEN",
                "Record an episode with episode add after CV or preflight.",
            )
        stamp = timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")
        before = self.conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        try:
            self.conn.execute(
                """
                INSERT INTO episodes(
                    timestamp, contest, task, actions, outcome, lesson, evidence, tags, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (stamp, contest, task, actions, outcome, lesson, evidence, tags, source),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            if "unique" in str(exc).lower():
                found = self.conn.execute(
                    "SELECT id FROM episodes WHERE contest=? AND task=? AND lesson=?",
                    (contest, task, lesson),
                ).fetchone()
                return {
                    "status": "duplicate",
                    "id": int(found["id"]) if found else None,
                    "path": str(self.path),
                }
            raise MymlfwError(
                "BAD_EPISODE",
                "Use outcome worked, failed, or partial.",
            ) from exc
        after = self.conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        if after == before:
            found = self.conn.execute(
                "SELECT id FROM episodes WHERE contest=? AND task=? AND lesson=?",
                (contest, task, lesson),
            ).fetchone()
            return {"status": "duplicate", "id": int(found["id"]) if found else None, "path": str(self.path)}
        row_id = int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        if dump:
            self._append_dump(
                {
                    "op": "insert",
                    "row": {
                        "actions": actions,
                        "contest": contest,
                        "evidence": evidence,
                        "lesson": lesson,
                        "outcome": outcome,
                        "source": source,
                        "tags": tags,
                        "task": task,
                        "timestamp": stamp,
                    },
                    "table": "episodes",
                }
            )
        if supersedes is not None:
            self.mark_superseded(int(supersedes), row_id, dump=dump)
        if outcome == "worked":
            older = self.conn.execute(
                """
                SELECT id FROM episodes
                WHERE outcome='failed' AND tags=? AND evidence=? AND id!=? AND superseded_by IS NULL
                """,
                (tags, evidence, row_id),
            ).fetchall()
            for item in older:
                self.mark_superseded(int(item["id"]), row_id, dump=dump)
        self._index_episode(row_id)
        return {"status": "added", "id": row_id, "path": str(self.path)}

    def _index_note(self, note_id: int) -> None:
        from mymlfw.rag.index import note_chunk

        row = self.conn.execute("SELECT * FROM field_notes WHERE id=?", (note_id,)).fetchone()
        if row is not None:
            self.upsert_chunk(note_chunk(dict(row), "recipes/memory.db"))

    def _index_episode(self, episode_id: int) -> None:
        from mymlfw.rag.index import episode_chunk

        row = self.conn.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()
        if row is not None:
            self.upsert_chunk(episode_chunk(dict(row), "recipes/EPISODES.jsonl"))

    def mark_superseded(self, episode_id: int, by_id: int, dump: bool = True) -> None:
        self.conn.execute(
            "UPDATE episodes SET superseded_by=? WHERE id=? AND superseded_by IS NULL",
            (by_id, episode_id),
        )
        self.conn.commit()
        self._index_episode(episode_id)
        if dump:
            self._append_dump({"by": by_id, "id": episode_id, "op": "supersede", "table": "episodes"})

    def episodes(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM episodes ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def replace_chunks(self, source_path: str, chunks: list[dict]) -> None:
        self.conn.execute("DELETE FROM rag_chunks WHERE source_path=?", (source_path,))
        for chunk in chunks:
            self.conn.execute(
                """
                INSERT INTO rag_chunks(chunk_id, source_path, chunk_type, outcome_weight, meta_text, body_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk["chunk_id"],
                    source_path,
                    chunk["chunk_type"],
                    float(chunk.get("outcome_weight", 1.0)),
                    chunk["meta_text"],
                    chunk["body_text"],
                ),
            )
        self.conn.commit()

    def upsert_chunk(self, chunk: dict) -> None:
        self.conn.execute("DELETE FROM rag_chunks WHERE chunk_id=?", (chunk["chunk_id"],))
        self.conn.execute(
            """
            INSERT INTO rag_chunks(chunk_id, source_path, chunk_type, outcome_weight, meta_text, body_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chunk["chunk_id"],
                chunk["source_path"],
                chunk["chunk_type"],
                float(chunk.get("outcome_weight", 1.0)),
                chunk["meta_text"],
                chunk["body_text"],
            ),
        )
        self.conn.commit()

    def delete_source(self, source_path: str) -> None:
        self.conn.execute("DELETE FROM rag_chunks WHERE source_path=?", (source_path,))
        self.conn.execute("DELETE FROM ingested_files WHERE file_path=?", (source_path,))
        self.conn.commit()

    def chunks(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT chunk_id, source_path, chunk_type, outcome_weight, meta_text, body_text FROM rag_chunks ORDER BY chunk_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def match_fts(self, match: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT rag_chunks.chunk_id
            FROM rag_chunks_fts
            JOIN rag_chunks ON rag_chunks.chunk_id = rag_chunks_fts.chunk_id
            WHERE rag_chunks_fts MATCH ?
            """,
            (match,),
        ).fetchall()
        return [row["chunk_id"] for row in rows]

    def bm25(self, match: str) -> list[tuple[str, float]]:
        if not match.strip():
            return []
        try:
            rows = self.conn.execute(
                """
                SELECT rag_chunks.chunk_id AS chunk_id,
                       bm25(rag_chunks_fts, 0.0, 2.0, 1.0) * rag_chunks.outcome_weight AS score
                FROM rag_chunks_fts
                JOIN rag_chunks ON rag_chunks.chunk_id = rag_chunks_fts.chunk_id
                WHERE rag_chunks_fts MATCH ?
                ORDER BY score ASC, rag_chunks.chunk_id ASC
                """,
                (match,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(row["chunk_id"], float(row["score"])) for row in rows]
