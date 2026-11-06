"""Notebook chunker: hypothesis + code + truncated output as one unit.

AST ``def``/``class`` tags land on each unit. Must not import ``mymlfw.train``
or engines.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NotebookUnit:
    """Atomic retrieval unit: markdown hypothesis + code + truncated output."""

    unit_index: int
    hypothesis_md: str
    code: str
    output_preview: str
    ast_tags: list[str] = field(default_factory=list)
    cell_indices: list[int] = field(default_factory=list)


_OUTPUT_CAP = 2000


def _truncate(text: str, cap: int = _OUTPUT_CAP) -> str:
    if len(text) <= cap:
        return text
    return text[: cap - 3] + "..."


def _ast_tags(code: str) -> list[str]:
    tags: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return tags
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            tags.append(f"def:{node.name}")
        elif isinstance(node, ast.ClassDef):
            tags.append(f"class:{node.name}")
    return tags


def _cell_source(cell: dict[str, Any]) -> str:
    src = cell.get("source", "")
    if isinstance(src, list):
        return "".join(src)
    return str(src)


def _cell_output_text(cell: dict[str, Any]) -> str:
    chunks: list[str] = []
    for out in cell.get("outputs") or []:
        if not isinstance(out, dict):
            continue
        text = out.get("text")
        if isinstance(text, list):
            chunks.append("".join(text))
        elif isinstance(text, str):
            chunks.append(text)
        data = out.get("data") or {}
        if isinstance(data, dict) and "text/plain" in data:
            plain = data["text/plain"]
            if isinstance(plain, list):
                chunks.append("".join(plain))
            else:
                chunks.append(str(plain))
    return _truncate("\n".join(chunks).strip())


def chunk_notebook_dict(nb: dict[str, Any]) -> list[NotebookUnit]:
    """Group preceding markdown + code (+ outputs) into atomic units."""
    cells = nb.get("cells") or []
    units: list[NotebookUnit] = []
    pending_md: list[str] = []
    pending_idx: list[int] = []

    for idx, cell in enumerate(cells):
        ctype = cell.get("cell_type")
        if ctype == "markdown":
            pending_md.append(_cell_source(cell).strip())
            pending_idx.append(idx)
            continue
        if ctype != "code":
            continue
        code = _cell_source(cell)
        hypothesis = "\n\n".join(m for m in pending_md if m).strip()
        unit = NotebookUnit(
            unit_index=len(units),
            hypothesis_md=hypothesis,
            code=code,
            output_preview=_cell_output_text(cell),
            ast_tags=_ast_tags(code),
            cell_indices=[*pending_idx, idx],
        )
        units.append(unit)
        pending_md.clear()
        pending_idx.clear()
    return units


def chunk_notebook_path(path: str | Path) -> list[NotebookUnit]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("notebook_root_must_be_object")
    return chunk_notebook_dict(data)
