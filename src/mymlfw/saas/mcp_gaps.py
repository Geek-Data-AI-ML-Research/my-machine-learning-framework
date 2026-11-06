"""MCP capability-gap reports — service façade over ``saas.db.mcp_gap_data``."""

from __future__ import annotations

import os
from typing import Any

from mymlfw.saas.db import mcp_gap_data
from mymlfw.saas.schemas import McpGapReportCreate, McpGapReportResponse


def _db_from_client(mongo_client: Any | None) -> Any | None:
    if mongo_client is None:
        return None
    from mymlfw.saas.db.client import get_saas_database

    return get_saas_database(
        mongo_client, os.environ.get("MYMLFW_MONGO_DB", "mymlfw")
    )


async def report_gap(
    *,
    workspace_id: str,
    body: McpGapReportCreate,
    mongo_client: Any | None = None,
) -> McpGapReportResponse:
    return await mcp_gap_data.create_gap(
        _db_from_client(mongo_client),
        workspace_id=workspace_id,
        body=body,
    )


async def list_gap_reports(
    *,
    workspace_id: str,
    project_id: str | None = None,
    limit: int = 50,
    mongo_client: Any | None = None,
) -> list[McpGapReportResponse]:
    return await mcp_gap_data.list_gaps(
        _db_from_client(mongo_client),
        workspace_id=workspace_id,
        project_id=project_id,
        limit=limit,
    )
