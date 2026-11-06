"""Human-only elicitation confirm (403 for agent/PAT)."""

from __future__ import annotations


class ElicitationError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def confirm_elicitation(*, actor: str, action: str) -> dict[str, str]:
    if actor in {"agent", "pat", "mcp"}:
        raise ElicitationError("human_only")
    if actor not in {"owner", "member", "human"}:
        raise ElicitationError("human_only")
    return {"status": "confirmed", "action": action, "actor": actor}
