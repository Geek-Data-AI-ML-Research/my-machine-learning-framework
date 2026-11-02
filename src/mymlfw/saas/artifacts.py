"""OOF artifact lifecycle: ``pending_upload`` → confirm HEAD → ``ready``.

Never mark MinIO artifacts ready without a confirm HEAD that matches the
pinned Content-Length. Stale pending rows older than 2h become ``expired``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from mymlfw.saas.ids import new_oof_id
from mymlfw.saas.schemas import (
    OofArtifactConfirmRequest,
    OofArtifactCreateRequest,
    OofArtifactPresignResponse,
    OofArtifactResponse,
    OofArtifactStatus,
)
from mymlfw.saas.storage import (
    PENDING_UPLOAD_TTL,
    MemoryObjectStore,
    ObjectStore,
    object_key_for_oof,
)


class ArtifactError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class InMemoryArtifactRepo:
    """Dict-backed repo for unit tests (ScopedCollection lands with Mongo routes)."""

    rows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def insert(self, doc: dict[str, Any]) -> None:
        self.rows[doc["_id"]] = dict(doc)

    def get(self, oof_id: str) -> dict[str, Any] | None:
        row = self.rows.get(oof_id)
        return None if row is None else dict(row)

    def save(self, doc: dict[str, Any]) -> None:
        self.rows[doc["_id"]] = dict(doc)

    def list_pending(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.rows.values() if r.get("status") == "pending_upload"]


@dataclass
class OofArtifactService:
    store: ObjectStore
    repo: InMemoryArtifactRepo
    workspace_id: str
    project_id: str
    pending_ttl: timedelta = PENDING_UPLOAD_TTL

    def create_upload(self, body: OofArtifactCreateRequest) -> OofArtifactPresignResponse:
        oof_id = new_oof_id()
        now = datetime.now(UTC)
        key = object_key_for_oof(
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            oof_id=oof_id,
            filename=body.filename,
        )
        presign = self.store.presign_put(
            key,
            content_length=body.content_length,
            content_sha256=body.content_sha256,
            expires_in=self.pending_ttl,
            content_disposition="attachment",
        )
        doc = {
            "_id": oof_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "experiment_id": body.experiment_id,
            "run_id": body.run_id,
            "status": OofArtifactStatus.pending_upload.value,
            "object_key": key,
            "filename": body.filename,
            "content_length": body.content_length,
            "content_sha256": body.content_sha256,
            "split_hash": body.split_hash,
            "etag": None,
            "schema_version": 1,
            "created_at": now,
            "updated_at": now,
            "ready_at": None,
            "expires_at": presign.expires_at,
            "deleted_at": None,
        }
        self.repo.insert(doc)
        return OofArtifactPresignResponse(
            oof_id=oof_id,
            upload_url=presign.url,
            object_key=key,
            expires_at=presign.expires_at,
            headers=presign.headers,
            content_disposition="attachment",
        )

    def confirm(
        self,
        oof_id: str,
        body: OofArtifactConfirmRequest | None = None,
    ) -> OofArtifactResponse:
        body = body or OofArtifactConfirmRequest()
        doc = self.repo.get(oof_id)
        if doc is None:
            raise ArtifactError("oof_not_found", "Unknown OOF artifact id.")
        if doc["status"] == OofArtifactStatus.ready.value:
            return self._to_response(doc)
        if doc["status"] == OofArtifactStatus.expired.value:
            raise ArtifactError("oof_expired", "Pending upload TTL elapsed; create a new slot.")
        if doc["status"] != OofArtifactStatus.pending_upload.value:
            raise ArtifactError("oof_bad_status", f"Cannot confirm status={doc['status']}.")

        now = datetime.now(UTC)
        expires_at = doc.get("expires_at")
        if isinstance(expires_at, datetime) and now > expires_at:
            doc["status"] = OofArtifactStatus.expired.value
            doc["updated_at"] = now
            self.repo.save(doc)
            raise ArtifactError("oof_expired", "Pending upload TTL elapsed; create a new slot.")

        head = self.store.head(doc["object_key"])
        if head is None or not head.exists:
            raise ArtifactError(
                "oof_object_missing",
                "HEAD Object failed; upload the bytes then retry confirm.",
            )
        if head.content_length != int(doc["content_length"]):
            raise ArtifactError(
                "oof_length_mismatch",
                "HEAD Content-Length does not match pinned upload length.",
            )
        if body.expected_etag and head.etag and body.expected_etag.strip('"') != head.etag.strip('"'):
            raise ArtifactError("oof_etag_mismatch", "HEAD ETag does not match expected_etag.")

        doc["status"] = OofArtifactStatus.ready.value
        doc["etag"] = head.etag
        doc["updated_at"] = now
        doc["ready_at"] = now
        self.repo.save(doc)
        return self._to_response(doc)

    def get(self, oof_id: str) -> OofArtifactResponse:
        doc = self.repo.get(oof_id)
        if doc is None:
            raise ArtifactError("oof_not_found", "Unknown OOF artifact id.")
        return self._to_response(doc)

    def expire_stale_pending(self, *, now: datetime | None = None) -> int:
        """Mark pending uploads past TTL as expired. Returns count expired."""
        now = now or datetime.now(UTC)
        expired = 0
        for doc in self.repo.list_pending():
            expires_at = doc.get("expires_at") or (doc["created_at"] + self.pending_ttl)
            if now > expires_at:
                doc["status"] = OofArtifactStatus.expired.value
                doc["updated_at"] = now
                self.repo.save(doc)
                expired += 1
        return expired

    @staticmethod
    def _to_response(doc: dict[str, Any]) -> OofArtifactResponse:
        return OofArtifactResponse(
            oof_id=doc["_id"],
            experiment_id=doc["experiment_id"],
            run_id=doc.get("run_id"),
            status=OofArtifactStatus(doc["status"]),
            object_key=doc["object_key"],
            content_length=int(doc["content_length"]),
            content_sha256=doc["content_sha256"],
            split_hash=doc.get("split_hash"),
            etag=doc.get("etag"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            ready_at=doc.get("ready_at"),
        )


def default_memory_service(
    *,
    workspace_id: str = "org_01HTESTWORKSPACE0000000000",
    project_id: str = "prj_01HTESTPROJECT000000000000",
) -> tuple[OofArtifactService, MemoryObjectStore]:
    store = MemoryObjectStore()
    svc = OofArtifactService(
        store=store,
        repo=InMemoryArtifactRepo(),
        workspace_id=workspace_id,
        project_id=project_id,
    )
    return svc, store
