"""Apply retrieved wiring on a new git worktree. Does not record an episode."""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
from pathlib import Path

import tomllib

from mymlfw.campaign.profile import profile_features
from mymlfw.errors import MymlfwError
from mymlfw.rag.analyze import load_frames
from mymlfw.rag.index import clean_text, retrieve

ENGINES = {
    "closed-set-llm-id": "TextBlendEngine",
    "grouped-text": "TextBlendEngine",
    "ranking": "RankedCandidateEngine",
    "code-agent": "AgentZipEngine",
    "circuit-portfolio": "PortfolioEngine",
    "benchmark": "BenchmarkEngine",
}
ENGINE_NAMES = (
    "TextBlendEngine",
    "RankedCandidateEngine",
    "AgentZipEngine",
    "PortfolioEngine",
    "BenchmarkEngine",
)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _require_checkout(source: Path) -> None:
    probe = _git(source, "rev-parse", "--is-inside-work-tree", check=False)
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        raise MymlfwError("GIT_REQUIRED", "Run advise inside an existing git checkout.")
    head = _git(source, "rev-parse", "--verify", "HEAD", check=False)
    if head.returncode != 0:
        raise MymlfwError("GIT_NO_COMMITS", "git commit -m 'initial'")


def _require_git(source: Path) -> None:
    _require_checkout(source)
    dirty = _git(source, "status", "--porcelain", "--untracked-files=no", check=False)
    if dirty.returncode != 0:
        raise MymlfwError("GIT_REQUIRED", "Run advise inside an existing git checkout.")
    if dirty.stdout.strip():
        raise MymlfwError("DIRTY_TREE", "Commit or stash tracked changes before advise.")


def _branch_exists(source: Path, branch: str) -> bool:
    probe = _git(source, "show-ref", "--verify", f"refs/heads/{branch}", check=False)
    return probe.returncode == 0


class atomic_worktree:
    def __init__(self, source: Path, branch: str, dest: Path):
        self.source = source
        self.branch = branch
        self.dest = dest
        self.created = False

    def __enter__(self) -> Path:
        if self.dest.exists() or _branch_exists(self.source, self.branch):
            raise MymlfwError(
                "ADVICE_EXISTS",
                "Run advise --clean --dir <contest> --id <shortid> before reusing that id.",
            )
        _git(self.source, "worktree", "add", "-b", self.branch, str(self.dest), "HEAD")
        self.created = True
        return self.dest

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None or not self.created:
            return False
        _git(self.source, "worktree", "remove", "--force", str(self.dest), check=False)
        _git(self.source, "branch", "-D", self.branch, check=False)
        return False


def _load_frames(source: Path):
    return load_frames(source)


def _citation(chunk: dict) -> str:
    chunk_id = str(chunk.get("chunk_id") or "")
    if chunk_id.startswith("episode:"):
        return chunk_id
    if "#" in chunk_id and not chunk_id.startswith(("code:", "nb:", "config:")):
        experiment = chunk_id.split("#", 1)[1]
        source = str(chunk.get("source_path") or "")
        if source:
            return f"{source}#{experiment}"
        return chunk_id
    line = None
    text = chunk.get("body_text") or ""
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        body = None
    if isinstance(body, dict):
        line = body.get("line_start")
    if line:
        return f"{chunk.get('source_path')}#L{line}"
    return chunk.get("source_path") or chunk_id


def _attr(value: str) -> str:
    text = clean_text(value).replace('"', "").replace("<", "").replace(">", "")
    return " ".join(text.split())


def _fence_body(value: str) -> str:
    body = clean_text(value)
    body = body.replace("</retrieved_note", "< /retrieved_note")
    body = body.replace("<retrieved_note", "< retrieved_note")
    return body


def _fence(chunk: dict) -> str:
    source = _attr(_citation(chunk))
    score = chunk.get("score")
    rendered = f"{float(score):.2f}" if isinstance(score, (int, float)) else "0.00"
    body = _fence_body(chunk.get("body_text") or "")
    return f'<retrieved_note source="{source}" score="{rendered}">\n{body}\n</retrieved_note>'


def _pattern_block(chunk: dict) -> str:
    text = chunk.get("body_text") or ""
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    name = body.get("name") or chunk.get("meta_text") or ""
    signature = body.get("signature") or ""
    doc = body.get("docstring") or ""
    path = _citation(chunk)
    return (
        f"{_fence(chunk)}\n"
        f"path: {path}\n"
        f"signature: {signature}\n"
        f"name: {name}\n"
        f"docstring: {doc}\n"
        "Adapt this pattern in the contest; do not copy the external file."
    )


def _text_p95(train) -> int:
    if train is None or len(train) == 0:
        return 0
    import pandas as pd

    longest = 0.0
    for column in train.columns:
        series = train[column]
        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            continue
        lengths = series.fillna("").astype(str).str.len()
        if len(lengths) == 0 or int(lengths.max()) == 0:
            continue
        longest = max(longest, float(lengths.quantile(0.95)))
    return int(longest)


