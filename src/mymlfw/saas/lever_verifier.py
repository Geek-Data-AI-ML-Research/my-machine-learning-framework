"""Lever mutation gate — structural checks always; optional LLM judge (E2).

Autopilot / propose_lever must call this — never cosine similarity alone.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal

# One-variable levers only — deny shell / multi-statement payloads.
_SHELL_MARKERS = (
    "&&",
    "||",
    ";",
    "`",
    "$(",
    "\n",
    "rm -",
    "curl ",
    "wget ",
    "/bin/",
    "os.system",
    "subprocess",
)
# One lever: identifier or id=value (no whitespace / shell metacharacters).
_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,64}(=[A-Za-z0-9_.\-+:/]{0,64})?$")


@dataclass(frozen=True)
class LeverVerifierResult:
    """Gate outcome for a proposed one-variable mutation."""

    allowed: bool
    status: Literal["passed", "deferred_llm", "rejected"]
    reason: str
    deferred_to_llm: bool = False


def verify_lever_mutation(
    *,
    variable: str,
    parent_node_id: str | None = None,
    mode: str | None = None,
    context: dict[str, Any] | None = None,
) -> LeverVerifierResult:
    """Production gate: reject empty / multi-var / shell-shaped levers.

    When ``MYMLFW_LEVER_LLM=1`` and ``mymlfw.saas.llm`` is importable, defer to
    the LLM judge (Phase E2). Until then structural pass is authoritative —
    never a silent always-allow stub.
    """
    _ = parent_node_id, mode
    name = (variable or "").strip()
    if not name:
        return LeverVerifierResult(
            allowed=False,
            status="rejected",
            reason="empty_variable",
            deferred_to_llm=False,
        )
    if not _VAR_RE.match(name):
        return LeverVerifierResult(
            allowed=False,
            status="rejected",
            reason="invalid_variable_shape",
            deferred_to_llm=False,
        )
    lowered = name.lower()
    for marker in _SHELL_MARKERS:
        if marker in lowered or marker in name:
            return LeverVerifierResult(
                allowed=False,
                status="rejected",
                reason=f"shell_marker:{marker.strip()}",
                deferred_to_llm=False,
            )
    ctx = context or {}
    proposed = str(ctx.get("proposed_value") or ctx.get("cli_steps") or "")
    if proposed:
        for marker in _SHELL_MARKERS:
            if marker in proposed:
                return LeverVerifierResult(
                    allowed=False,
                    status="rejected",
                    reason=f"payload_shell_marker:{marker.strip()}",
                    deferred_to_llm=False,
                )
        # AGENTS: LLMs must not emit raw bash cli_steps — template_id only.
        if "cli_steps" in ctx and isinstance(ctx.get("cli_steps"), str):
            return LeverVerifierResult(
                allowed=False,
                status="rejected",
                reason="raw_cli_steps_forbidden",
                deferred_to_llm=False,
            )

    use_llm = os.environ.get("MYMLFW_LEVER_LLM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if use_llm:
        try:
            from mymlfw.saas import llm as llm_mod  # type: ignore[attr-defined]
        except ImportError:
            return LeverVerifierResult(
                allowed=False,
                status="rejected",
                reason="lever_llm_unavailable",
                deferred_to_llm=True,
            )
        judge = getattr(llm_mod, "judge_lever_mutation", None)
        if judge is None:
            return LeverVerifierResult(
                allowed=False,
                status="rejected",
                reason="lever_llm_judge_missing",
                deferred_to_llm=True,
            )
        return judge(
            variable=name,
            parent_node_id=parent_node_id,
            mode=mode,
            context=ctx,
        )

    return LeverVerifierResult(
        allowed=True,
        status="passed",
        reason="structural_ok",
        deferred_to_llm=False,
    )
