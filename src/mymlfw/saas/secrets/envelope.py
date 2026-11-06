"""Envelope encrypt for RunPod/AWS credential blobs (AES-256-GCM + KEK).

Ciphertext is ``bytes`` (binData) — never hex strings at rest. Production
requires ``MYMLFW_KEK_V{n}`` when ``MYMLFW_ENV`` is prod or ``MYMLFW_REQUIRE_KEK=1``.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Final

DEFAULT_KEK_VERSION: Final[int] = 1
CIPHER_ALG: Final[str] = "aes-256-gcm"
# Legacy XOR stream from Wave-1 stub — open only, never seal.
_LEGACY_CIPHER_ALG: Final[str] = "aes-256-gcm-stub"


class EnvelopeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class EnvelopeBlob:
    """Sealed secret material — do not return ``ciphertext`` via MCP/API."""

    ciphertext: bytes
    kek_version: int = DEFAULT_KEK_VERSION
    cipher_alg: str = CIPHER_ALG
    nonce: bytes = b""

    def public_meta(self) -> dict[str, int | str]:
        return {
            "kek_version": self.kek_version,
            "cipher_alg": self.cipher_alg,
            "ciphertext_len": len(self.ciphertext),
        }


def current_kek_version() -> int:
    raw = os.environ.get("MYMLFW_KEK_VERSION", "").strip()
    if not raw:
        return DEFAULT_KEK_VERSION
    try:
        return max(1, int(raw))
    except ValueError as exc:
        raise EnvelopeError("invalid_kek_version", "MYMLFW_KEK_VERSION must be int") from exc


def _allow_dev_kek_fallback() -> bool:
    """Dev/test only. Production / MYMLFW_REQUIRE_KEK=1 must set MYMLFW_KEK_V{n}."""
    require = os.environ.get("MYMLFW_REQUIRE_KEK", "").strip().lower()
    if require in {"1", "true", "yes", "on"}:
        return False
    env = os.environ.get("MYMLFW_ENV", "dev").strip().lower()
    return env not in {"prod", "production"}


def _kek_material(version: int) -> bytes:
    env_key = f"MYMLFW_KEK_V{version}"
    material = os.environ.get(env_key, "").encode("utf-8")
    if not material:
        if not _allow_dev_kek_fallback():
            raise EnvelopeError(
                "kek_missing",
                f"Set {env_key} (or unset MYMLFW_REQUIRE_KEK / use non-prod MYMLFW_ENV)",
            )
        # Deterministic local/dev fallback — never ship as production KEK.
        material = f"mymlfw-dev-kek-v{version}".encode("utf-8")
    return hashlib.sha256(material).digest()


def seal_secret(plaintext: bytes | str, *, kek_version: int | None = None) -> EnvelopeBlob:
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    version = kek_version if kek_version is not None else current_kek_version()
    nonce = secrets.token_bytes(12)
    key = _kek_material(version)
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise EnvelopeError(
            "crypto_missing",
            "pip install cryptography (saas extra) for AES-256-GCM envelope",
        ) from exc
    # ciphertext || tag (AESGCM.encrypt appends 16-byte tag)
    ct = AESGCM(key).encrypt(nonce, plaintext, associated_data=None)
    return EnvelopeBlob(ciphertext=ct, kek_version=version, cipher_alg=CIPHER_ALG, nonce=nonce)


def open_secret(blob: EnvelopeBlob) -> bytes:
    key = _kek_material(blob.kek_version)
    if blob.cipher_alg == CIPHER_ALG:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise EnvelopeError(
                "crypto_missing",
                "pip install cryptography (saas extra) for AES-256-GCM envelope",
            ) from exc
        try:
            return AESGCM(key).decrypt(blob.nonce, blob.ciphertext, associated_data=None)
        except Exception as exc:  # noqa: BLE001 — InvalidTag etc.
            raise EnvelopeError("decrypt_failed", "AES-GCM decrypt failed") from exc
    if blob.cipher_alg == _LEGACY_CIPHER_ALG:
        # One-way migration path for secrets sealed before AES-GCM.
        stream = hashlib.sha256(key + blob.nonce).digest()
        return bytes(b ^ stream[i % len(stream)] for i, b in enumerate(blob.ciphertext))
    raise EnvelopeError("unsupported_cipher", f"cipher_alg={blob.cipher_alg}")
