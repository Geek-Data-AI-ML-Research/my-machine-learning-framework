#!/usr/bin/env python3
"""AST / contract anti-drift checks for Campaign SaaS (CI + pre-commit)."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "mymlfw"

DB_ALLOW = SRC / "saas" / "db"
API_DIR = SRC / "api"
MCP_DIR = SRC / "mcp"
SAAS_DIR = SRC / "saas"
OPENAPI_PATH = ROOT / "contracts" / "openapi.json"


class DriftViolation(Exception):
    pass


def _iter_py(root: Path):
    if not root.exists():
        return
    for path in root.rglob("*.py"):
        if path.name == "AGENTS.md":
            continue
        yield path


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def check_no_raw_db_outside_saas_db() -> list[str]:
    errors: list[str] = []
    forbidden_names = {"AsyncDatabase", "AsyncMongoClient"}
    for path in _iter_py(SRC):
        if DB_ALLOW in path.parents or path.parent == DB_ALLOW:
            continue
        # client re-export helpers may mention names in strings only — scan AST.
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("pymongo") or mod.startswith("bson"):
                    if "mcp" in path.parts or path.parts[-2:] == ("saas", "rag"):
                        # rag may not import pymongo at all in Wave 1; flag mcp always.
                        if "mcp" in path.parts:
                            errors.append(f"{path}: MCP must not import {mod}")
                for alias in node.names:
                    if alias.name in forbidden_names and DB_ALLOW not in path.parents:
                        # Allow type comments in api deps only via string annotations later.
                        if "saas/db" not in str(path):
                            # api may import AsyncMongoClient only through saas.db — flag direct.
                            if mod.startswith("pymongo"):
                                errors.append(
                                    f"{path}:{node.lineno}: raw {alias.name} import outside saas/db"
                                )
            if isinstance(node, ast.Attribute) and isinstance(node.attr, str):
                if node.attr == "raw_db":
                    errors.append(f"{path}:{node.lineno}: .raw_db access forbidden")
            if isinstance(node, ast.Subscript):
                # db["experiments"] pattern: Name/Attribute load of db then Str
                pass
    # Broader text scan for AsyncDatabase / .raw_db[ outside saas/db
    for path in _iter_py(SRC):
        if DB_ALLOW in path.parents or path.parent == DB_ALLOW:
            continue
        text = path.read_text(encoding="utf-8")
        if "AsyncDatabase" in text and "TYPE_CHECKING" not in text:
            # allow quoting in AGENTS — not py
            errors.append(f"{path}: AsyncDatabase reference outside saas/db")
        if ".raw_db[" in text:
            errors.append(f"{path}: .raw_db[ outside saas/db")
    return errors


def check_no_torch_in_control_plane() -> list[str]:
    errors: list[str] = []
    for root in (API_DIR, MCP_DIR, SAAS_DIR):
        for path in _iter_py(root):
            # Documented exception: none in Wave 1; train extra stays outside these trees.
            tree = _parse(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "torch" or alias.name.startswith("torch."):
                            errors.append(f"{path}:{node.lineno}: torch import forbidden")
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod == "torch" or mod.startswith("torch."):
                        errors.append(f"{path}:{node.lineno}: torch import forbidden")
    return errors


def check_mcp_no_mongo() -> list[str]:
    errors: list[str] = []
    mongo_markers = (
        "AsyncMongoClient",
        "AsyncDatabase",
        "ScopedCollection",
        "pymongo",
        "find_one",
        "aggregate(",
        "insert_one",
        "create_saas_mongo_client",
    )
    for path in _iter_py(MCP_DIR):
        text = path.read_text(encoding="utf-8")
        for marker in mongo_markers:
            if marker in text:
                errors.append(f"{path}: MCP must not contain Mongo marker {marker!r}")
    return errors


def check_openapi_drift() -> list[str]:
    """Stub: ensure committed openapi.json exists and lists core paths."""
    errors: list[str] = []
    if not OPENAPI_PATH.exists():
        errors.append(f"missing {OPENAPI_PATH}")
        return errors
    try:
        data = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"openapi.json invalid: {exc}")
        return errors
    paths = data.get("paths") or {}
    for required in ("/health", "/v1/auth/login", "/v1/auth/register", "/v1/me"):
        if required not in paths:
            errors.append(f"openapi.json missing path {required}")
    # schemas.py MetricSample / FiniteMetric must forbid inf/nan — reflected as note
    if "components" not in data:
        errors.append("openapi.json missing components")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        choices=("all", "db", "torch", "mcp", "openapi"),
        default="all",
    )
    args = parser.parse_args(argv)
    errors: list[str] = []
    if args.check in ("all", "db"):
        errors.extend(check_no_raw_db_outside_saas_db())
    if args.check in ("all", "torch"):
        errors.extend(check_no_torch_in_control_plane())
    if args.check in ("all", "mcp"):
        errors.extend(check_mcp_no_mongo())
    if args.check in ("all", "openapi"):
        errors.extend(check_openapi_drift())
    if errors:
        print("anti-drift violations:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("anti-drift: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
