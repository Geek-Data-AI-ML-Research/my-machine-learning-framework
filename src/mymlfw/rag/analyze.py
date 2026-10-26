"""Read-only next step for a contest directory."""

from __future__ import annotations

import ast
import csv
import json
import re
from pathlib import Path

import pandas as pd

from mymlfw.campaign.match import recommend_recipes
from mymlfw.campaign.profile import profile_features
from mymlfw.rag.index import retrieve

RECIPE_ENGINE = {
    "closed-set-llm-id": "TextBlendEngine",
    "grouped-text": "TextBlendEngine",
    "ranking": "RankedCandidateEngine",
    "code-agent": "AgentZipEngine",
    "circuit-portfolio": "PortfolioEngine",
    "benchmark": "BenchmarkEngine",
}
KILL = {"kill", "confirmed-large-gap"}
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_@\-]*(?:=[A-Za-z0-9_@.\-+]+)?")


def _first(roots: list[Path], relatives: tuple[str, ...]) -> Path | None:
    for root in roots:
        for relative in relatives:
            path = root / relative
            if path.is_file():
                return path
    return None


def load_frames(root: Path):
    """Train and test tables from a contest root or a data directory."""
    root = Path(root)
    train_path = _first(
        [root],
        ("data/train.csv", "data/train.parquet", "train.csv", "train.parquet", "items.jsonl"),
    )
    test_path = _first([root], ("data/test.csv", "data/test.parquet", "test.csv", "test.parquet"))
    train = _read_table(train_path) if train_path is not None else None
    test = _read_table(test_path) if test_path is not None else None
    return train, test


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    return pd.read_csv(path)


def _number(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _rows(path: Path | None) -> list[dict]:
    if path is None:
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def engine_classes(path: Path) -> set[str]:
    """Class and import names. The file is not imported."""
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name):
                    found.add(base.id)
                elif isinstance(base, ast.Attribute):
                    found.add(base.attr)
        elif isinstance(node, ast.ImportFrom):
            found.update(alias.name for alias in node.names)
    return found


def _variable_tokens(*parts: str) -> set[str]:
    tokens = set()
    for part in parts:
        tokens.update(TOKEN.findall(part or ""))
    return tokens


def _ledger_variables(values: set[str]) -> set[str]:
    names = set(values)
    for value in values:
        if "=" in value:
            names.add(value.split("=", 1)[0])
    return names


def _summary(rows: list[dict]) -> dict:
    scored = [row for row in rows if _number(row.get("public_score")) is not None or _number(row.get("cv_mean")) is not None]
    public = [value for value in (_number(row.get("public_score")) for row in rows) if value is not None]
    means = [
        value
        for row in rows
        if (row.get("verdict") or "") != "pending"
        for value in [_number(row.get("cv_mean"))]
        if value is not None
    ]
    last_two = scored[-2:]
    plateau = False
    if len(last_two) == 2:
        deltas = [_number(row.get("cv_delta")) for row in last_two]
        if all(delta is not None and abs(delta) < 1e-5 for delta in deltas):
            plateau = True
        earlier = [
            value
            for row in scored[:-2]
            for value in [_number(row.get("public_score"))]
            if value is not None
        ]
        current = [_number(row.get("public_score")) for row in last_two]
        if earlier and all(value is not None for value in current):
            if max(current) <= max(earlier):
                plateau = True
    latest = rows[-1] if rows else {}
    kill = next((row for row in reversed(rows) if (row.get("verdict") or "") in KILL), None)
    last_variable = (scored[-1].get("variable") if scored else "") or ""
    return {
        "latest_verdict": (latest.get("verdict") or None) if rows else None,
        "latest_variable": latest.get("variable") or "",
        "best_cv_mean": max(means) if means else None,
        "best_public_score": max(public) if public else None,
        "variables": {row.get("variable") or "" for row in rows if row.get("variable")},
        "plateau": plateau,
        "last_variable": last_variable,
        "kill": kill,
        "pending": (latest.get("verdict") or "") == "pending",
    }


