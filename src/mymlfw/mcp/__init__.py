"""MCP server package (handlers stay thin; no Mongo — see AGENTS.md).

Phase B2: PAT auth + get_next_mission / complete_mission / get_project_dashboard.
"""

from mymlfw.mcp.server import build_mcp_server, main

__all__ = ["build_mcp_server", "main"]
