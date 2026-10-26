"""Create a contest tree, archive probes, and promote plugins."""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from mymlfw.campaign.ledger import COLUMNS, load_ledger
from mymlfw.campaign.match import load_recipe_cards
from mymlfw.errors import MymlfwError
from mymlfw.kernel.build import kernel_metadata
from mymlfw.kernel.run import CELL2_TEMPLATE
from mymlfw.paths import checkout_root, repo_root

TOKEN_LIMIT = 1500
INDEX_START = "<!-- mymlfw-index -->"
INDEX_END = "<!-- /mymlfw-index -->"
CATEGORIES = ("blend", "cv", "metrics", "sanitize", "contrib")
FORBIDDEN_IMPORTS = (
    "mymlfw.train.lora",
    "mymlfw.train.grpo",
    "mymlfw.cloud",
    "mymlfw.engines",
    "torch",
)
BLEND_FORBIDDEN = FORBIDDEN_IMPORTS + ("mymlfw.kernel", "mymlfw.submit")
TRAP_VERDICTS = {"kill", "confirmed-large-gap"}
DEFAULT_PLAYBOOK = (
    "# GRANDMASTER_PLAYBOOK\n\n"
    "Winning probes and killed probes are recorded by `python -m mymlfw archive-contest`.\n"
)


def token_count(text: str) -> int:
    return len(text.split())


def ensure_token_budget(text: str, limit: int = TOKEN_LIMIT) -> None:
    count = token_count(text)
    if count > limit:
        raise MymlfwError(
            "LLMSTXT_TOO_LONG",
            "Keep llms.txt at or under 1500 whitespace-delimited tokens.",
            tokens=count,
            limit=limit,
        )


def _split_llms(text: str) -> str:
    if INDEX_START in text and INDEX_END in text:
        return text.split(INDEX_START, 1)[0].rstrip()
    return text.rstrip()


def _contrib_line(path: Path) -> str:
    doc = ast.get_docstring(ast.parse(path.read_text())) or path.stem
    first = doc.strip().splitlines()[0].strip()
    return f"contrib/{path.name} — {first}"


def llms_index_body(root: Path | None = None) -> str:
    root = root or repo_root()
    lines = [f"recipe {card['id']}: {card['summary']}" for card in load_recipe_cards(root)]
    contrib = root / "src" / "mymlfw" / "contrib"
    if contrib.is_dir():
        for path in sorted(contrib.glob("*.py")):
            if path.name == "__init__.py":
                continue
            lines.append(_contrib_line(path))
    return "\n".join(lines)


def render_llms(head: str, index_body: str) -> str:
    body = index_body.strip("\n")
    return f"{head.rstrip()}\n\n{INDEX_START}\n{body}\n{INDEX_END}\n"


def sync_llms_index(path=None) -> Path:
    """Regenerate the index between markers. Refuse to write past the token cap."""

    path = Path(path) if path else repo_root() / "llms.txt"
    current = path.read_text() if path.exists() else ""
    new = render_llms(_split_llms(current), llms_index_body())
    ensure_token_budget(new)
    if current != new:
        path.write_text(new)
    _mirror_packaged_llms(path)
    return path


def _mirror_packaged_llms(source: Path) -> None:
    checkout = checkout_root()
    if checkout is None or source.resolve() != (checkout / "llms.txt").resolve():
        return
    packaged = Path(__file__).resolve().parent / "resources" / "llms.txt"
    if packaged.parent.is_dir():
        packaged.parent.mkdir(parents=True, exist_ok=True)
        (packaged.parent / "recipes").mkdir(parents=True, exist_ok=True)
        packaged.write_text(source.read_text())