def _code_name(chunk: dict) -> tuple[str, str]:
    try:
        body = json.loads(chunk.get("body_text") or "")
    except json.JSONDecodeError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return body.get("name") or chunk.get("meta_text") or "pattern", chunk.get("source_path") or ""


def _positive_record(text: str, evidence: str, tags: str) -> dict:
    return {"text": f"A previous task that worked: {text}", "tokens": _variable_tokens(evidence, tags)}


def _positives(store, found) -> list[dict]:
    episodes = {
        int(row["id"]): row
        for row in store.episodes()
        if row.get("outcome") == "worked" and not row.get("superseded_by")
    }
    notes = {int(row["id"]): row for row in store.field_notes()}
    chosen = []
    seen = set()
    for item in found.get("positive") or []:
        chunk_id = str(item.get("chunk_id") or "")
        if chunk_id in seen or ":" not in chunk_id:
            continue
        kind, raw_id = chunk_id.split(":", 1)
        if not raw_id.isdigit():
            continue
        row_id = int(raw_id)
        seen.add(chunk_id)
        if kind == "episode" and row_id in episodes:
            row = episodes[row_id]
            chosen.append(_positive_record(row["lesson"], row.get("evidence") or "", row.get("tags") or ""))
        elif kind == "field_note" and row_id in notes:
            row = notes[row_id]
            chosen.append(_positive_record(row["rule"], row.get("evidence") or "", row.get("tags") or ""))
    return chosen


def _failed(store, contest: str, found) -> dict | None:
    rows = [
        row
        for row in store.episodes()
        if row.get("outcome") == "failed"
        and not row.get("superseded_by")
        and (not contest or row.get("contest") == contest)
    ]
    if not rows:
        return None
    for item in found.get("negative") or []:
        if item["chunk_type"] != "episode" or "[OUTCOME: failed]" not in item["meta_text"]:
            continue
        for row in reversed(rows):
            if row["lesson"] in (item.get("body_text") or ""):
                return row
    return rows[-1]


