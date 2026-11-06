"""mymlfw MCP server — stdio and Streamable HTTP (PAT-authenticated control plane)."""

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
    """Create the MCP server with mission + cloud tools registered."""

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
            "mymlfw Campaign MCP. Authenticate with Authorization: Bearer <pat> "
            "or MYMLFW_MCP_PAT (prefer env/header — avoid tool pat args on HTTP). "
            "Never put PAT/JWT in query strings. "
            "Mission loop: list_projects → get_next_mission → "
            "report_mission_progress → complete_mission. "
            "Always pass lease_fencing_token from the claim and a unique "
            "idempotency_key (or Idempotency-Key header) on every mutating tool. "
            "Cloud: enable org feature_flags.cloud_runners via the API, then "
            "connect_cloud_provider → quote_cloud_launch → launch_cloud_runner. "
            "Scopes: mcp:worker (missions), mcp:cloud or mcp:worker (cloud)."
        ),
        lifespan=lifespan,
    )

    @server.prompt(
        name="mission_loop",
        description="Standard claim → progress → complete loop with fencing + idempotency.",
    )
    async def mission_loop_prompt() -> str:
        return (
            "1. list_projects\n"
            "2. get_next_mission(project_id, idempotency_key=<uuid>)\n"
            "3. Work the brief; call report_mission_progress with the same "
            "lease_fencing_token and a new idempotency_key periodically\n"
            "4. complete_mission(..., lease_fencing_token, outcome, "
            "idempotency_key=<uuid>)\n"
            "On stale_lease: re-claim with get_next_mission; do not reuse the old token."
        )

    @server.prompt(
        name="campaign_sync",
        description=(
            "Keep Studio Overview updated while running a Kaggle/standalone campaign. "
            "Chat alone does not move the dashboard."
        ),
    )
    async def campaign_sync_prompt() -> str:
        return (
            "Contract: after every real campaign step, call MCP before the next user reply.\n"
            "Auth: Authorization Bearer PAT (mcp:worker). Mutating tools need idempotency_key.\n"
            "Orient: list_projects → get_project_dashboard → optional advise_project / "
            "query_project_brain.\n"
            "Work: get_next_mission → report_mission_progress(note, percent) on milestones "
            "(data pulled, CV number, submit started) → complete_mission(outcome, "
            "fold_scores, notes with public/CV/submission ref).\n"
            "Before a new variable: propose_lever_execution (one open lever only).\n"
            "External HF/Kaggle/kernel assets: register_external_asset; before final submit "
            "verify_project_licenses(gate=kaggle_submit).\n"
            "Dead ends / kills: record so query_project_brain(scope=dead_ends) remembers.\n"
            "Kaggle LB sync is Studio/HTTP refresh — not an MCP tool yet.\n"
            "If a needed MCP tool is missing or broken: call report_mcp_gap "
            "(title, needed_capability, context, workaround, severity, "
            "suggested_tool_name) with a fresh idempotency_key, and tell the human.\n"
            "Full playbook: docs/how-to/agent-mcp-campaign-sync.md"
        )

    @server.prompt(
        name="cloud_launch",
        description="Connect provider, quote micros/hr, then launch (billable).",
    )
    async def cloud_launch_prompt() -> str:
        return (
            "Prereq: owner enabled feature_flags.cloud_runners.\n"
            "1. connect_cloud_provider(provider, api_key|role_arn, idempotency_key)\n"
            "2. list_cloud_gpus / quote_cloud_launch\n"
            "3. launch_cloud_runner(..., cost_estimate_micros_hr from quote, "
            "idempotency_key)\n"
            "Never echo API keys. Stop with stop_cloud_runner(idempotency_key)."
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
            "Atomically claim the next queued mission. Requires idempotency_key. "
            "Returns lease_fencing_token for complete_mission / report_mission_progress."
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
            "Complete a leased mission. Requires lease_fencing_token + idempotency_key; "
            "mismatch returns error_code=stale_lease."
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
        description=(
            "Heartbeat / renew lease; requires matching lease_fencing_token "
            "and idempotency_key."
        ),
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
            "Mid-mission 3-bucket RAG query (promoted / dead_ends / intel). "
            "Returns status=ready|empty with cited BrainHit rows."
        ),
    )
    async def query_project_brain(
        project_id: str,
        ctx: Context,
        scope: Literal["dead_ends", "episodes", "kaggle_intel", "all"] = "all",
        max_tokens: int = 512,
        detail_level: Literal["summary", "full"] = "summary",
        query: str = "",
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
            query=query,
        )

    @server.tool(
        name="advise_project",
        description=(
            "Structured Project Brain advise. Always runs citation_firewall — "
            "hallucinated ULIDs are stripped."
        ),
    )
    async def advise_project(
        project_id: str,
        ctx: Context,
        task: str = "next experiment",
        max_missions: int = 3,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_advise_project(
            project_id=project_id,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
            task=task,
            max_missions=max_missions,
        )

    @server.tool(
        name="list_roadmap",
        description=(
            "List Studio Roadmap strategies for a project (plan / status / results)."
        ),
    )
    async def list_roadmap(
        project_id: str,
        ctx: Context,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_list_roadmap(
            project_id=project_id,
            pats=rt.pats,
            mongo_client=rt.mongo_client,
            brain=rt.brain,
            headers=_headers(ctx),
            pat=pat,
        )

    @server.tool(
        name="add_roadmap_strategy",
        description=(
            "Add one Roadmap strategy (title + plan). Requires idempotency_key. "
            "Use for Handbook/validation stages — one strategy per stage or theme."
        ),
    )
    async def add_roadmap_strategy(
        project_id: str,
        title: str,
        plan: str,
        idempotency_key: str,
        ctx: Context,
        priority: int = 100,
        status: str = "planned",
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_add_roadmap_strategy(
            project_id=project_id,
            title=title,
            plan=plan,
            pats=rt.pats,
            mongo_client=rt.mongo_client,
            brain=rt.brain,
            headers=_headers(ctx),
            pat=pat,
            idempotency_key=idempotency_key,
            priority=priority,
            status=status,
        )

    @server.tool(
        name="update_roadmap_strategy",
        description=(
            "Patch a Roadmap strategy (status, result, plan, metric). "
            "Requires idempotency_key. status: planned|in_progress|executed|cancelled."
        ),
    )
    async def update_roadmap_strategy(
        project_id: str,
        strategy_id: str,
        idempotency_key: str,
        ctx: Context,
        title: str | None = None,
        plan: str | None = None,
        status: str | None = None,
        result: str | None = None,
        result_metric: float | None = None,
        priority: int | None = None,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_update_roadmap_strategy(
            project_id=project_id,
            strategy_id=strategy_id,
            pats=rt.pats,
            mongo_client=rt.mongo_client,
            brain=rt.brain,
            headers=_headers(ctx),
            pat=pat,
            idempotency_key=idempotency_key,
            title=title,
            plan=plan,
            status=status,
            result=result,
            result_metric=result_metric,
            priority=priority,
        )

    @server.tool(
        name="list_org_runners",
        description=(
            "List org runners (local / RunPod / AWS). Never returns API keys. "
            "Gated by org feature_flags.cloud_runners."
        ),
    )
    async def list_org_runners(
        ctx: Context,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_list_org_runners(
            pats=rt.pats,
            cloud_store=rt.cloud_store,
            headers=_headers(ctx),
            pat=pat,
        )

    @server.tool(
        name="list_cloud_accounts",
        description="List connected cloud provider accounts (no secrets).",
    )
    async def list_cloud_accounts(
        ctx: Context,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_list_cloud_accounts(
            pats=rt.pats,
            cloud_store=rt.cloud_store,
            headers=_headers(ctx),
            pat=pat,
        )

    @server.tool(
        name="connect_cloud_provider",
        description=(
            "Seal a RunPod API key (api_key) or AWS BYOC role ARN (role_arn). "
            "Requires idempotency_key. Never returns secrets."
        ),
    )
    async def connect_cloud_provider(
        provider: Literal["runpod", "aws"],
        ctx: Context,
        api_key: str | None = None,
        role_arn: str | None = None,
        region: str = "us-east-1",
        idempotency_key: str | None = None,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_connect_cloud_provider(
            provider=provider,
            pats=rt.pats,
            cloud_store=rt.cloud_store,
            headers=_headers(ctx),
            pat=pat,
            api_key=api_key,
            role_arn=role_arn,
            region=region,
            idempotency_key=idempotency_key,
        )

    @server.tool(
        name="disconnect_cloud_provider",
        description="Disconnect a cloud provider account. Requires idempotency_key.",
    )
    async def disconnect_cloud_provider(
        provider: Literal["runpod", "aws"],
        ctx: Context,
        idempotency_key: str | None = None,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_disconnect_cloud_provider(
            provider=provider,
            pats=rt.pats,
            cloud_store=rt.cloud_store,
            headers=_headers(ctx),
            pat=pat,
            idempotency_key=idempotency_key,
        )

    @server.tool(
        name="list_cloud_gpus",
        description="List GPU offers + cost_estimate_micros_hr for a connected provider.",
    )
    async def list_cloud_gpus(
        provider: Literal["runpod", "aws"],
        ctx: Context,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_list_cloud_gpus(
            provider=provider,
            pats=rt.pats,
            cloud_store=rt.cloud_store,
            headers=_headers(ctx),
            pat=pat,
        )

    @server.tool(
        name="quote_cloud_launch",
        description=(
            "Quote micros/hr before launching a runner. Pass the quote into "
            "launch_cloud_runner."
        ),
    )
    async def quote_cloud_launch(
        provider: Literal["runpod", "aws"],
        gpu_type: str,
        ctx: Context,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_quote_cloud_launch(
            provider=provider,
            gpu_type=gpu_type,
            pats=rt.pats,
            cloud_store=rt.cloud_store,
            headers=_headers(ctx),
            pat=pat,
        )

    @server.tool(
        name="launch_cloud_runner",
        description=(
            "Launch a RunPod pod or AWS GPU instance after accepting a quote "
            "(billable). Requires cost_estimate_micros_hr + idempotency_key."
        ),
    )
    async def launch_cloud_runner(
        provider: Literal["runpod", "aws"],
        gpu_type: str,
        cost_estimate_micros_hr: int,
        ctx: Context,
        spot: bool = True,
        idempotency_key: str | None = None,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_launch_cloud_runner(
            provider=provider,
            gpu_type=gpu_type,
            cost_estimate_micros_hr=cost_estimate_micros_hr,
            pats=rt.pats,
            cloud_store=rt.cloud_store,
            headers=_headers(ctx),
            pat=pat,
            spot=spot,
            idempotency_key=idempotency_key,
        )

    @server.tool(
        name="stop_cloud_runner",
        description=(
            "Stop or terminate an org runner by runner_id. Requires idempotency_key."
        ),
    )
    async def stop_cloud_runner(
        runner_id: str,
        ctx: Context,
        terminate: bool = False,
        idempotency_key: str | None = None,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_stop_cloud_runner(
            runner_id=runner_id,
            pats=rt.pats,
            cloud_store=rt.cloud_store,
            headers=_headers(ctx),
            pat=pat,
            terminate=terminate,
            idempotency_key=idempotency_key,
        )

    @server.tool(
        name="propose_lever_execution",
        description="One-variable lever gate via lever_verifier (not cosine).",
    )
    async def propose_lever_execution(
        project_id: str,
        variable: str,
        ctx: Context,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        from mymlfw.mcp.phase_d_tools import tool_propose_lever_execution

        return await tool_propose_lever_execution(
            project_id=project_id,
            variable=variable,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
        )

    @server.tool(
        name="register_external_asset",
        description="Register an HF/Kaggle/paper asset onto project_credits.",
    )
    async def register_external_asset(
        project_id: str,
        name: str,
        ctx: Context,
        spdx: str = "UNVERIFIED_LICENSE",
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        from mymlfw.mcp.phase_d_tools import tool_register_external_asset

        return await tool_register_external_asset(
            project_id=project_id,
            name=name,
            spdx=spdx,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
        )

    @server.tool(
        name="verify_project_licenses",
        description="Hard license gate for kaggle_submit, final_promote, git_export.",
    )
    async def verify_project_licenses(
        project_id: str,
        credits: list[dict[str, Any]],
        gate: str,
        ctx: Context,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        from mymlfw.mcp.phase_d_tools import tool_verify_project_licenses

        return await tool_verify_project_licenses(
            project_id=project_id,
            credits=credits,
            gate=gate,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
        )

    @server.tool(
        name="get_next_autopilot_probe",
        description="Driver B probe lease (~15m) with fencing token.",
    )
    async def get_next_autopilot_probe(
        project_id: str,
        ctx: Context,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        from mymlfw.mcp.phase_d_tools import tool_get_next_autopilot_probe

        return await tool_get_next_autopilot_probe(
            project_id=project_id,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
        )

    @server.tool(
        name="complete_autopilot_rung",
        description="Complete an autopilot rung; requires fencing token + Idempotency-Key.",
    )
    async def complete_autopilot_rung(
        project_id: str,
        session_id: str,
        fencing_token: int,
        variable: str,
        ctx: Context,
        idempotency_key: str | None = None,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        from mymlfw.mcp.phase_d_tools import tool_complete_autopilot_rung

        return await tool_complete_autopilot_rung(
            project_id=project_id,
            session_id=session_id,
            fencing_token=fencing_token,
            variable=variable,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
            idempotency_key=idempotency_key,
        )

    @server.tool(
        name="report_mcp_gap",
        description=(
            "Report a missing or broken MCP capability so Studio can track it. "
            "Call when you cannot sync an action (no tool, wrong shape, auth/friction). "
            "Requires idempotency_key."
        ),
    )
    async def report_mcp_gap(
        title: str,
        needed_capability: str,
        idempotency_key: str,
        ctx: Context,
        context: str = "",
        workaround: str = "",
        severity: str = "annoying",
        project_id: str | None = None,
        suggested_tool_name: str = "",
        suggested_args_schema: str = "",
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_report_mcp_gap(
            title=title,
            needed_capability=needed_capability,
            pats=rt.pats,
            mongo_client=rt.mongo_client,
            headers=_headers(ctx),
            pat=pat,
            idempotency_key=idempotency_key,
            context=context,
            workaround=workaround,
            severity=severity,
            project_id=project_id,
            suggested_tool_name=suggested_tool_name,
            suggested_args_schema=suggested_args_schema,
        )

    @server.tool(
        name="list_mcp_gaps",
        description="List open MCP gap reports for this PAT workspace (optional project filter).",
    )
    async def list_mcp_gaps(
        ctx: Context,
        project_id: str | None = None,
        limit: int = 50,
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        return await mcp_tools.tool_list_mcp_gaps(
            pats=rt.pats,
            mongo_client=rt.mongo_client,
            headers=_headers(ctx),
            pat=pat,
            project_id=project_id,
            limit=limit,
        )

    @server.tool(
        name="confirm_elicitation",
        description="Human-only confirm. PAT/agent actors are refused.",
    )
    async def confirm_elicitation(
        action: str,
        ctx: Context,
        actor: str = "human",
        project_id: str = "",
        pat: str | None = None,
    ) -> dict[str, Any]:
        rt = _runtime(ctx)
        from mymlfw.mcp.phase_d_tools import tool_confirm_elicitation

        return await tool_confirm_elicitation(
            action=action,
            actor=actor,
            pats=rt.pats,
            headers=_headers(ctx),
            pat=pat,
            project_id=project_id,
        )

    @server.resource(
        "mymlfw://orgs/{org_id}/runners",
        name="org_runners",
        description=(
            "Read-only org runners resource. Never includes provider secrets."
        ),
        mime_type="application/json",
    )
    async def org_runners_resource(org_id: str, ctx: Context) -> dict[str, Any]:
        """PAT-scoped: URI org_id must match the authenticated workspace."""
        from mymlfw.mcp.auth import aresolve_auth_context, auth_error_payload
        from mymlfw.saas.providers.mcp_facade import cloud_service_for_org

        rt = _runtime(ctx)
        try:
            auth = await aresolve_auth_context(headers=_headers(ctx), store=rt.pats)
        except PermissionError as exc:
            return auth_error_payload(exc) or {
                "error_code": "invalid_or_missing_pat",
                "message": str(exc),
            }
        if org_id != auth.principal.workspace_id:
            return {
                "error_code": "org_mismatch",
                "message": "Resource org_id must match PAT workspace",
                "suggested_fix": "Use mymlfw://orgs/{workspace_id}/runners",
            }
        svc, enabled = cloud_service_for_org(
            auth.principal.workspace_id, cloud_store=rt.cloud_store
        )
        return mcp_tools.resource_org_runners(
            org_id=auth.principal.workspace_id,
            cloud_service=svc if enabled else None,
            cloud_runners_enabled=enabled,
        )

    return server


def main(
    transport: Literal["stdio", "streamable-http", "sse"] = "stdio",
    *,
    host: str = "127.0.0.1",
    port: int = 8100,
) -> None:
    import os

    # Compose binds 0.0.0.0 *inside* the container; host publish stays 127.0.0.1:8100.
    # Refuse all-interfaces bind only in production (use a reverse proxy instead).
    if host in {"0.0.0.0", "::"} and os.environ.get("MYMLFW_ENV", "dev").lower() in {
        "prod",
        "production",
    }:
        raise SystemExit(
            "Refusing to bind MCP on 0.0.0.0 in production — "
            "terminate TLS at a reverse proxy and bind a private interface"
        )
    server = build_mcp_server()
    if transport == "stdio":
        server.run(transport="stdio")
    elif transport == "streamable-http":
        server.run(transport="streamable-http", host=host, port=port)
    else:
        # SSE is supported for legacy clients; never put PAT in the query string.
        server.run(transport="sse", host=host, port=port)
