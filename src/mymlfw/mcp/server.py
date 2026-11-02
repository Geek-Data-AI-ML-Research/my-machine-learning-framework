"""mymlfw MCP server — stdio and Streamable HTTP (B2 PAT walking skeleton)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer

from mymlfw.mcp import tools as mcp_tools
from mymlfw.saas.missions import MissionService
from mymlfw.saas.pats import PatStore
from mymlfw.saas.runtime import (
    ControlPlaneRuntime,
    close_control_plane_runtime,
    open_control_plane_runtime,
)


def _headers(ctx: Context | None) -> dict[str, str] | None:
    if ctx is None:
        return None
    try:
        raw = ctx.headers
    except Exception:
        return None
    if raw is None:
        return None
    return {str(k): str(v) for k, v in raw.items()}


def _runtime(ctx: Context) -> ControlPlaneRuntime:
    return ctx.request_context.lifespan_context  # type: ignore[return-value]


def build_mcp_server(
    *,
    missions: MissionService | None = None,
    pats: PatStore | None = None,
    name: str = "mymlfw",
) -> MCPServer[ControlPlaneRuntime]:
    """Create the MCP server with B2 tools registered."""

    @asynccontextmanager
    async def lifespan(
        _server: MCPServer[ControlPlaneRuntime],
    ) -> AsyncIterator[ControlPlaneRuntime]:
        runtime = await open_control_plane_runtime(missions=missions, pats=pats)
        try:
            yield runtime
        finally:
            await close_control_plane_runtime(runtime)

    server: MCPServer[ControlPlaneRuntime] = MCPServer(
        name=name,
        instructions=(
            "mymlfw Campaign MCP (B2). Authenticate with a project PAT "
            "(Authorization: Bearer or MYMLFW_MCP_PAT). "
            "Core loop: list_projects → get_next_mission → "
            "report_mission_progress → complete_mission. "
            "Always pass lease_fencing_token from the claim."
        ),
        lifespan=lifespan,
    )

    @server.tool(
        name="list_projects",
        description="List projects visible to the authenticated PAT workspace.",
    )
    async def list_projects(
        ctx: Context,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_list_projects(
            missions=rt.missions,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
        )

    @server.tool(
        name="get_project_dashboard",
        description="Metrics board for a project (goals / levers / missions / dead ends).",
    )
    async def get_project_dashboard(
        project_id: str,
        ctx: Context,
        detail_level: Literal["summary", "full"] = "summary",
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_get_project_dashboard(
            project_id=project_id,
            missions=rt.missions,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
            detail_level=detail_level,
        )

    @server.tool(
        name="get_next_mission",
        description=(
            "Atomically claim the next queued mission. Returns lease_fencing_token "
            "(attempt_count) required for complete_mission / report_mission_progress."
        ),
    )
    async def get_next_mission(
        project_id: str,
        ctx: Context,
        idempotency_key: str | None = None,
        detail_level: Literal["summary", "full"] = "summary",
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_get_next_mission(
            project_id=project_id,
            missions=rt.missions,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
            idempotency_key=idempotency_key,
            detail_level=detail_level,
        )

    @server.tool(
        name="complete_mission",
        description=(
            "Complete a leased mission. Requires lease_fencing_token from claim; "
            "mismatch returns error_code=stale_lease (HTTP 409 equivalent)."
        ),
    )
    async def complete_mission(
        project_id: str,
        mission_id: str,
        lease_fencing_token: int,
        outcome: Literal["succeeded", "failed", "abandoned"],
        ctx: Context,
        fold_scores: list[float] | None = None,
        notes: str = "",
        idempotency_key: str | None = None,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_complete_mission(
            project_id=project_id,
            mission_id=mission_id,
            lease_fencing_token=lease_fencing_token,
            outcome=outcome,
            missions=rt.missions,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
            fold_scores=fold_scores,
            notes=notes,
            idempotency_key=idempotency_key,
        )

    @server.tool(
        name="report_mission_progress",
        description="Heartbeat / renew lease; requires matching lease_fencing_token.",
    )
    async def report_mission_progress(
        project_id: str,
        mission_id: str,
        lease_fencing_token: int,
        ctx: Context,
        note: str = "",
        percent: float | None = None,
        idempotency_key: str | None = None,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_report_mission_progress(
            project_id=project_id,
            mission_id=mission_id,
            lease_fencing_token=lease_fencing_token,
            missions=rt.missions,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
            note=note,
            percent=percent,
            idempotency_key=idempotency_key,
        )

    @server.tool(
        name="query_project_brain",
        description=(
            "Reserved mid-mission RAG query (Phase E). B2 returns status=not_ready."
        ),
    )
    async def query_project_brain(
        project_id: str,
        ctx: Context,
        scope: Literal["dead_ends", "episodes", "kaggle_intel", "all"] = "all",
        max_tokens: int = 512,
        detail_level: Literal["summary", "full"] = "summary",
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_query_project_brain(
            project_id=project_id,
            missions=rt.missions,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
            scope=scope,
            max_tokens=max_tokens,
            detail_level=detail_level,
        )

    return server


def main(
    transport: Literal["stdio", "streamable-http", "sse"] = "stdio",
    *,
    host: str = "127.0.0.1",
    port: int = 8100,
) -> None:
    server = build_mcp_server()
    if transport == "stdio":
        server.run(transport="stdio")
    elif transport == "streamable-http":
        server.run(transport="streamable-http", host=host, port=port)
    else:
        server.run(transport="sse", host=host, port=port)
