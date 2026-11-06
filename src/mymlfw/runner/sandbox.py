"""Sandbox notes for BYOC jobs (local + future cloud image entrypoint)."""

from __future__ import annotations

SANDBOX_NOTES: tuple[str, ...] = (
    "Pull inputs and push artifacts only via job-scoped presigned URLs.",
    "Do not embed Mongo URI, KEK, or provider API keys in the job env.",
    "verify_public_notebook jobs require --network none; never run on local IDE agents.",
    "Heartbeat at least every 30s while a job is active; idle runners self-stop on timeout.",
    "Job token TTL is 2h; re-claim for a fresh token rather than extending.",
    "Dead-man: if API unreachable and idle past idle_timeout_minutes, self-stop "
    "(EC2 terminate-on-shutdown / RunPod stop hook).",
    "AWS Spot: poll instance-action every 5s; on 2m notice checkpoint + requeue "
    "without infra strike.",
)


def sandbox_notes() -> list[str]:
    return list(SANDBOX_NOTES)
