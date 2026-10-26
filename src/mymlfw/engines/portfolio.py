"""Pack only members whose bytes match a checker receipt."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from mymlfw.errors import MymlfwError


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PortfolioEngine:
    def prepare(self, frame):
        return frame

    def package(self, members: list[dict], out_zip) -> dict:
        accepted = []
        seen = set()
        for member in members:
            path = Path(member["path"])
            receipt = str(member.get("receipt_sha256", ""))
            digest = _sha256(path)
            if receipt and receipt == digest:
                if path.name in seen:
                    raise MymlfwError(
                        "DUPLICATE_MEMBER",
                        "Rename portfolio members so each zip entry name is unique.",
                        name=path.name,
                    )
                seen.add(path.name)
                accepted.append((path.name, path, digest))
        if not accepted:
            raise MymlfwError(
                "MISSING_RECEIPT",
                "A portfolio member is packed only when its checker receipt matches the file hash.",
            )
        accepted.sort(key=lambda item: item[0])
        out_zip = Path(out_zip)
        with zipfile.ZipFile(out_zip, "w") as archive:
            for name, path, _digest in accepted:
                info = zipfile.ZipInfo(filename=name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, path.read_bytes())
        return {"members": [name for name, _path, _digest in accepted]}
