"""DB-layer domain errors for leases / missions (raised by ProjectScopedDB)."""

from __future__ import annotations


class StaleLeaseError(Exception):
    """Fencing token (attempt_count) mismatch — map to HTTP/MCP 409."""

    error_code = "stale_lease"

    def __init__(
        self,
        message: str = "Lease fencing token is stale",
        *,
        mission_id: str | None = None,
        expected: int | None = None,
    ) -> None:
        super().__init__(message)
        self.mission_id = mission_id
        self.expected = expected


class MissionNotFoundError(Exception):
    error_code = "mission_not_found"

    def __init__(self, message: str = "Mission not found", *, mission_id: str | None = None) -> None:
        super().__init__(message)
        self.mission_id = mission_id