def _fingerprint(features: dict, train) -> str:
    classes = features.get("n_classes")
    if classes is None:
        kind = "unlabeled"
    elif int(classes) > 2:
        kind = "multiclass"
    elif int(classes) == 2:
        kind = "binary"
    else:
        kind = "unlabeled"
    grouped = "grouped" if features.get("has_group_col") else "ungrouped"
    return f"{kind} | {grouped} | text_p95={_text_p95(train)}"


def _advice_text(contest: str, branch: str, task: str, found: dict, source: Path, features: dict | None = None, train=None) -> str:
    written = {"docs/MYMLFW_ADVICE.md", "engine_mymlfw.py", "bin/preflight_submit.sh", "requirements.txt"}
    candidates = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = path.relative_to(source).as_posix()
        if rel not in written:
            candidates.append(rel)
    lines = [
        "# MYMLFW RAG Advice Brief",
        f"Query Fingerprint: `{_fingerprint(features or {}, train)}`",
        f"Query: `{clean_text(found.get('query') or task)}`",
        "",
        "## 1. DO NOT REPEAT (Retrieved Traps & Failed Episodes)",
    ]
    lines.extend(_fence(chunk) for chunk in found.get("negative") or [])
    lines.extend(["", "## 2. RECOMMENDED PLAYBOOK (Retrieved Wins & Recipes)"])
    lines.extend(_fence(chunk) for chunk in list(found.get("recipes") or []) + list(found.get("positive") or []))
    lines.extend(["", "## 3. LEARNED PATTERNS FROM OTHER PROJECTS"])
    lines.extend(_pattern_block(chunk) for chunk in found.get("patterns") or [])
    lines.extend(["", "## 4. CANDIDATE FILES TO INSPECT (Untouched by Advise)"])
    lines.extend(f"- {name}" for name in candidates)
    safe_task = " ".join(task.replace('"', "'").split())
    lines.extend(
        [
            "",
            "python -m mymlfw episode add "
            f"--contest {contest} --task \"{safe_task}\" "
            f"--actions \"applied advise branch {branch}\" "
            "--outcome worked --lesson \"<filled after CV or preflight>\" "
            f"--evidence {branch}",
            "",
        ]
    )
    return "\n".join(lines)


def render_engine(class_name: str) -> str:
    parent = class_name if class_name in ENGINE_NAMES else "TextBlendEngine"
    return (
        f"from mymlfw.engines import {parent}\n\n"
        f"class ContestEngine({parent}):\n"
        "    classes = []\n\n"
        "    def predict_row(self, row):\n"
        "        raise NotImplementedError\n"
    )


def _dist_name(item: str) -> str:
    bare = str(item).strip().split("[", 1)[0].split("@", 1)[0]
    bare = bare.split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].split(" ", 1)[0]
    return bare.strip()


def _requirement_names(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        bare = line.split("#", 1)[0].strip()
        if not bare or bare.startswith("-"):
            continue
        name = _dist_name(bare)
        if name:
            names.append(name)
    return names


def _dependency_names(text: str) -> list[str]:
    if not text.strip():
        return []
    loaded = tomllib.loads(text)
    deps = (loaded.get("project") or {}).get("dependencies") or []
    return [name for name in (_dist_name(item) for item in deps) if name]


def _with_dependency(text: str) -> str | None:
    if "mymlfw" in _dependency_names(text):
        return None
    if re.search(r"(?m)^dependencies\s*=\s*\[", text):
        edited = re.sub(r"(?m)^(dependencies\s*=\s*\[)", '\\1\n  "mymlfw",', text, count=1)
    elif re.search(r"(?m)^\[project\]\s*$", text):
        edited = re.sub(r"(?m)^\[project\]\s*$", '[project]\ndependencies = ["mymlfw"]', text, count=1)
    else:
        edited = text.rstrip() + '\n\n[project]\ndependencies = ["mymlfw"]\n'
    tomllib.loads(edited)
    return edited


def _retrieved_text(found: dict) -> str:
    parts = []
    for key in ("negative", "positive", "recipes", "patterns"):
        for chunk in found.get(key) or []:
            parts.append(str(chunk.get("body_text") or ""))
            parts.append(str(chunk.get("meta_text") or ""))
    return "\n".join(parts)


def write_tree(
    dest: Path,
    source: Path,
    contest: str,
    branch: str,
    task: str,
    found: dict,
    engine_class: str,
    features: dict | None = None,
    train=None,
) -> list[str]:
    written = []
    docs = dest / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "MYMLFW_ADVICE.md").write_text(
        _advice_text(contest, branch, task, found, source, features=features, train=train)
    )
    written.append("docs/MYMLFW_ADVICE.md")
    (dest / "engine_mymlfw.py").write_text(render_engine(engine_class))
    written.append("engine_mymlfw.py")

    requirements = dest / "requirements.txt"
    existing = requirements.read_text() if requirements.is_file() else ""
    if "mymlfw" not in _requirement_names(existing):
        requirements.write_text(existing + ("" if existing.endswith("\n") or not existing else "\n") + "mymlfw\n")
        written.append("requirements.txt")

    project = dest / "pyproject.toml"
    if project.is_file():
        edited = _with_dependency(project.read_text())
        if edited is not None:
            project.write_text(edited)
            written.append("pyproject.toml")

    mentions = "preflight" in _retrieved_text(found).casefold()
    if (source / "bin").is_dir() or (dest / "bin").is_dir() or mentions:
        script = dest / "bin" / "preflight_submit.sh"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(
            "#!/bin/sh\n"
            "exec \"${PYTHON:-python3}\" -m mymlfw preflight --require-scale-report \"$@\"\n"
        )
        script.chmod(0o755)
        written.append("bin/preflight_submit.sh")
    data = source / "data"
    if data.exists():
        link = dest / "data"
        if not link.exists():
            link.symlink_to(os.path.relpath(data, dest), target_is_directory=True)
        marker = dest / ".mymlfw"
        marker.mkdir(parents=True, exist_ok=True)
        (marker / "data_dir").write_text(str(data.resolve()) + "\n")
    return written


