"""Integrity / leakage gate for advise + mission briefs (Phase E)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_LEAK_PATTERNS = (
    re.compile(r"mongodb(\+srv)?://", re.I),
    re.compile(r"MYMLFW_KEK_", re.I),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----"),
)


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    reasons: tuple[str, ...]


def check_text_integrity(text: str) -> IntegrityResult:
    reasons: list[str] = []
    for pat in _LEAK_PATTERNS:
        if pat.search(text or ""):
            reasons.append(f"secret_pattern:{pat.pattern[:32]}")
    if "\x00" in (text or ""):
        reasons.append("nul_byte")
    return IntegrityResult(ok=not reasons, reasons=tuple(reasons))


def scrub_secrets(text: str) -> str:
    out = text or ""
    for pat in _LEAK_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out.replace("\x00", "")
