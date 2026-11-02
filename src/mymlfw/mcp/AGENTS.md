# MCP server (`src/mymlfw/mcp/`)

Thin MCP tools/resources/prompts over saas services. One contract for Cursor, Claude, Z, Trae, etc.

## DO

- Keep handlers thin: call saas services only; no business logic in `mcp/`.
- Mutating tools: send **Idempotency-Key**; require lease fencing token where specified.
- B2 walking skeleton (later): PAT + `get_next_mission` / `complete_mission` / `get_project_dashboard`.
- Hash PATs at rest; never return secrets in tool responses.
- Human-only elicitation confirm (E2) — never agent/PAT tokens.

## DO NOT

- Do **not** query Mongo / touch `AsyncDatabase` / `ScopedCollection` from MCP handlers.
- Do **not** put torch or embedding weights in the mcp image.
- Do **not** return RunPod/AWS secrets.
- Do **not** confirm elicitation with agent/PAT tokens.
- Do **not** put JWT/PAT in SSE query strings.
- Do **not** dispatch `verify_public_notebook` to local IDE agents.

## CI

AST checks fail if MCP modules contain Mongo query patterns or raw driver imports.
