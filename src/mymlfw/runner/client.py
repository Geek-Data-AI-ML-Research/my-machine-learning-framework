"""Local BYOC runner client: heartbeat + claim-job → hashed job-scoped tokens."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from mymlfw.runner.env import validate_runner_env
from mymlfw.runner.sandbox import sandbox_notes
from mymlfw.saas.ids import new_job_id, new_job_token_id, new_runner_id
from mymlfw.saas.schemas import (
    JobClaimRequest,
    JobClaimResponse,
    JobScopedCredentials,
    RunnerHeartbeatRequest,
    RunnerHeartbeatResponse,
    RunnerKind,
)

JOB_TOKEN_TTL = timedelta(hours=2)


def hash_runner_token(token: str) -> bytes:
    """One-way hash for persistence — never store reversible runner tokens."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def hash_job_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def mint_job_token(
    *,
    run_id: str | None = None,
    job_id: str | None = None,
    upload_presigns: list[dict[str, str]] | None = None,
    download_presigns: list[dict[str, str]] | None = None,
) -> JobScopedCredentials:
    """Mint a 2h job_token (raw returned once; callers persist ``hash_job_token`` only)."""
    raw = f"{new_job_token_id()}_{secrets.token_urlsafe(24)}"
    return JobScopedCredentials(
        job_id=job_id or new_job_id(),
        job_token=raw,
        expires_at=datetime.now(UTC) + JOB_TOKEN_TTL,
        run_id=run_id,
        upload_presigns=list(upload_presigns or []),
        download_presigns=list(download_presigns or []),
        sandbox_notes=sandbox_notes(),
    )


# Back-compat alias for older imports / tests.
mint_job_token_stub = mint_job_token


@dataclass
class RunnerClient:
    """In-process runner agent used by API claim routes and local CLI."""

    api_url: str = ""
    runner_token: str = ""
    runner_id: str = field(default_factory=new_runner_id)
    kind: RunnerKind = RunnerKind.local
    last_heartbeat_at: datetime | None = None
    token_hash: bytes | None = None
    _queue: list[dict[str, Any]] = field(default_factory=list)
    # job_id → sha256(job_token) — never store reversible tokens.
    _job_token_hashes: dict[str, bytes] = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> RunnerClient:
        cleaned = validate_runner_env(env)
        token = cleaned["MYMLFW_RUNNER_TOKEN"]
        runner_id = cleaned.get("MYMLFW_RUNNER_ID") or new_runner_id()
        return cls(
            api_url=cleaned["MYMLFW_API_URL"],
            runner_token=token,
            runner_id=runner_id,
            token_hash=hash_runner_token(token) if token else None,
        )

    def heartbeat(
        self,
        *,
        status: str = "idle",
        capability_tags: list[str] | None = None,
    ) -> RunnerHeartbeatResponse:
        now = datetime.now(UTC)
        self.last_heartbeat_at = now
        _ = RunnerHeartbeatRequest(
            runner_id=self.runner_id,
            kind=self.kind,
            capability_tags=capability_tags or ["local_cpu"],
            status=status,  # type: ignore[arg-type]
        )
        return RunnerHeartbeatResponse(runner_id=self.runner_id, accepted=True, server_time=now)

    def enqueue_job(
        self,
        *,
        run_id: str | None = None,
        upload_presigns: list[dict[str, str]] | None = None,
        download_presigns: list[dict[str, str]] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        job_id = new_job_id()
        self._queue.append(
            {
                "job_id": job_id,
                "run_id": run_id,
                "upload_presigns": list(upload_presigns or []),
                "download_presigns": list(download_presigns or []),
                "payload": dict(payload or {}),
            }
        )
        return job_id

    # Back-compat
    def enqueue_stub_job(self, *, run_id: str | None = None) -> str:
        return self.enqueue_job(run_id=run_id)

    def claim_job(self, body: JobClaimRequest | None = None) -> JobClaimResponse:
        body = body or JobClaimRequest(runner_id=self.runner_id)
        if body.runner_id != self.runner_id:
            return JobClaimResponse(claimed=False, credentials=None)
        if not self._queue:
            return JobClaimResponse(claimed=False, credentials=None)
        job = self._queue.pop(0)
        creds = mint_job_token(
            run_id=job.get("run_id"),
            job_id=job["job_id"],
            upload_presigns=job.get("upload_presigns"),
            download_presigns=job.get("download_presigns"),
        )
        self._job_token_hashes[creds.job_id] = hash_job_token(creds.job_token)
        self.heartbeat(status="busy", capability_tags=body.capability_tags)
        return JobClaimResponse(claimed=True, credentials=creds)

    def status(self) -> dict[str, Any]:
        return {
            "runner_id": self.runner_id,
            "kind": self.kind.value,
            "api_url": self.api_url,
            "has_token": bool(self.runner_token),
            "token_hash_prefix": (
                self.token_hash[:4].hex() if self.token_hash else None
            ),
            "last_heartbeat_at": (
                self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None
            ),
            "queued_jobs": len(self._queue),
            "sandbox_notes": sandbox_notes(),
            "mongo_uri_in_env": False,
        }
