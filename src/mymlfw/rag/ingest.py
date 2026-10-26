"""Index docs and code without executing the files."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import tokenize
from datetime import datetime, timezone
from pathlib import Path

import yaml

from mymlfw.errors import MymlfwError
from mymlfw.rag.index import (
    SKIP_DIRS,
    clean_text,
    ledger_chunks,
    markdown_chunks,
    recipe_chunks,
    retrieve,
    skipped_file,
)
from mymlfw.rag.store import Store

DOC_SUFFIXES = {".md", ".rst", ".yaml", ".yml", ".json"}
ML_WORDS = (
    "loss",
    "metric",
    "score",
    "blend",
    "oof",
    "fold",
    "calibrate",
    "augment",
    "feature",
    "postprocess",
    "rank",
    "soup",
)
BASE_HINTS = ("Module", "BaseEstimator", "Dataset", "Engine")
HYPER_KEYS = {"lr", "lora_r", "warmup_ratio"}


class SkipFile(Exception):
    """This file is counted in files_skipped and is not indexed."""


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _walk_files(root: Path) -> list[Path]:
    found = []

    def walk(path: Path) -> None:
        if path.is_symlink():
            return
        try:
            children = list(path.iterdir())
        except OSError:
            return
        for child in children:
            if child.name in SKIP_DIRS or child.is_symlink():
                continue
            if child.is_dir():
                if (child / ".git").is_file():
                    continue
                walk(child)
                continue
            if child.is_file():
                found.append(child)

    walk(root)
    return found


def _eligible(path: Path, mode: str) -> bool:
    suffix = path.suffix.lower()
    if skipped_file(path):
        return False
    if mode == "notes":
        return suffix in {".md", ".rst"} or path.name == "experiments.csv"
    if suffix in DOC_SUFFIXES or path.name == "experiments.csv":
        return True
    if mode == "docs":
        return False
    return suffix in {".py", ".ipynb"}


def _comments(source: str, start: int, end: int) -> str:
    notes = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT and start <= token.start[0] <= end:
                notes.append(token.string.lstrip("# ").strip())
    except tokenize.TokenError:
        return ""
    return " ".join(notes)


def _snippet(source: str, start: int, end: int) -> str:
    lines = source.splitlines()
    return "\n".join(lines[start - 1 : min(end, start - 1 + 60)])


def _signature(node: ast.AST) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    args = []
    positional = node.args.args
    defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)

    def render(arg, default) -> str:
        if default is None:
            return arg.arg
        try:
            shown = ast.unparse(default)
        except Exception:
            shown = "?"
        return f"{arg.arg}={shown}"

    for arg, default in zip(positional, defaults):
        args.append(render(arg, default))
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        args.append(render(arg, default))
    return f"{node.name}({', '.join(args)})"


def _auto_tags(tree: ast.AST) -> list[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    tags = []
    if "peft" in names or "LoraConfig" in names:
        tags.extend(["lora", "peft"])
    if "GroupKFold" in names or "StratifiedGroupKFold" in names:
        tags.extend(["group_cv", "cv"])
    if "optuna" in names or "minimize" in names:
        tags.extend(["blend", "optimization"])
    if "log_softmax" in names or "kl_div" in names:
        tags.extend(["distillation", "calibration"])
    return tags


def _interesting_function(node: ast.FunctionDef) -> bool:
    haystack = f"{node.name} {ast.get_docstring(node) or ''}".lower()
    return any(word in haystack for word in ML_WORDS)


def code_chunks(source: str, source_path: str, extra_tags: list[str] | None = None) -> list[dict]:
    tree = ast.parse(source)
    tags = list(extra_tags or []) + _auto_tags(tree)
    chunks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = []
            for base in node.bases:
                try:
                    bases.append(ast.unparse(base))
                except Exception:
                    bases.append("")
            init = next((item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"), None)
            signature = _signature(init) if init else f"{node.name}()"
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            marked = node.name
            base_names = [base.split(".")[-1].strip("() ") for base in bases]
            if any(name.endswith(hint) for name in base_names for hint in BASE_HINTS):
                marked = f"{node.name} {', '.join(bases)}"
            chunks.append(_code_record(source, source_path, node, signature, tags, marked, bases))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _interesting_function(node):
            chunks.append(_code_record(source, source_path, node, _signature(node), tags, node.name, []))
    return chunks


def _code_record(source, source_path, node, signature, tags, marked, bases) -> dict:
    end = getattr(node, "end_lineno", node.lineno) or node.lineno
    doc = ast.get_docstring(node) or ""
    comments = _comments(source, node.lineno, end)
    snippet = _snippet(source, node.lineno, end)
    body = {
        "name": node.name,
        "signature": signature,
        "docstring": doc,
        "bases": bases,
        "comments": comments,
        "line_start": node.lineno,
        "line_end": min(end, node.lineno + 59),
        "snippet": snippet,
    }
    tag_text = ",".join(dict.fromkeys(tags))
    return {
        "chunk_id": f"code:{source_path}:{node.lineno}:{node.name}",
        "source_path": source_path,
        "chunk_type": "code_pattern",
        "outcome_weight": 1.0,
        "meta_text": clean_text(f"[NAME: {marked}] [TAGS: {tag_text}] {signature}"),
        "body_text": json.dumps(body),
    }


def _notebook_chunks(path: Path, extra_tags: list[str]) -> list[dict]:
    raw = json.loads(path.read_text())
    cells = []
    for cell in raw.get("cells") or []:
        source = cell.get("source") or ""
        if isinstance(source, list):
            source = "".join(source)
        cells.append((cell.get("cell_type"), source))
    stripped = json.dumps([{"cell_type": kind, "source": source} for kind, source in cells])
    if len(stripped.encode()) > 256_000:
        raise SkipFile(str(path))
    chunks = []
    for index, (kind, source) in enumerate(cells):
        if kind != "markdown":
            continue
        code = ""
        if index + 1 < len(cells) and cells[index + 1][0] == "code":
            code = cells[index + 1][1]
        heading = next((line for line in source.splitlines() if line.startswith("#")), source.splitlines()[0] if source else "notebook")
        chunks.append(
            {
                "chunk_id": f"nb:{path}:{index}",
                "source_path": str(path),
                "chunk_type": "doc",
                "outcome_weight": 1.0,
                "meta_text": clean_text(heading),
                "body_text": clean_text(f"{source}\n{code}"),
            }
        )
        if code.strip():
            try:
                chunks.extend(code_chunks(code, str(path), extra_tags))
            except SyntaxError:
                continue
    return chunks


def _hyper_keys(value, found: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in HYPER_KEYS:
                found.add(str(key))
            _hyper_keys(item, found)
    elif isinstance(value, list):
        for item in value:
            _hyper_keys(item, found)


def _config_chunk(path: Path, root: Path) -> dict | None:
    text = path.read_text()
    try:
        loaded = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except Exception:
        return None
    found: set[str] = set()
    _hyper_keys(loaded, found)
    if not found and path.suffix.lower() in {".yaml", ".yml"}:
        return None
    meta = f"[KEYS: {', '.join(sorted(found))}]"
    ledger = None
    for candidate in (root / "experiments.csv", root / "ledger" / "experiments.csv"):
        if candidate.is_file():
            ledger = candidate
            break
    if ledger is not None:
        best = None
        import csv

        for row in csv.DictReader(ledger.open()):
            if (row.get("verdict") or "") == "pending" or not row.get("cv_mean"):
                continue
            try:
                score = float(row["cv_mean"])
            except ValueError:
                continue
            if best is None or score > best[0]:
                best = (score, row.get("variable") or "")
        if best:
            meta += f" [BEST: {best[0]} {best[1]}]"
    readme = root / "README.md"
    if readme.is_file():
        for line in readme.read_text().splitlines():
            if line.startswith("#"):
                meta += f" [README: {line.strip()}]"
                break
    return {
        "chunk_id": f"config:{path}",
        "source_path": str(path),
        "chunk_type": "doc",
        "outcome_weight": 1.0,
        "meta_text": clean_text(meta),
        "body_text": clean_text(text[:4000]),
    }


def _chunks_for(path: Path, root: Path, mode: str, tags: list[str]) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".ipynb":
        return _notebook_chunks(path, tags)
    if suffix == ".py":
        return code_chunks(path.read_text(), str(path), tags)
    if path.name == "experiments.csv":
        return ledger_chunks(path.read_text(), root.name, str(path))
    if suffix == ".md" or suffix == ".rst":
        return markdown_chunks(path.read_text(), str(path))
    if suffix in {".yaml", ".yml", ".json"}:
        recipe = recipe_chunks(path.read_text(), str(path)) if suffix in {".yaml", ".yml"} else []
        config = _config_chunk(path, root)
        chunks = list(recipe)
        if config and (config["meta_text"] not in {item["meta_text"] for item in chunks}):
            if "[KEYS:" in config["meta_text"] or not recipe:
                chunks.append(config)
        return chunks
    return []


def _mode_for(root: Path, mode: str) -> str:
    if mode != "auto":
        return mode
    for path in _walk_files(root):
        if path.suffix.lower() in {".py", ".ipynb"}:
            return "repo"
    return "docs"


def _purge_root(store: Store, root: str) -> None:
    stale = store.conn.execute(
        "SELECT file_path FROM ingested_files WHERE repo_root=?",
        (root,),
    ).fetchall()
    for item in stale:
        store.delete_source(item["file_path"])


def ingest(path, mode: str = "auto", tags: str = "", db=None, sync: bool = False) -> dict:
    store = Store(db)
    try:
        if sync:
            roots = [
                row["repo_root"]
                for row in store.conn.execute("SELECT DISTINCT repo_root FROM ingested_files").fetchall()
            ]
            summary = {"status": "ok", "files_seen": 0, "files_updated": 0, "files_skipped": 0, "chunk_count": 0}
            for root in roots:
                if not Path(root).is_dir():
                    _purge_root(store, root)
                    continue
                one = _ingest_root(store, Path(root), mode, tags)
                for key in ("files_seen", "files_updated", "files_skipped"):
                    summary[key] += one[key]
            summary["chunk_count"] = store.conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
            return summary
        if not path:
            raise MymlfwError("USAGE", "Pass --path, or pass --sync to refresh registered repos.")
        root = Path(path)
        if not root.is_dir():
            raise MymlfwError("INGEST_PATH", "Pass a directory that exists.", path=str(path))
        return _ingest_root(store, root, mode, tags)
    finally:
        store.close()


def _ingest_root(store: Store, root: Path, mode: str, tags: str) -> dict:
    root = Path(root).resolve()
    chosen = _mode_for(root, mode)
    extra = [part.strip() for part in tags.split(",") if part.strip()]
    seen = updated = skipped = 0
    present = set()
    for path in _walk_files(root):
        if not _eligible(path, chosen):
            continue
        seen += 1
        present.add(str(path))
        try:
            digest = _sha(path)
        except OSError:
            skipped += 1
            continue
        row = store.conn.execute(
            "SELECT file_sha256 FROM ingested_files WHERE file_path=?",
            (str(path),),
        ).fetchone()
        if row and row["file_sha256"] == digest:
            continue
        try:
            chunks = _chunks_for(path, root, chosen, extra)
        except (SkipFile, SyntaxError, json.JSONDecodeError, UnicodeError, OSError, ValueError, yaml.YAMLError):
            skipped += 1
            continue
        store.replace_chunks(str(path), chunks)
        store.conn.execute(
            """
            INSERT INTO ingested_files(file_path, repo_root, repo_name, file_sha256, ingested_at, chunk_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_sha256=excluded.file_sha256,
                ingested_at=excluded.ingested_at,
                chunk_count=excluded.chunk_count
            """,
            (
                str(path),
                str(root),
                root.name,
                digest,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                len(chunks),
            ),
        )
        store.conn.commit()
        updated += 1
    stale = store.conn.execute(
        "SELECT file_path FROM ingested_files WHERE repo_root=?",
        (str(root),),
    ).fetchall()
    for item in stale:
        if item["file_path"] not in present:
            store.delete_source(item["file_path"])
    total = store.conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
    return {
        "status": "ok",
        "files_seen": seen,
        "files_updated": updated,
        "files_skipped": skipped,
        "chunk_count": int(total),
    }


def search(query: str, chunk_type: str = "code_pattern", db=None) -> list[dict]:
    store = Store(db)
    try:
        found = retrieve(store, query)
        hits = []
        pools = found["ranked"]
        for item in pools:
            if chunk_type and item["chunk_type"] != chunk_type:
                continue
            record = {"source_path": item["source_path"], "chunk_type": item["chunk_type"], "score": item["score"]}
            try:
                body = json.loads(item["body_text"])
            except json.JSONDecodeError:
                body = {"snippet": item["body_text"], "name": "", "signature": "", "line_start": None, "line_end": None}
            if isinstance(body, dict):
                record.update(
                    {
                        "name": body.get("name", ""),
                        "signature": body.get("signature", ""),
                        "source_path": item["source_path"],
                        "line_start": body.get("line_start"),
                        "line_end": body.get("line_end"),
                        "snippet": body.get("snippet", item["body_text"]),
                    }
                )
            hits.append(record)
        return hits
    finally:
        store.close()
