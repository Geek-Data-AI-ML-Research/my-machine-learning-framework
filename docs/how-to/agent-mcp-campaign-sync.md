# Keep a Studio project updated via MCP

How-to for coding agents. Use the Campaign SaaS **MCP server** so every real step of a Kaggle (or standalone) campaign lands on the Studio project dashboard — not only in chat.

This page is binding for agents connected to `mymlfw-mcp`. Mirror lives in [`src/mymlfw/mcp/AGENTS.md`](../../src/mymlfw/mcp/AGENTS.md).

## Connect

1. Bring up the stack (`make up`). The **mcp** Compose service starts automatically on `http://127.0.0.1:8100/mcp` (host publish is loopback-only; never publish MCP as `0.0.0.0` on the host).
2. Studio **Settings → Agent PAT** (or `POST /v1/orgs/current/pats` with Idempotency-Key) mints a PAT with scope `mcp:worker` (add `mcp:cloud` only if launching runners). Copy the plaintext once.
3. Point the agent host at that URL with `Authorization: Bearer <pat>` (or `MYMLFW_MCP_PAT`). Prefer header/env over tool `pat` arguments.
4. Every **mutating** tool needs a fresh `idempotency_key` (UUID). Do not reuse keys across different side effects.

Ops → Agent / MCP card shows `http://127.0.0.1:8100/mcp`. Stdio (`python -m mymlfw.mcp`) remains available for non-Compose agents.

## Tell a running Cursor agent (paste as follow-up)

Use this when the agent is already mid-campaign (training, stacking, submitting) and Studio is stale. MCP must already be configured for that Cursor project (`http://127.0.0.1:8100/mcp` + Bearer PAT from Studio Settings).

```text
Stop narrating-only. From now on keep the mymlfw Studio project updated via MCP before each user-visible reply.

1. Load MCP prompt `campaign_sync` (or follow docs/how-to/agent-mcp-campaign-sync.md).
2. Orient: list_projects → get_project_dashboard — bind to the existing Studio project (do not create Demo Campaign).
3. After every real step (download, notebook reuse, CV number, submit, dead end): call the matching MCP tools (register_external_asset, propose_lever_execution, report_mission_progress, complete_mission, …) with a fresh idempotency_key.
4. If a tool is missing, wrong, or you cannot sync an action: call report_mcp_gap(title, needed_capability, context, workaround, severity, suggested_tool_name, idempotency_key) AND tell me in chat what is missing.
5. Do not claim Studio is updated unless MCP (or Studio HTTP) wrote the state.
```

Studio Settings → Agent connect shows the same paste block after you mint a PAT.

## Golden rule

**If you changed the campaign state, call MCP before the next chat reply.**

Chat alone does not update Overview. Missions, progress %, lever status, dead-end memory, and credits only move when tools (or Studio HTTP) write them.

## Report missing MCP features

When you need a call that does not exist (example: `kaggle_refresh` from MCP), or a tool fails for a product reason:

1. `report_mcp_gap` with `needed_capability`, what you tried (`context`), what you did instead (`workaround`), `severity` (`blocker` | `annoying` | `nice_to_have`), and optional `suggested_tool_name` / `suggested_args_schema`.
2. Tell the human in chat (one short line + the gap id).
3. Continue with the documented workaround (Studio HTTP / chat) — do not invent fake tool results.

Humans triage gaps under Studio **Ops → MCP gaps** (`GET /v1/orgs/current/mcp-gaps`).

## Orient (every session)

```
list_projects
get_project_dashboard(project_id, detail_level="summary")
advise_project(project_id, task="next experiment")   # optional
query_project_brain(project_id, query="…", scope="all")
```

- Bind work to the **existing** project id (e.g. `playground-cc` / fraud contest). Do not invent a new Demo Campaign.
- Read dashboard: primary goal, public/CV, open levers, queued missions, dead ends.
- `advise_project` / `query_project_brain` go through the citation firewall — use citations; do not fabricate ULIDs.

## Mission loop (required for work that moves the needle)

Use MCP prompt `mission_loop`, or:

1. `get_next_mission(project_id, idempotency_key=<uuid>)`  
   → save `mission_id` + `lease_fencing_token`
2. While working: `report_mission_progress(project_id, mission_id, lease_fencing_token, note=…, percent=…, idempotency_key=<new uuid>)`  
   - Call on meaningful milestones (data ready, CV number, submit started), not every sentence.
