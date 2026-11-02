"""Object storage helpers for OOF / research artifacts (MinIO-compatible).

Presigns pin Content-Length and SHA-256. Confirm promotes ``pending_upload``
only after a successful HEAD that matches expected size. Unit tests use
``MemoryObjectStore``; Compose MinIO uses ``HmacPresignStore`` until boto3
lands behind the optional saas extra.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import quote, urlencode


@dataclass(frozen=True)
class PresignPut:
    url: str
    object_key: str
    expires_at: datetime
    headers: dict[str, str]


@dataclass(frozen=True)
class HeadResult:
    content_length: int
    etag: str | None
    exists: bool = True


class ObjectStore(Protocol):
    def presign_put(
        self,
        object_key: str,
        *,
        content_length: int,
        content_sha256: str,
        expires_in: timedelta = timedelta(hours=2),
        content_disposition: str = "attachment",
    ) -> PresignPut: ...

    def head(self, object_key: str) -> HeadResult | None: ...

    def put_bytes(self, object_key: str, body: bytes, *, etag: str | None = None) -> HeadResult: ...


@dataclass
class MemoryObjectStore:
    """In-process store for unit tests (simulates MinIO HEAD/PUT)."""

    objects: dict[str, dict[str, Any]] = field(default_factory=dict)
    base_url: str = "https://minio.test/mymlfw"

    def presign_put(
        self,
        object_key: str,
        *,
        content_length: int,
        content_sha256: str,
        expires_in: timedelta = timedelta(hours=2),
        content_disposition: str = "attachment",
    ) -> PresignPut:
        expires_at = datetime.now(UTC) + expires_in
        qs = urlencode(
            {
                "X-Amz-Expires": str(int(expires_in.total_seconds())),
                "X-Amz-SignedHeaders": "content-length;x-amz-checksum-sha256",
                "X-Mymlfw-Pin-Length": str(content_length),
                "X-Mymlfw-Pin-SHA256": content_sha256,
            }
        )
        return PresignPut(
            url=f"{self.base_url}/{quote(object_key, safe='/')}?{qs}",
            object_key=object_key,
            expires_at=expires_at,
            headers={
                "Content-Length": str(content_length),
                "x-amz-checksum-sha256": content_sha256,
                "Content-Disposition": content_disposition,
            },
        )

    def head(self, object_key: str) -> HeadResult | None:
        obj = self.objects.get(object_key)
        if obj is None:
            return None
        return HeadResult(
            content_length=int(obj["content_length"]),
            etag=obj.get("etag"),
            exists=True,
        )

    def put_bytes(self, object_key: str, body: bytes, *, etag: str | None = None) -> HeadResult:
        digest = hashlib.sha256(body).hexdigest()
        tag = etag or f'"{digest[:16]}"'
        self.objects[object_key] = {
            "body": body,
            "content_length": len(body),
            "sha256": digest,
            "etag": tag,
        }
        return HeadResult(content_length=len(body), etag=tag, exists=True)


@dataclass
class HmacPresignStore:
    """SigV4-free HMAC stub for Compose without boto3.

    PUT bodies are not uploaded through this class — runners hit the returned
    URL (MinIO gateway or a test double). ``head`` uses an optional probe hook.
    """

    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    _probe: dict[str, HeadResult] = field(default_factory=dict)

    def presign_put(
        self,
        object_key: str,
        *,
        content_length: int,
        content_sha256: str,
        expires_in: timedelta = timedelta(hours=2),
        content_disposition: str = "attachment",
    ) -> PresignPut:
        expires_at = datetime.now(UTC) + expires_in
        exp = int(expires_at.timestamp())
        payload = f"PUT\n{self.bucket}\n{object_key}\n{content_length}\n{content_sha256}\n{exp}"
        sig = hmac.new(
            self.secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        qs = urlencode(
            {
                "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
                "X-Amz-Credential": f"{self.access_key}/{time.strftime('%Y%m%d')}/{self.region}/s3/aws4_request",
                "X-Amz-Date": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
                "X-Amz-Expires": str(int(expires_in.total_seconds())),
                "X-Amz-Signature": sig,
                "X-Mymlfw-Pin-Length": str(content_length),
                "X-Mymlfw-Pin-SHA256": content_sha256,
            }
        )
        base = self.endpoint.rstrip("/")
        return PresignPut(
            url=f"{base}/{self.bucket}/{quote(object_key, safe='/')}?{qs}",
            object_key=object_key,
            expires_at=expires_at,
            headers={
                "Content-Length": str(content_length),
                "x-amz-checksum-sha256": content_sha256,
                "Content-Disposition": content_disposition,
            },
        )

    def head(self, object_key: str) -> HeadResult | None:
        return self._probe.get(object_key)

    def put_bytes(self, object_key: str, body: bytes, *, etag: str | None = None) -> HeadResult:
        result = HeadResult(
            content_length=len(body),
            etag=etag or f'"{hashlib.sha256(body).hexdigest()[:16]}"',
            exists=True,
        )
        self._probe[object_key] = result
        return result

    def record_head(self, object_key: str, result: HeadResult) -> None:
        """Test / worker hook when a real MinIO HEAD is mocked."""
        self._probe[object_key] = result


PENDING_UPLOAD_TTL = timedelta(hours=2)


def object_key_for_oof(
    *,
    workspace_id: str,
    project_id: str,
    oof_id: str,
    filename: str,
) -> str:
    safe_name = filename.replace("/", "_").replace("..", "_")
    return f"{workspace_id}/{project_id}/oof/{oof_id}/{safe_name}"
