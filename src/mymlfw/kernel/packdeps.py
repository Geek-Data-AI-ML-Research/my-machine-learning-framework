"""Offline wheel command for a Kaggle kernel. Dry-run does not download."""

from __future__ import annotations

from pathlib import Path


def pack_deps(requirements, out_dir, dry_run: bool = True) -> dict:
    requirements = Path(requirements)
    out_dir = Path(out_dir)
    cmd = (
        f"pip download -r {requirements} -d {out_dir} "
        "--platform manylinux2014_x86_64 --python-version 310 --only-binary=:all:"
    )
    snippet = f"pip install --no-index --find-links={out_dir} -r {requirements}"
    plan = {"cmd": cmd, "snippet": snippet, "dry_run": dry_run}
    if dry_run:
        return plan
    from mymlfw.errors import MymlfwError

    raise MymlfwError(
        "PACK_DEPS_LIVE",
        "Re-run with --dry-run. Live wheel downloads are outside the test suite.",
    )
