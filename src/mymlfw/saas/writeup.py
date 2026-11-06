"""Competition writeup generator (attribution table from credits)."""

from __future__ import annotations

from typing import Any


def render_writeup(
    *,
    title: str,
    summary: str,
    credits: list[dict[str, Any]] | None = None,
) -> str:
    lines = [f"# {title}", "", summary.strip(), "", "## Attribution", ""]
    lines.append("| name | spdx | authors |")
    lines.append("| --- | --- | --- |")
    for c in credits or []:
        authors = ", ".join(c.get("authors") or [])
        lines.append(f"| {c.get('name')} | {c.get('spdx')} | {authors} |")
    return "\n".join(lines) + "\n"
