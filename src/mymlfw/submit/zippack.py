"""Reproducible zip packing. Forbidden paths are left out of the archive."""

from __future__ import annotations

import fnmatch
import hashlib
import zipfile
from pathlib import Path

FORBIDDEN = (
    ".env*",
    "*.pem",
    "*.key",
    ".git/*",
    "__pycache__/*",
    "*.pyc",
    ".DS_Store",
    "*secret*",
    "*credentials*",
    "*id_rsa*",
    "*id_dsa*",
    "*id_ed25519*",
    "*id_ecdsa*",
)


def _forbidden(relative: str) -> bool:
    folded_rel = relative.lower()
    folded_name = Path(relative).name.lower()
    for pattern in FORBIDDEN:
        folded = pattern.lower()
        if fnmatch.fnmatch(folded_rel, folded) or fnmatch.fnmatch(folded_name, folded):
            return True
    return False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def zip_bundle(source_dir, out_zip, max_unpacked: int = 3 * 1024**3) -> dict:
    source_dir = Path(source_dir)
    files = []
    skipped = []
    unpacked = 0
    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_dir).as_posix()
        if _forbidden(relative):
            skipped.append(relative)
            continue
        unpacked += path.stat().st_size
        files.append((relative, path))
    if unpacked > max_unpacked:
        from mymlfw.errors import MymlfwError

        raise MymlfwError("ZIP_TOO_LARGE", "The unpacked bundle exceeds the size cap.", unpacked=unpacked)
    files.sort(key=lambda item: item[0])
    out_zip = Path(out_zip)
    members = {}
    with zipfile.ZipFile(out_zip, "w") as archive:
        for relative, path in files:
            data = path.read_bytes()
            info = zipfile.ZipInfo(filename=relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0
            archive.writestr(info, data)
            members[relative] = _sha256(data)
    digest = _sha256(out_zip.read_bytes())
    return {"sha256": digest, "members": members, "skipped": skipped}