3. Finish: `complete_mission(project_id, mission_id, lease_fencing_token, outcome, fold_scores=[…], notes=…, idempotency_key=<uuid>)`  
   - `outcome`: `succeeded` | `failed` | `abandoned`  
   - Put CV / public score / submission ref in `notes` and numeric folds in `fold_scores` when you have them.
4. On `error_code=stale_lease`: re-claim with `get_next_mission`; never reuse the old fencing token.

If no mission is queued, ask the human (Studio Overview → Assign next mission) or complete prior work via dashboard — do not silently continue without a lease when the project expects mission accounting.

## Map a Kaggle campaign onto tools

Example agent narrative → MCP calls:

| Agent moment | MCP (and notes) |
| --- | --- |
| “Competition is credit-card fraud (ROC-AUC)” | `list_projects` + `get_project_dashboard` — confirm kaggle project + primary goal |
| “Kaggle auth works. Downloading the data…” | `register_external_asset(project_id, name="kaggle://competitions/<slug>", spdx=…)` then `report_mission_progress(…, note="downloading competition data", percent=10)` |
| “Pulling top notebooks / public artifacts” | `register_external_asset` per HF/Kaggle/kernel asset **before** using it in a final stack; `query_project_brain(scope="kaggle_intel")` |
| “Building GBDT + digit features / adapting 0.95154 approach” | `propose_lever_execution(project_id, variable="<one variable>")` — one open lever at a time; if refused, pick another variable |
| “Hillclimb too slow — switching to logistic stack” | Progress note via `report_mission_progress`; if this is a new variable, `propose_lever_execution` first |
| “Artifact stack CV is 0.95097” | `report_mission_progress(…, note="artifact stack CV 0.95097", percent=70)` and include fold scores when completing |
| “Submitting… scored 0.95143 (top ~0.95192)” | `complete_mission(…, outcome="succeeded", notes="public 0.95143; top ~0.95192; submission …", fold_scores=[…])` then refresh Studio Kaggle intel (HTTP `POST /v1/projects/{id}/kaggle/refresh` with human/API token — not an MCP tool yet) |
| Dead end (e.g. hillclimb on 700k rows) | Prefer recording via Studio/API dead-ends or brain ingest so `query_project_brain(scope="dead_ends")` remembers; do not repeat a killed variable |
| Validation / Handbook roadmap stages | `list_roadmap` → `add_roadmap_strategy(title, plan, priority, idempotency_key)` per stage; mark done with `update_roadmap_strategy(..., status="executed", result=…, result_metric=…)` |

## Licenses and submit gates

Before treating a stack as final / submit-ready:

1. `register_external_asset` for every external weight/kernel/dataset used in the final ensemble.
2. `verify_project_licenses(project_id, credits=[…], gate="kaggle_submit")` (or `final_promote` / `git_export`).
3. Do not auto-submit overnight; Autopilot must not set `auto_kaggle_submit`.

## Cloud runners (optional)

Only when org `feature_flags.cloud_runners` is on (owner API). Use MCP prompt `cloud_launch`: connect → quote micros/hr → launch. Never echo keys. Prefer runners for long training; do not train inside `api`/`mcp` containers.

## What MCP does **not** do (yet)

| Need | Use instead |
| --- | --- |
| Live Kaggle LB / submissions pull | Studio Kaggle → Sync, or `POST /v1/projects/{id}/kaggle/refresh` with human session / project token |
| Create project / goals | Studio New project wizard or `POST /v1/projects` |
| Flip org feature flags | Owner `PATCH /v1/orgs/current/feature-flags` — MCP must not elevate |
| Confirm human elicitation | Web session / Passkey / TOTP — never PAT |

## Anti-patterns

- Narrating CV / public scores in chat without `report_mission_progress` / `complete_mission`.
- Opening a second lever while one is `open`.
- Completing a mission without the matching `lease_fencing_token`.
- Reusing `idempotency_key` for a different side effect.
- Putting PATs in SSE query strings or logging secrets.
- Querying Mongo from the agent — only MCP tools / Studio HTTP.

## Quick checklist before each user-visible update

1. Same `project_id` as Studio.
2. Active lease or just completed one with real `notes` / `fold_scores`.
3. External assets registered if used.
4. Dashboard re-read (`get_project_dashboard`) so the next step matches Overview.

Prompt on the server: `campaign_sync` (same contract, short form).