def _short_id() -> str:
    return secrets.token_hex(3)


def _paths(source: Path, short_id: str) -> tuple[str, str, Path]:
    contest = source.name
    branch = f"mymlfw/advise-{contest}-{short_id}"
    dest = source.parent / f"{contest}-advise-{short_id}"
    return contest, branch, dest


def clean(directory, short_id: str) -> dict:
    source = Path(directory).resolve()
    _require_checkout(source)
    contest, branch, dest = _paths(source, short_id)
    _git(source, "worktree", "remove", "--force", str(dest), check=False)
    _git(source, "branch", "-D", branch, check=False)
    return {"status": "ok", "source_dir": str(source), "branch": branch, "worktree_dir": str(dest)}


def advise(directory, db=None, task: str = "next experiment") -> dict:
    source = Path(directory).resolve()
    _require_git(source)
    from mymlfw.rag.store import Store

    store = Store(db) if db else Store()
    try:
        before = store.conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        from mymlfw.rag.index import contest_dirs
        from mymlfw.rag.ingest import ingest as ingest_tree

        roots = []
        for root in contest_dirs(source.parent):
            resolved = root.resolve()
            if resolved in roots:
                continue
            roots.append(resolved)
            ingest_tree(resolved, mode="notes", db=store.path)
        if source.resolve() not in roots:
            ingest_tree(source, mode="notes", db=store.path)
        train, test = _load_frames(source)
        features = profile_features(train) if train is not None else {}
        found = retrieve(store, task, train=train, test=test, features=features)
        top = (found.get("recipes") or [{}])[0]
        recipe_id = str(top.get("chunk_id") or "").split("recipe:", 1)[-1] if top else ""
        if recipe_id.startswith("recipe:"):
            recipe_id = recipe_id.split("recipe:", 1)[-1]
        engine_class = ENGINES.get(recipe_id, "TextBlendEngine")
        for _ in range(5):
            short_id = _short_id()
            contest, branch, dest = _paths(source, short_id)
            if not dest.exists() and not _branch_exists(source, branch):
                break
        else:
            raise MymlfwError("ADVICE_EXISTS", "Remove an old advise worktree and retry.")
        with atomic_worktree(source, branch, dest):
            written = write_tree(
                dest, source, contest, branch, task, found, engine_class, features=features, train=train
            )
            if (dest / "recipes" / "memory.db").exists():
                raise MymlfwError("MEMORY_IN_WORKTREE", "Keep memory.db in the framework checkout.")
            from mymlfw.rag.analyze import analyze, format_next_steps

            report = analyze(dest, db=store.path, task=task, source_dir=source)
            advice_path = dest / "docs" / "MYMLFW_ADVICE.md"
            brief = advice_path.read_text()
            command = f"python -m mymlfw episode add --contest {contest}"
            steps = format_next_steps(report["next_steps"]) + "\n"
            index = brief.rfind(command)
            if index == -1:
                brief = brief + "\n" + steps
            else:
                brief = brief[:index] + steps + brief[index:]
            advice_path.write_text(brief)
        after = store.conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        if after != before:
            raise MymlfwError("EPISODE_CHANGED", "advise does not insert episodes.")
        ids = []
        for key in ("negative", "positive", "recipes", "patterns"):
            ids.extend(chunk.get("chunk_id") for chunk in found.get(key) or [])
        return {
            "status": "ok",
            "source_dir": str(source),
            "worktree_dir": str(dest),
            "branch": branch,
            "top_recipe": recipe_id,
            "engine_class": engine_class,
            "files_written": written,
            "retrieved_ids": [item for item in ids if item],
            "next_command": (
                "pytest && ./bin/preflight_submit.sh"
                if "bin/preflight_submit.sh" in written
                else "pytest"
            ),
        }
    finally:
        store.close()
