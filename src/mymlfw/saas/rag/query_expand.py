"""Query expander — goal text + error_slices feed slice-targeted retrieval."""

from __future__ import annotations

from typing import Any, Iterable


def expand_query(
    base_query: str,
    *,
    error_slices: Iterable[dict[str, Any] | str] | None = None,
    goal_titles: Iterable[str] | None = None,
) -> str:
    """Append slice / goal tokens so retrieve is not goal-title-only."""
    parts = [base_query.strip()] if base_query and base_query.strip() else []
    for title in goal_titles or []:
        t = str(title or "").strip()
        if t and t not in parts:
            parts.append(t)
    for slice_row in error_slices or []:
        if isinstance(slice_row, str):
            label = slice_row.strip()
        else:
            label = str(
                slice_row.get("label")
                or slice_row.get("slice")
                or slice_row.get("name")
                or ""
            ).strip()
            hint = str(slice_row.get("hint") or slice_row.get("description") or "").strip()
            if hint:
                label = f"{label} {hint}".strip()
        if label:
            parts.append(label)
    return " ".join(parts).strip() or "next experiment dead ends and promoted levers"
