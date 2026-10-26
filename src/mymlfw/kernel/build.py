"""Build a four-cell notebook with a gzip payload whose mtime is zero."""

from __future__ import annotations

import ast
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path

from mymlfw.errors import MymlfwError, PayloadTooLargeError

MAX_PAYLOAD_BYTES = 512_000
CELL_NAMES = ("cell0_overview.md", "cell1_stage.py", "cell2_run.py", "cell3_fuse.py")


def gzip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, filename="") as handle:
        handle.write(data)
    return buffer.getvalue()


def kernel_metadata(
    kernel_id: str,
    code_file: str,
    *,
    enable_gpu: bool = True,
    dataset_sources=None,
    model_sources=None,
    competition_sources=None,
) -> dict:
    return {
        "code_file": code_file,
        "competition_sources": list(competition_sources or []),
        "dataset_sources": list(dataset_sources or []),
        "enable_gpu": bool(enable_gpu),
        "enable_internet": False,
        "id": kernel_id,
        "kernel_type": "notebook",
        "language": "python",
        "model_sources": list(model_sources or []),
        "title": kernel_id.split("/")[-1],
    }


def _code_cell(source: str) -> dict:
    if not source.endswith("\n"):
        source += "\n"
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def _md_cell(source: str) -> dict:
    if not source.endswith("\n"):
        source += "\n"
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def build_notebook(src_dir, out_nb, payload_files) -> dict:
    src_dir = Path(src_dir)
    raw = {}
    total = 0
    for relative in payload_files:
        if relative.endswith(".npz") or "weight" in Path(relative).name.lower():
            raise MymlfwError(
                "PAYLOAD_KIND",
                "Weights and npz files are dataset sources, not notebook payloads.",
                file=relative,
            )
        data = (src_dir / relative).read_bytes()
        if relative.endswith(".py"):
            ast.parse(data.decode("utf-8"), filename=relative)
        total += len(data)
        raw[relative] = data
    if total > MAX_PAYLOAD_BYTES:
        raise PayloadTooLargeError(total)
    compressed = {relative: gzip_bytes(data) for relative, data in raw.items()}
    encoded = {relative: base64.b64encode(blob).decode("ascii") for relative, blob in compressed.items()}
    hashes = {relative: hashlib.sha256(data).hexdigest() for relative, data in raw.items()}
    cell1 = (src_dir / "cell1_stage.py").read_text()
    cell1 = cell1.replace("__PAYLOAD_B64__", json.dumps(encoded, sort_keys=True))
    cell1 = cell1.replace("__PAYLOAD_SHA256__", json.dumps(hashes, sort_keys=True))
    cells = [
        _md_cell((src_dir / "cell0_overview.md").read_text()),
        _code_cell(cell1),
        _code_cell((src_dir / "cell2_run.py").read_text()),
        _code_cell((src_dir / "cell3_fuse.py").read_text()),
    ]
    for cell in cells[1:]:
        ast.parse("".join(cell["source"]))
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    text = json.dumps(notebook, indent=1, sort_keys=True) + "\n"
    out_nb = Path(out_nb)
    out_nb.write_text(text)
    manifest = {
        "notebook_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "payload_b64": encoded,
        "payload_sha256": hashes,
    }
    manifest_path = out_nb.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def extract_payload(manifest_path) -> dict[str, bytes]:
    document = json.loads(Path(manifest_path).read_text())
    out = {}
    for relative, blob in document["payload_b64"].items():
        raw = base64.b64decode(blob)
        out[relative] = gzip.decompress(raw)
        if raw[4:8] != b"\x00\x00\x00\x00":
            raise MymlfwError("GZIP_MTIME", "Payload gzip mtime must be 0.", file=relative)
    return out