def _normalize_tags(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw = ",".join(str(item) for item in value)
    else:
        raw = str(value or "")
    tags = []
    seen = set()
    for part in raw.split(","):
        tag = part.strip().lower()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return sorted(tags)


def field_notes_path(notes=None) -> Path:
    if notes:
        return Path(notes)
    root = checkout_root() or Path.cwd()
    return root / "recipes" / "memory.db"


def _load_notes(path: Path) -> list[dict]:
    if not path.exists():
        return []
    from mymlfw.rag.store import Store

    store = Store(path)
    try:
        notes = []
        for entry in store.field_notes():
            tags = [part for part in str(entry.get("tags", "")).split(",") if part]
            notes.append(
                {
                    "tags": tags,
                    "rule": entry.get("rule", ""),
                    "evidence": entry.get("evidence", ""),
                }
            )
        return notes
    finally:
        store.close()


def remember(tag: str, rule: str, evidence: str = "", notes=None, db=None) -> dict:
    path = field_notes_path(db or notes)
    tags = _normalize_tags(tag)
    rule = str(rule)
    if not tags:
        raise MymlfwError("MISSING_TAG", "Pass --tag with at least one tag.")
    if not rule.strip():
        raise MymlfwError("MISSING_RULE", "Pass --rule with the note to remember.")
    from mymlfw.rag.store import Store

    store = Store(path)
    try:
        return store.add_field_note(",".join(tags), rule, evidence)
    finally:
        store.close()


def list_recipes(match: str = "", notes_path=None) -> list[dict]:
    needle = match.lower().strip()
    cards = []
    for card in load_recipe_cards():
        haystack = " ".join(
            [str(card.get("id", "")), str(card.get("summary", "")), " ".join(card.get("tags") or [])]
        ).lower()
        if needle and needle not in haystack:
            continue
        cards.append(card)
    notes_file = Path(notes_path) if notes_path else field_notes_path()
    for entry in _load_notes(notes_file):
        tags = [str(item) for item in (entry.get("tags") or [])]
        rule = str(entry.get("rule", ""))
        haystack = f"{' '.join(tags)} {rule}".lower()
        if needle and needle not in haystack:
            continue
        cards.append(
            {
                "id": "field-note",
                "summary": rule,
                "tags": tags,
                "evidence": entry.get("evidence", ""),
            }
        )
    return cards


def show_recipe(recipe_id: str) -> str:
    path = repo_root() / "recipes" / f"{recipe_id}.yaml"
    if not path.is_file():
        raise MymlfwError(
            "RECIPE_NOT_FOUND",
            "Pass a recipe id from python -m mymlfw recipes.",
            recipe=recipe_id,
        )
    return path.read_text()


def _delta(rows: list[dict], row: dict):
    if row.get("cv_delta"):
        return float(row["cv_delta"])
    baseline = next((item for item in rows if item["experiment_id"] == row["baseline_id"]), None)
    if baseline and baseline.get("cv_mean") and row.get("cv_mean"):
        return float(row["cv_mean"]) - float(baseline["cv_mean"])
    return None


def _win_key(rows, row):
    delta = _delta(rows, row)
    if delta is None:
        return (1, 0.0, row["experiment_id"])
    return (0, -delta, row["experiment_id"])


def _trap_key(rows, row):
    delta = _delta(rows, row)
    if delta is None:
        return (1, 0.0, row["experiment_id"])
    return (0, delta, row["experiment_id"])


def _split_archive(rows: list[dict]):
    wins = [row for row in rows if row["verdict"] == "promote-candidate"]
    traps = [row for row in rows if row["verdict"] in TRAP_VERDICTS]
    wins.sort(key=lambda row: _win_key(rows, row))
    traps.sort(key=lambda row: _trap_key(rows, row))
    return wins, traps


def _render_entry(rows, row) -> str:
    delta = _delta(rows, row)
    delta_text = "" if delta is None else f"{delta:.6g}"
    return "\n".join(
        [
            f"### {row['experiment_id']}",
            f"- variable: {row['variable']}",
            f"- cv_mean: {row['cv_mean']}",
            f"- cv_delta: {delta_text}",
            f"- public_score: {row['public_score']}",
            f"- note: {row['note']}",
            "",
        ]
    )


def _render_playbook(preamble: str, rows, wins, traps) -> str:
    parts = [preamble.rstrip(), "", "## proven_wins", ""]
    for row in wins:
        parts.append(_render_entry(rows, row))
    parts.append("## known_traps")
    parts.append("")
    for row in traps:
        parts.append(_render_entry(rows, row))
    return "\n".join(parts).rstrip() + "\n"


def _note(rows, row) -> dict:
    delta = _delta(rows, row)
    return {
        "experiment_id": row["experiment_id"],
        "variable": row["variable"],
        "cv_mean": row.get("cv_mean", ""),
        "cv_delta": "" if delta is None else float(f"{delta:.6g}"),
        "public_score": row.get("public_score", ""),
        "note": row.get("note", ""),
    }


def _note_sort_key(item: dict, descending: bool):
    raw = item.get("cv_delta")
    if raw == "" or raw is None:
        return (1, 0.0, str(item.get("experiment_id", "")))
    value = float(raw)
    return (0, -value if descending else value, str(item.get("experiment_id", "")))


def _merge_notes(existing, incoming, descending: bool) -> list:
    merged = []
    index = {}
    for item in existing:
        if not isinstance(item, dict):
            continue
        key = (item.get("experiment_id"), item.get("variable"))
        index[key] = len(merged)
        merged.append(dict(item))
    for item in incoming:
        key = (item.get("experiment_id"), item.get("variable"))
        if key in index:
            merged[index[key]] = dict(item)
        else:
            index[key] = len(merged)
            merged.append(dict(item))
    merged.sort(key=lambda item: _note_sort_key(item, descending))
    return merged


def _update_recipe(recipe_id: str, rows, wins, traps, recipes_dir=None) -> Path:
    directory = Path(recipes_dir) if recipes_dir else repo_root() / "recipes"
    path = directory / f"{recipe_id}.yaml"
    if not path.is_file():
        raise MymlfwError(
            "RECIPE_NOT_FOUND",
            "Pass a recipe id that matches a file in recipes/.",
            recipe=recipe_id,
        )
    card = yaml.safe_load(path.read_text())
    if not isinstance(card, dict):
        raise MymlfwError(
            "RECIPE_NOT_FOUND",
            "The recipe file must be a YAML mapping.",
            recipe=recipe_id,
        )
    card["proven_wins"] = _merge_notes(card.get("proven_wins") or [], [_note(rows, row) for row in wins], True)
    card["known_traps"] = _merge_notes(card.get("known_traps") or [], [_note(rows, row) for row in traps], False)
    path.write_text(yaml.safe_dump(card, sort_keys=False))
    return path


def archive_contest(ledger, playbook, recipe: str | None = None, recipes_dir=None) -> Path:
    playbook = Path(playbook)
    if "site-packages" in playbook.resolve().parts:
        raise MymlfwError(
            "SITE_PACKAGES",
            "Refusing to write the playbook into site-packages.",
        )
    llms = repo_root() / "llms.txt"
    if llms.exists():
        ensure_token_budget(llms.read_text())
    if recipe:
        directory = Path(recipes_dir) if recipes_dir else repo_root() / "recipes"
        if not (directory / f"{recipe}.yaml").is_file():
            raise MymlfwError(
                "RECIPE_NOT_FOUND",
                "Pass a recipe id that matches a file in recipes/.",
                recipe=recipe,
            )
    rows = load_ledger(ledger)
    wins, traps = _split_archive(rows)
    if playbook.exists():
        current = playbook.read_text()
        preamble = current.split("## proven_wins", 1)[0].rstrip() if "## proven_wins" in current else current.rstrip()
    else:
        preamble = DEFAULT_PLAYBOOK.rstrip()
    playbook.parent.mkdir(parents=True, exist_ok=True)
    playbook.write_text(_render_playbook(preamble, rows, wins, traps))
    if recipe:
        _update_recipe(recipe, rows, wins, traps, recipes_dir=recipes_dir)
    return playbook


DYNAMIC_CALLS = {"__import__", "exec", "eval", "compile", "import_module", "importlib.import_module"}


def _dotted(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def imported_modules(source: str) -> list[str]:
    tree = ast.parse(source)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base:
                names.append(base)
            for alias in node.names:
                names.append(f"{base}.{alias.name}" if base else alias.name)
        elif isinstance(node, ast.Call):
            call = _dotted(node.func)
            if call in DYNAMIC_CALLS or call.endswith(".import_module") or call.endswith(".__import__"):
                names.append(call)
    return names


def forbidden_imports(source: str, category: str) -> list[str]:
    banned = BLEND_FORBIDDEN if category == "blend" else FORBIDDEN_IMPORTS
    found = []
    for name in imported_modules(source):
        if name in DYNAMIC_CALLS or name.endswith(".import_module") or name.endswith(".__import__"):
            found.append(name)
            continue
        for item in banned:
            if name == item or name.startswith(item + "."):
                found.append(name)
                break
    return found


def default_contrib_dir() -> Path:
    return repo_root() / "src" / "mymlfw" / "contrib"


def default_contrib_tests_dir() -> Path:
    return repo_root() / "tests"


def _projected_line(stem: str, source: str) -> str:
    doc = ast.get_docstring(ast.parse(source)) or stem
    first = doc.strip().splitlines()[0].strip()
    return f"contrib/{stem}.py — {first}"


def promote_plugin(plugin, category: str, dest=None, tests_dest=None) -> Path:
    plugin = Path(plugin)
    if category not in CATEGORIES:
        raise MymlfwError(
            "PLUGIN_CATEGORY",
            "Category must be one of: blend, cv, metrics, sanitize, contrib.",
            category=category,
        )
    if not plugin.is_file():
        raise MymlfwError(
            "PLUGIN_NOT_FOUND",
            "Pass the path to the plugin module.",
            plugin=str(plugin),
        )
    test_path = plugin.with_name(f"test_{plugin.stem}.py")
    if not test_path.is_file():
        raise MymlfwError(
            "PLUGIN_TEST_MISSING",
            f"Add {test_path.name} next to the plugin.",
            test=str(test_path),
        )
    source = plugin.read_text()
    test_source = test_path.read_text()
    try:
        blocked = forbidden_imports(source, category) + forbidden_imports(test_source, category)
    except SyntaxError as exc:
        raise MymlfwError("PLUGIN_SYNTAX", "Fix the plugin so it parses.", note=str(exc)) from exc
    if blocked:
        raise MymlfwError(
            "PLUGIN_IMPORT_FORBIDDEN",
            "Remove imports that point upward in the phase DAG.",
            imports=blocked,
        )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        note = (completed.stderr or completed.stdout or "").strip()
        raise MymlfwError(
            "PLUGIN_TEST_FAILED",
            "Fix the sibling pytest file before promoting the plugin.",
            note=note[-800:],
        )
    dest_dir = Path(dest) if dest else default_contrib_dir()
    tests_dir = Path(tests_dest) if tests_dest else default_contrib_tests_dir()
    installing = dest is None or Path(dest).resolve() == default_contrib_dir().resolve()
    llms = repo_root() / "llms.txt"
    if installing and llms.exists():
        current = llms.read_text()
        lines = [line for line in llms_index_body().splitlines() if line]
        extra = _projected_line(plugin.stem, source)
        if extra not in lines:
            lines.append(extra)
        ensure_token_budget(render_llms(_split_llms(current), "\n".join(lines)))
    elif llms.exists():
        ensure_token_budget(llms.read_text())
    dest_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    init = dest_dir / "__init__.py"
    if not init.exists():
        init.write_text(
            '"""Promoted contest plugins.\n\nThis package does not import mymlfw.train.lora.\n"""\n'
        )
    target = dest_dir / f"{plugin.stem}.py"
    test_target = tests_dir / f"test_contrib_{plugin.stem}.py"
    shutil.copyfile(plugin, target)
    shutil.copyfile(test_path, test_target)
    if installing:
        try:
            sync_llms_index(llms)
        except MymlfwError:
            target.unlink(missing_ok=True)
            test_target.unlink(missing_ok=True)
            raise
    return target


def new_contest(name: str, dest) -> Path:
    root = Path(dest) / name
    (root / "ledger").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "configs").mkdir()
    (root / "kernel" / "src").mkdir(parents=True)
    (root / "bin").mkdir()
    (root / "cloud").mkdir()
    (root / "custom_plugins").mkdir()
    header = ",".join(COLUMNS)
    (root / "ledger" / "experiments.csv").write_text(header + "\n")
    (root / "ledger" / "hypotheses.yaml").write_text("probes: []\n")
    (root / "STATUS.md").write_text(f"# {name}\n\nNo public score yet.\n")
    (root / "docs" / "AGENT_HANDOFF.md").write_text(
        f"# {name} handoff\n\nRead llms.txt, then ledger/experiments.csv.\n"
    )
    (root / "llms.txt").write_text((repo_root() / "llms.txt").read_text())
    (root / "configs" / "train.yaml").write_text(
        "peft_type: lora\nrank: 16\nlora_alpha: 32\ntarget_modules:\n  - q_proj\n  - v_proj\n"
    )
    (root / "custom_plugins" / "README.md").write_text(
        "# custom plugins\n\n"
        "One plugin module plus `test_<name>.py` beside it.\n"
        "CPU-only. No network.\n"
    )
    metadata = kernel_metadata(f"local/{name}", f"{name}.ipynb", dataset_sources=[])
    (root / "kernel" / "kernel-metadata.json").write_text(
        __import__("json").dumps(metadata, indent=1, sort_keys=True) + "\n"
    )
    (root / "kernel" / "src" / "cell0_overview.md").write_text(f"# {name}\n")
    (root / "kernel" / "src" / "cell1_stage.py").write_text(
        "PAYLOAD = __PAYLOAD_B64__\nHASH = __PAYLOAD_SHA256__\n"
    )
    (root / "kernel" / "src" / "cell2_run.py").write_text(CELL2_TEMPLATE)
    (root / "kernel" / "src" / "cell3_fuse.py").write_text("print('fuse')\n")
    script = (
        "#!/bin/sh\n"
        "exec \"${PYTHON:-python3}\" -m mymlfw preflight --require-scale-report \"$@\"\n"
    )
    bin_path = root / "bin" / "preflight_submit.sh"
    bin_path.write_text(script)
    bin_path.chmod(0o755)
    launch = root / "cloud" / "launch.sh"
    launch.write_text(
        "#!/bin/sh\n"
        "exec \"${PYTHON:-python3}\" -m mymlfw cloud launch \\\n"
        f"  --project {name} --role primary --gpu T4 \\\n"
        "  --command \"python train.py\" \\\n"
        "  --idle-kill 30 --max-runtime 120 \\\n"
        "  --ledger ledger/experiments.csv \\\n"
        "  --experiment-id \"$1\" --baseline-id \"$2\" --variable \"$3\" \\\n"
        "  --band-low \"$4\" --band-high \"$5\" \\\n"
        "  --out cloud/rendered.sh\n"
    )
    launch.chmod(0o755)
    (root / "engine.py").write_text(
        "from mymlfw.engines import PredictorProtocol, TextBlendEngine\n\n"
        "class ContestEngine(TextBlendEngine):\n"
        "    classes = []\n\n"
        "    def predict_row(self, row):\n"
        "        raise NotImplementedError\n\n"
        "    def predict(self, frame):\n"
        "        return self.run(frame, self.predict_row, self.classes)\n"
    )
    return root
