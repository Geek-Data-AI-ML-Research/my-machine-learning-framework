# MCP walking skeleton

How-to. Prefer Compose: `make up` starts MCP on `http://127.0.0.1:8100/mcp` with the same Mongo as the API. Mint a PAT via Studio Settings or `POST /v1/orgs/current/pats`. For a host process instead: `python -m mymlfw.mcp` (stdio) or `--transport streamable-http --host 127.0.0.1`.

Authenticate with `Authorization: Bearer <pat>`. Mutating tools need `idempotency_key`. Mission loop: `list_projects` → `get_next_mission` → `report_mission_progress` → `complete_mission` (fencing token must match).

Phase E/E2 tools: `query_project_brain`, `advise_project`, `propose_lever_execution`, `get_next_autopilot_probe`, `complete_autopilot_rung`, `register_external_asset`, `verify_project_licenses`. `confirm_elicitation` refuses PAT/agent actors.

Prompts: `mission_loop`, `campaign_sync` (keep Studio updated during a Kaggle run), `cloud_launch`.

Agents running a full contest should follow [Keep a Studio project updated via MCP](agent-mcp-campaign-sync.md) so Overview tracks CV/public scores and assets automatically.

OAuth 2.1 PKCE S256 helpers live in `mymlfw.mcp.oauth` behind `feature_flags.mcp_oauth`.