def analyze(directory, db=None, task: str = "", out=None, source_dir=None) -> dict:
    from mymlfw.rag.store import Store

    files_root = Path(directory)
    data_root = Path(source_dir) if source_dir else files_root
    file_roots = [files_root, data_root]
    data_roots = [data_root, files_root]
    ledger_path = _first(data_roots, ("ledger/experiments.csv",))
    train_path = _first(
        data_roots,
        ("data/train.csv", "data/train.parquet", "train.csv", "train.parquet", "items.jsonl"),
    )
    test_path = _first(data_roots, ("data/test.csv", "data/test.parquet", "test.csv", "test.parquet"))
    engine_path = _first(file_roots, ("engine_mymlfw.py", "engine.py"))
    kernel_path = _first(
        file_roots,
        ("kernel-metadata.json", "kernel/kernel-metadata.json", "kernel/src/kernel-metadata.json"),
    )
    profile_path = _first(file_roots, ("DATA_PROFILE.md",))
    requirements = _first(file_roots, ("requirements.txt", "pyproject.toml"))
    preflight = _first(file_roots, ("bin/preflight_submit.sh", "scripts/preflight.py"))
    rows = _rows(ledger_path)
    summary = _summary(rows)
    features = profile_features(_read_table(train_path)) if train_path is not None else None
    cards = recommend_recipes(features) if features else []
    present = set()
    if engine_path is not None:
        present = engine_classes(engine_path)
        other = engine_path.with_name("engine.py" if engine_path.name == "engine_mymlfw.py" else "engine_mymlfw.py")
        if not other.is_file():
            for root in file_roots:
                candidate = root / other.name
                if candidate.is_file():
                    present |= engine_classes(candidate)
                    break
        else:
            present |= engine_classes(other)
    mismatch = None
    for card in cards:
        recipe_id = str(card.get("id") or "")
        mapped = RECIPE_ENGINE.get(recipe_id)
        if mapped and mapped not in present:
            mismatch = recipe_id
            break
    gaps = []
    if ledger_path is None:
        gaps.append("missing ledger")
    if summary["pending"]:
        gaps.append(f"pending {summary['latest_variable']}".strip())
    if summary["kill"]:
        gaps.append(f"{summary['kill'].get('verdict')} {summary['kill'].get('variable')}")
    query = " ".join(part for part in [task, *gaps] if part)
    if summary["plateau"]:
        query = f"{query} stagnant score after {summary['last_variable']} plateau orthogonal shift".strip()
    store = Store(db) if db else Store()
    try:
        train = _read_table(train_path) if train_path is not None else None
        test = _read_table(test_path) if test_path is not None else None
        found = retrieve(store, query or "next experiment", train=train, test=test, features=features or {})
        query = found["query"]
        warnings = []
        if ledger_path is None:
            warnings.append(
                {
                    "text": "Create ledger/experiments.csv with python -m mymlfw probe register before the next run.",
                    "why": "missing ledger",
                }
            )
        else:
            if summary["pending"] and summary["kill"] is None:
                warnings.append(
                    {
                        "text": f"Finish the pending probe {summary['latest_variable']} before opening another variable.",
                        "why": "pending",
                    }
                )
            if summary["kill"] is not None:
                warnings.append(
                    {
                        "text": f"Do not repeat {summary['kill'].get('variable')}. {summary['kill'].get('note') or ''}".rstrip(),
                        "why": summary["kill"].get("verdict") or "",
                    }
                )
        failed = _failed(store, data_root.name, found)
        if failed is not None:
            lesson = failed.get("lesson") or failed.get("body_text") or ""
            warnings.append({"text": f"Do not repeat this task. {lesson}".rstrip(), "why": "failed episode"})
        warnings = warnings[:2]
        actions = []
        if mismatch:
            actions.append(
                {
                    "text": f"The profile matches {mismatch}. The tree engine does not.",
                    "why": mismatch,
                }
            )
        code = next((item for item in found.get("patterns") or [] if item["chunk_type"] == "code_pattern"), None)
        if code is None:
            code = next((item for item in found.get("ranked") or [] if item["chunk_type"] == "code_pattern"), None)
        if code is not None:
            name, source = _code_name(code)
            why = ""
            if summary["plateau"]:
                why = f"stagnant score after {summary['last_variable']}"
            actions.append(
                {
                    "text": f"Adapt {name} from {source}. Do not copy the external file.",
                    "why": why,
                }
            )
        tried = _ledger_variables(summary["variables"])
        for candidate in _positives(store, found):
            tokens = candidate["tokens"]
            if tokens and tokens <= tried:
                continue
            actions.append({"text": candidate["text"], "why": "worked"})
            break
        steps = (warnings + actions)[:5]
        if out:
            lines = ["# NEXT STEPS"]
            for step in steps:
                lines.append(f"- {step['text']}")
                if step.get("why"):
                    lines.append(f"  why: {step['why']}")
            Path(out).write_text("\n".join(lines) + "\n")
        return {
            "status": "ok",
            "dir": str(files_root),
            "structure": {
                "ledger": str(ledger_path) if ledger_path else None,
                "train": str(train_path) if train_path else None,
                "engine": str(engine_path) if engine_path else None,
                "kernel": str(kernel_path) if kernel_path else None,
                "data_profile": profile_path is not None,
                "requirements": requirements is not None,
                "preflight": preflight is not None,
                "features": features,
            },
            "latest_verdict": summary["latest_verdict"],
            "best_public_score": summary["best_public_score"],
            "plateau": summary["plateau"],
            "gaps": gaps,
            "query": query,
            "next_steps": steps,
        }
    finally:
        store.close()


def format_next_steps(steps: list[dict]) -> str:
    lines = ["# NEXT STEPS"]
    for step in steps:
        lines.append(f"- {step['text']}")
    return "\n".join(lines) + "\n"
