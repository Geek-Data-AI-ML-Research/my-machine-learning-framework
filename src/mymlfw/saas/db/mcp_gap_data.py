"""Mongo-backed MCP capability gap reports from agents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from mymlfw.saas.ids import new_gap_id
from mymlfw.saas.schemas import (
    McpGapReportCreate,
    McpGapReportResponse,
    McpGapSeverity,
)

MCP_GAPS = "mcp_gap_reports"

# Unit-test / no-Mongo fallback (Compose always uses Mongo).
_MEMORY: list[dict[str, Any]] = []


def reset_memory_gaps_for_tests() -> None:
    _MEMORY.clear()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def gap_from_doc(doc: dict[str, Any]) -> McpGapReportResponse:
    severity = doc.get("severity") or McpGapSeverity.annoying.value
    try:
        sev = McpGapSeverity(severity)
    except ValueError:
        sev = McpGapSeverity.annoying
    status = str(doc.get("status") or "open")
    if status not in {"open", "accepted", "wontfix", "shipped"}:
        status = "open"
    return McpGapReportResponse(
        id=doc.get("id") or doc["_id"],
        workspace_id=doc["workspace_id"],
        project_id=doc.get("project_id"),
        title=str(doc.get("title") or ""),
        needed_capability=str(doc.get("needed_capability") or ""),
        context=str(doc.get("context") or ""),
        workaround=str(doc.get("workaround") or ""),
        severity=sev,
        suggested_tool_name=str(doc.get("suggested_tool_name") or ""),
        suggested_args_schema=str(doc.get("suggested_args_schema") or ""),
        status=status,  # type: ignore[arg-type]
        created_at=doc.get("created_at"),
    )


def _build_doc(
    *,
    workspace_id: str,
    body: McpGapReportCreate,
) -> dict[str, Any]:
    gap_id = new_gap_id()
    now = _utcnow()
    return {
        "_id": gap_id,
        "id": gap_id,
        "workspace_id": workspace_id,
        "project_id": body.project_id,
        "schema_version": 1,
        "title": body.title.strip(),
        "needed_capability": body.needed_capability.strip(),
        "context": (body.context or "").strip(),
        "workaround": (body.workaround or "").strip(),
        "severity": body.severity.value,
        "suggested_tool_name": (body.suggested_tool_name or "").strip(),
        "suggested_args_schema": (body.suggested_args_schema or "").strip(),
        "status": "open",
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }


async def create_gap(
    db: AsyncDatabase | None,
    *,
    workspace_id: str,
    body: McpGapReportCreate,
) -> McpGapReportResponse:
    doc = _build_doc(workspace_id=workspace_id, body=body)
    if db is None:
        _MEMORY.append(doc)
        return gap_from_doc(doc)
    await db[MCP_GAPS].insert_one(doc)
    return gap_from_doc(doc)


async def list_gaps(
    db: AsyncDatabase | None,
    *,
    workspace_id: str,
    project_id: str | None = None,
    limit: int = 50,
) -> list[McpGapReportResponse]:
    lim = max(1, min(limit, 200))
    if db is None:
        rows = [
            d
            for d in _MEMORY
            if d.get("workspace_id") == workspace_id
            and d.get("deleted_at") is None
            and (not project_id or d.get("project_id") == project_id)
        ]
        rows.sort(key=lambda d: d.get("created_at") or _utcnow(), reverse=True)
        return [gap_from_doc(d) for d in rows[:lim]]
    filt: dict[str, Any] = {
        "workspace_id": workspace_id,
        "deleted_at": None,
    }
    if project_id:
        filt["project_id"] = project_id
    cursor = db[MCP_GAPS].find(filt).sort("created_at", -1).limit(lim)
    return [gap_from_doc(doc) async for doc in cursor]
