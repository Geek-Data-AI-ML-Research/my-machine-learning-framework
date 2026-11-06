"""Minimal envelope vault stubs (``kek_version`` on upstream-secret blobs)."""

from mymlfw.saas.secrets.envelope import (
    EnvelopeBlob,
    EnvelopeError,
    current_kek_version,
    open_secret,
    seal_secret,
)

__all__ = [
    "EnvelopeBlob",
    "EnvelopeError",
    "current_kek_version",
    "open_secret",
    "seal_secret",
]
