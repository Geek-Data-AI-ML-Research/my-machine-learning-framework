"""Typed chunks and the field-weighted retrieval rank."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from mymlfw.campaign.profile import profile_features
from mymlfw.campaign.match import recommend_recipes
from mymlfw.rag.store import Store

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "build", "dist"}
RAW_TABLES = {"train.csv", "test.csv", "train.parquet", "test.parquet"}
SKIP_SUFFIXES = {".pt", ".bin", ".safetensors", ".npz", ".pem"}
MAX_BYTES = 256_000
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
HEADING = re.compile(r"^(#{1,3}) (.+)$")
TOKEN = re.compile(r"[A-Za-z0-9_@=\-]{2,}")
TRAP_VERDICTS = {"kill", "confirmed-large-gap"}


def clean_text(value) -> str:
    return CONTROL.sub("", str(value or ""))


def _chunk_id(*parts) -> str:
    raw = "\n".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def ledger_chunks(text: str, contest: str, source_path: str) -> list[dict]:
    chunks = []
    for row in csv.DictReader(io.StringIO(text)):
        verdict = (row.get("verdict") or "").strip()
        if verdict == "pending" or not row.get("experiment_id"):
            continue
        kind = "trap" if verdict in TRAP_VERDICTS else "win" if verdict == "promote-candidate" else "doc"
        weight = 1.25 if kind == "trap" else 1.0
        variable = row.get("variable") or ""
        delta = row.get("cv_delta") or ""
        meta = (
            f"[CONTEST: {contest}] [VERDICT: {verdict}] [VAR: {variable}] [DELTA: {delta}]"
        )
        chunks.append(
            {
                "chunk_id": f"{contest}#{row['experiment_id']}",
                "source_path": source_path,
                "chunk_type": kind,
                "outcome_weight": weight,
                "meta_text": clean_text(meta),
                "body_text": clean_text(row.get("note") or ""),
            }
        )
    return chunks


def _clip_name(value: str) -> str:
    text = str(value)
    return text if len(text) <= 64 else text[:64]


def _rst_level(mark: str) -> int:
    if mark == "=":
        return 1
    if mark == "-":
        return 2
    return 3


def _heading_lines(text: str, rst: bool = False) -> list[tuple[int, str] | str]:
    """ATX headings, plus reStructuredText underlines when ``rst`` is set."""
    raw = text.splitlines()
    parsed: list[tuple[int, str] | str] = []
    index = 0
    while index < len(raw):
        line = raw[index]
        match = HEADING.match(line)
        if match:
            parsed.append((len(match.group(1)), line.strip()))
            index += 1
            continue
        underline = raw[index + 1] if index + 1 < len(raw) else ""
        title = line.strip()
        if (
            rst
            and title
            and not title.startswith("#")
            and underline
            and len(set(underline.strip())) == 1
            and underline.strip()[:1] in "=-~^"
            and len(underline.strip()) >= len(title)
        ):
            parsed.append((_rst_level(underline.strip()[0]), title if title.startswith("#") else f"{'#' * _rst_level(underline.strip()[0])} {title}"))
            index += 2
            continue
        parsed.append(line)
        index += 1
    return parsed


def markdown_chunks(text: str, source_path: str) -> list[dict]:
    chunks = []
    stack: list[tuple[int, str]] = []
    body: list[str] = []
    heading = ""

    def flush() -> None:
        if not heading and not any(line.strip() for line in body):
            return
        crumb = " > ".join(_clip_name(title) for _, title in stack) or _clip_name(heading)
        clipped = "\n".join(_clip_name(line) if len(line) > 64 and " " not in line.strip() else line for line in body)
        chunks.append(
            {
                "chunk_id": _chunk_id(source_path, crumb, "".join(body)[:80]),
                "source_path": source_path,
                "chunk_type": "doc",
                "outcome_weight": 1.0,
                "meta_text": clean_text(crumb),
                "body_text": clean_text(clipped.strip()),
            }
        )

    for item in _heading_lines(text, rst=str(source_path).lower().endswith(".rst")):
        if isinstance(item, tuple):
            flush()
            level, title = item
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            heading = title
            body = []
            continue
        body.append(item)
    flush()
    return chunks


def recipe_chunks(text: str, source_path: str) -> list[dict]:
    loaded = yaml.safe_load(text) or {}
    if not isinstance(loaded, dict) or not loaded.get("id"):
        return []
    recipe_id = str(loaded["id"])
    tags = loaded.get("tags") or []
    tag_text = ", ".join(str(tag) for tag in tags)
    prefix = f"[RECIPE: {recipe_id}] [TAGS: {tag_text}]"
    chunks = [
        {
            "chunk_id": f"recipe:{recipe_id}",
            "source_path": source_path,
            "chunk_type": "recipe",
            "outcome_weight": 1.0,
            "meta_text": clean_text(prefix),
            "body_text": clean_text(loaded.get("summary") or ""),
        }
    ]
    for kind, weight, chunk_type in (
        ("known_traps", 1.25, "trap"),
        ("proven_wins", 1.0, "win"),
    ):
        for item in loaded.get(kind) or []:
            if not isinstance(item, dict):
                continue
            variable = item.get("variable") or ""
            note = item.get("note") or item.get("lesson") or ""
            experiment = item.get("experiment_id") or variable
            chunks.append(
                {
                    "chunk_id": _chunk_id(recipe_id, kind, experiment, variable),
                    "source_path": source_path,
                    "chunk_type": chunk_type,
                    "outcome_weight": weight,
                    "meta_text": clean_text(f"{prefix} [VAR: {variable}]"),
                    "body_text": clean_text(note),
                }
            )
    return chunks


def note_chunk(entry: dict, source_path: str) -> dict:
    tags = entry.get("tags") or ""
    return {
        "chunk_id": f"field_note:{entry.get('id')}",
        "source_path": source_path,
        "chunk_type": "field_note",
        "outcome_weight": 1.0,
        "meta_text": clean_text(f"[TAGS: {tags}] [EVIDENCE: {entry.get('evidence') or ''}]"),
        "body_text": clean_text(entry.get("rule") or ""),
    }


def episode_chunk(entry: dict, source_path: str) -> dict:
    outcome = entry.get("outcome") or ""
    weight = 0.2 if entry.get("superseded_by") else 1.25 if outcome == "failed" else 1.0
    return {
        "chunk_id": f"episode:{entry.get('id')}",
        "source_path": source_path,
        "chunk_type": "episode",
        "outcome_weight": weight,
        "meta_text": clean_text(
            f"[CONTEST: {entry.get('contest')}] [OUTCOME: {outcome}] [TAGS: {entry.get('tags')}] "
            f"[TS: {entry.get('timestamp') or ''}]"
        ),
        "body_text": clean_text(f"{entry.get('task') or ''} {entry.get('lesson') or ''}"),
    }


def skipped_file(path: Path) -> bool:
    name = path.name
    if name in RAW_TABLES:
        return True
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    folded = name.casefold()
    if folded.startswith(".env") or "secret" in folded or "credentials" in folded or folded.endswith(".key"):
        return True
    if ".git" in path.parts:
        return True
    try:
        size = path.stat().st_size
    except OSError:
        return True
    if path.suffix.lower() != ".ipynb" and size > MAX_BYTES:
        return True
    return False


def chunks_for_path(path: Path, contest: str = "") -> list[dict]:
    path = Path(path)
    if skipped_file(path) or not path.is_file():
        return []
    text = path.read_text()
    if path.name == "experiments.csv":
        return ledger_chunks(text, contest or path.parent.parent.name, str(path))
    if path.suffix.lower() == ".md":
        return markdown_chunks(text, str(path))
    if path.suffix.lower() in {".yaml", ".yml"}:
        return recipe_chunks(text, str(path))
    return []


def contest_dirs(parent: Path) -> list[Path]:
    parent = Path(parent)
    found = []

    def walk(path: Path, depth: int) -> None:
        if depth > 2 or not path.is_dir() or path.is_symlink():
            return
        try:
            children = list(path.iterdir())
        except OSError:
            return
        for child in children:
            if child.name in SKIP_DIRS or child.is_symlink() or not child.is_dir():
                continue
            git = child / ".git"
            if git.is_file():
                continue
            if git.is_dir():
                found.append(child)
                continue
            walk(child, depth + 1)

    walk(parent, 1)
    return found


def expand_query(query: str, train=None, test=None) -> str:
    if train is None:
        return query
    features = profile_features(train)
    extra = []
    if features.get("has_group_col"):
        extra.append("GroupKFold group_ids prompt centering TwinHead leakage")
    target = features.get("target_col")
    if target and len(train):
        counts = train[target].value_counts(dropna=False)
        if len(counts) and float(counts.max()) / max(int(counts.min()), 1) > 5:
            extra.append("balanced_accuracy class_weight prior_shift Sinkhorn focal")
    longest = 0.0
    id_cols = set(features.get("id_cols") or [])
    for column in train.columns:
        if column in id_cols:
            continue
        series = train[column]
        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            continue
        lengths = series.fillna("").astype(str).str.len()
        if len(lengths) == 0 or int(lengths.max()) == 0:
            continue
        longest = max(longest, float(np.quantile(lengths.to_numpy(), 0.95)))
    if longest > 1024:
        extra.append("length_sort max_len truncation OOM gradient_checkpointing")
    if test is not None:
        if set(train.columns) != set(test.columns):
            extra.append("check_shift adversarial drift drop_column")
    tail = " ".join(extra)
    return f"{query} {tail}".strip()


def _fts_query(text: str) -> str:
    tokens = TOKEN.findall(text)
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens)


def _age_bonus(meta_text: str) -> float:
    match = re.search(r"\[TS: ([^\]]+)\]", meta_text or "")
    if not match or not match.group(1).strip():
        return 0.0
    raw = match.group(1).strip()
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return 0.0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age_days = max((datetime.now(timezone.utc) - stamp).total_seconds() / 86400.0, 0.0)
    return 0.02 / (1.0 + age_days)


def _negative(chunk: dict) -> bool:
    if chunk["chunk_type"] == "trap":
        return True
    if chunk["chunk_type"] == "episode" and "[OUTCOME: failed]" in chunk["meta_text"]:
        return True
    return False


def _positive(chunk: dict) -> bool:
    if chunk["chunk_type"] in {"win", "field_note"}:
        return True
    if chunk["chunk_type"] == "episode" and "[OUTCOME: worked]" in chunk["meta_text"]:
        return True
    return False


def _pattern(chunk: dict) -> bool:
    return chunk["chunk_type"] in {"code_pattern", "doc"}


def retrieve(store: Store, query: str, train=None, test=None, features: dict | None = None) -> dict:
    expanded = expand_query(query, train, test)
    chunks = store.chunks()
    by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    if features is None and train is not None:
        features = profile_features(train)
    features = features or {}

    bm25_hits = store.bm25(_fts_query(expanded))
    bm25_rank = {chunk_id: index + 1 for index, (chunk_id, _score) in enumerate(bm25_hits)}

    char_rank: dict[str, int] = {}
    vectors = {}
    if chunks:
        corpus = [f"{chunk['meta_text']} {chunk['body_text']}" for chunk in chunks]
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, norm="l2")
        try:
            matrix = vectorizer.fit_transform(corpus)
        except ValueError:
            matrix = None
        if matrix is not None:
            query_vec = vectorizer.transform([expanded])
            sims = cosine_similarity(query_vec, matrix).ravel()
            order = []
            for index, chunk in enumerate(chunks):
                vectors[chunk["chunk_id"]] = matrix[index]
                if float(sims[index]) >= 0.08:
                    order.append((float(sims[index]), chunk["chunk_id"]))
            order.sort(key=lambda item: (-item[0], item[1]))
            char_rank = {chunk_id: index + 1 for index, (_sim, chunk_id) in enumerate(order)}

    scored = []
    seen = set(bm25_rank) | set(char_rank)
    for chunk_id in seen:
        chunk = by_id[chunk_id]
        score = 0.0
        if chunk_id in bm25_rank:
            score += 1.0 / (60.0 + bm25_rank[chunk_id])
        if chunk_id in char_rank:
            score += 1.0 / (60.0 + char_rank[chunk_id])
        scored.append((score, _age_bonus(chunk["meta_text"]), chunk_id))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    ranked = []
    for score, _age, chunk_id in scored:
        item = dict(by_id[chunk_id])
        item["score"] = score
        ranked.append(item)

    selected_ids: list[str] = []

    def fill(pool, limit):
        chosen = []
        for item in pool:
            if len(chosen) >= limit:
                break
            vec = vectors.get(item["chunk_id"])
            if vec is not None and selected_ids:
                prev = [vectors[chunk_id] for chunk_id in selected_ids if chunk_id in vectors]
                if prev:
                    sims = cosine_similarity(vec, np.vstack([row.toarray() for row in prev]))
                    if float(np.max(sims)) > 0.85:
                        continue
            chosen.append(item)
            selected_ids.append(item["chunk_id"])
        return chosen

    recipe_cards = recommend_recipes(features)[:2] if features else []
    recipe_hits = [item for item in ranked if item["chunk_type"] == "recipe"]
    recipes = []
    for card in recipe_cards:
        recipes.append(
            {
                "chunk_id": f"recipe:{card['id']}",
                "source_path": f"recipes/{card['id']}.yaml",
                "chunk_type": "recipe",
                "meta_text": card["id"],
                "body_text": card.get("summary") or "",
                "score": 1.0,
            }
        )
    if len(recipes) < 2:
        recipes.extend(fill([item for item in recipe_hits if item["chunk_id"] not in {row["chunk_id"] for row in recipes}], 2 - len(recipes)))
    negative = fill([item for item in ranked if _negative(item)], 3)
    positive = fill([item for item in ranked if _positive(item)], 3)
    patterns = fill([item for item in ranked if _pattern(item)], 2)
    return {
        "query": expanded,
        "negative": negative,
        "positive": positive,
        "recipes": recipes,
        "patterns": patterns,
        "ranked": ranked,
    }
