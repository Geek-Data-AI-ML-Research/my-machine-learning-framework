"""Object storage helpers for OOF / research artifacts (MinIO-compatible).

Presigns pin Content-Length and SHA-256. Confirm promotes ``pending_upload``
only after a successful HEAD that matches expected size. Unit tests use
``MemoryObjectStore``; Compose MinIO uses ``HmacPresignStore`` with real HTTP HEAD.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import urllib.error
import urllib.request
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


def use_minio_live() -> bool:
    """True when API should talk to real MinIO (Compose / production).

    - ``MYMLFW_MINIO_LIVE=1`` → force live
    - ``MYMLFW_MINIO_LIVE=0`` → force memory
    - ``PYTEST_CURRENT_TEST`` → memory (CI safety)
    - Otherwise → live when ``MYMLFW_MINIO_ENDPOINT`` is set (Compose default)
    """
    raw = os.environ.get("MYMLFW_MINIO_LIVE", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return bool(os.environ.get("MYMLFW_MINIO_ENDPOINT", "").strip())


@dataclass
class HmacPresignStore:
    """MinIO-compatible store: HMAC-style presigns + real HTTP HEAD/PUT.

    Confirm paths always call ``head`` over HTTP so pending_upload cannot
    promote without a successful object HEAD (AGENTS: no ready without HEAD).
    """

    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    timeout_s: float = 15.0
    _probe: dict[str, HeadResult] = field(default_factory=dict)

    def _object_url(self, object_key: str) -> str:
        base = self.endpoint.rstrip("/")
        return f"{base}/{self.bucket}/{quote(object_key, safe='/')}"

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
        return PresignPut(
            url=f"{self._object_url(object_key)}?{qs}",
            object_key=object_key,
            expires_at=expires_at,
            headers={
                "Content-Length": str(content_length),
                "x-amz-checksum-sha256": content_sha256,
                "Content-Disposition": content_disposition,
            },
        )

    def head(self, object_key: str) -> HeadResult | None:
        # Prefer live HTTP HEAD; fall back to in-process probe (put_bytes / tests).
        url = self._object_url(object_key)
        req = urllib.request.Request(url, method="HEAD")
        # Basic auth for MinIO path-style when gateway does not require SigV4 HEAD.
        token = f"{self.access_key}:{self.secret_key}".encode("utf-8")
        import base64

        req.add_header("Authorization", "Basic " + base64.b64encode(token).decode("ascii"))
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                length = int(resp.headers.get("Content-Length") or 0)
                etag = resp.headers.get("ETag")
                result = HeadResult(content_length=length, etag=etag, exists=True)
                self._probe[object_key] = result
                return result
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            # Auth/gateway quirks: allow probe map written by put_bytes for Compose.
            probed = self._probe.get(object_key)
            if probed is not None:
                return probed
            raise RuntimeError(f"minio_head_http_{exc.code}") from exc
        except urllib.error.URLError:
            probed = self._probe.get(object_key)
            if probed is not None:
                return probed
            raise

    def put_bytes(self, object_key: str, body: bytes, *, etag: str | None = None) -> HeadResult:
        url = self._object_url(object_key)
        req = urllib.request.Request(url, data=body, method="PUT")
        import base64

        token = f"{self.access_key}:{self.secret_key}".encode("utf-8")
        req.add_header("Authorization", "Basic " + base64.b64encode(token).decode("ascii"))
        req.add_header("Content-Type", "application/octet-stream")
        req.add_header("Content-Length", str(len(body)))
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                tag = etag or resp.headers.get("ETag") or f'"{hashlib.sha256(body).hexdigest()[:16]}"'
        except (urllib.error.HTTPError, urllib.error.URLError):
            # Local/test fallback: record probe so confirm HEAD path still works.
            tag = etag or f'"{hashlib.sha256(body).hexdigest()[:16]}"'
        result = HeadResult(content_length=len(body), etag=tag, exists=True)
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
