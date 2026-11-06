# MCP server (`src/mymlfw/mcp/`)

Thin MCP tools/resources/prompts over saas services. One contract for Cursor, Claude, Z, Trae, etc.

Agent-facing playbook (how to keep Studio updated during a campaign):
[docs/how-to/agent-mcp-campaign-sync.md](../../../docs/how-to/agent-mcp-campaign-sync.md).
Prompts: `mission_loop`, `campaign_sync`, `cloud_launch`.

## Agent communication contract

Binding for any agent using this MCP server against a Studio project.

1. **Chat is not persistence.** CV numbers, downloads, notebook pulls, and submissions must hit MCP (or Studio HTTP) or Overview stays stale.
2. **Orient first:** `list_projects` → `get_project_dashboard` → optional `advise_project` / `query_project_brain`.
3. **Mission loop for real work:** `get_next_mission` → periodic `report_mission_progress` (milestones) → `complete_mission` with `lease_fencing_token`, `fold_scores`, and notes that include public/CV/submission refs.
4. **One lever at a time:** `propose_lever_execution` before a new variable; never open a second while one is `open`.
5. **Register before reuse:** `register_external_asset` for HF/Kaggle/kernel assets; `verify_project_licenses` before final submit/promote.
6. **Auth:** Bearer PAT / `MYMLFW_MCP_PAT`; scopes `mcp:worker` (missions) and optionally `mcp:cloud`. Fresh `idempotency_key` per mutation.
7. **Kaggle LB pull** is still Studio/HTTP `…/kaggle/refresh` — call it after submit so public score/rank appear on Overview.
8. **Missing tools:** `report_mcp_gap` (+ tell the human). Do not fake tool results.

Example mapping (fraud / ROC-AUC campaign): download → register asset + progress; adapt public notebook → register + propose lever; CV 0.95097 → `report_mission_progress`; public 0.95143 → `complete_mission` then HTTP kaggle refresh.

## DO

- Keep handlers thin: call saas services only; no business logic in `mcp/`. Cloud wiring uses `saas.providers.mcp_facade.cloud_service_for_org`.
- Mutating tools: **require** `idempotency_key` (or `Idempotency-Key` header); require lease fencing token on complete/progress.
- Auth: prefer `Authorization: Bearer` / `MYMLFW_MCP_PAT` over tool `pat` args. Return `{error_code, message, suggested_fix}` on auth failures.
- Scopes: `mcp:worker` (missions), `mcp:cloud` or `mcp:worker` (cloud), `mcp:admin` (all).
- Mission tools: `list_projects`, `get_project_dashboard`, `get_next_mission`, `report_mission_progress`, `complete_mission`; Phase E brain: `query_project_brain`, `advise_project` (always citation-firewall egress). Roadmap: `list_roadmap`, `add_roadmap_strategy`, `update_roadmap_strategy`.
- Cloud (org `feature_flags.cloud_runners` only — never elevate from MCP): `connect_cloud_provider`, `disconnect_cloud_provider`, `list_cloud_accounts`, `list_cloud_gpus`, `quote_cloud_launch`, `launch_cloud_runner`, `stop_cloud_runner`, `list_org_runners` + resource `mymlfw://orgs/{id}/runners`. Docs: [docs/how-to/connect-cloud-runners.md](../../../docs/how-to/connect-cloud-runners.md).
- Prompts: `mission_loop`, `campaign_sync`, `cloud_launch`.
- Hash PATs at rest (Mongo `agent_pats`); never return secrets in tool responses.
- Compose: `mcp` service on `127.0.0.1:8100/mcp` (container may bind `0.0.0.0`; host publish stays loopback). Refuse `0.0.0.0` bind when `MYMLFW_ENV=prod`.
- Entry: Compose stack, or `python -m mymlfw.mcp` / `mymlfw-mcp` (stdio or `--transport streamable-http`).

## DO NOT

- Do **not** query Mongo / touch `AsyncDatabase` / `ScopedCollection` from MCP handlers.
- Do **not** call `set_org_policy` / flip `feature_flags` from MCP.
- Do **not** put torch or embedding weights in the mcp image.
- Do **not** return RunPod/AWS secrets.
- Do **not** confirm elicitation with agent/PAT tokens.
- Do **not** put JWT/PAT in SSE query strings.
- Do **not** dispatch `verify_public_notebook` to local IDE agents.
- Do **not** skip Idempotency-Key on mutating tools.
- Do **not** narrate campaign progress only in chat while skipping `report_mission_progress` / `complete_mission`.

## CI

AST checks fail if MCP modules contain Mongo query patterns or raw driver imports.
