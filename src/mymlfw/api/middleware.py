"""X-Mymlfw-Client-Version handshake middleware."""

from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

CLIENT_VERSION_HEADER = "X-Mymlfw-Client-Version"


def _parse_major(version: str) -> int | None:
    try:
        return int(version.split(".", 1)[0])
    except (TypeError, ValueError):
        return None


class ClientVersionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, server_version: str) -> None:
        super().__init__(app)
        self.server_version = server_version
        self.server_major = _parse_major(server_version) or 0

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        client = request.headers.get(CLIENT_VERSION_HEADER)
        if not client:
            return await call_next(request)
        major = _parse_major(client)
        if major is None:
            return JSONResponse(
                {
                    "error_code": "invalid_client_version",
                    "message": f"Invalid {CLIENT_VERSION_HEADER}",
                    "suggested_fix": "Send semver like 0.1.0",
                },
                status_code=400,
            )
        if major != self.server_major:
            return JSONResponse(
                {
                    "error_code": "client_version_rejected",
                    "message": "Major client version mismatch",
                    "suggested_fix": f"Upgrade client to {self.server_version}",
                    "details": {
                        "client_version": client,
                        "server_version": self.server_version,
                        "level": "reject",
                    },
                },
                status_code=426,
            )
        response = await call_next(request)
        if major == self.server_major and client != self.server_version:
            response.headers["X-Mymlfw-Version-Warn"] = "minor_mismatch"
        response.headers["X-Mymlfw-Server-Version"] = self.server_version
        return response
