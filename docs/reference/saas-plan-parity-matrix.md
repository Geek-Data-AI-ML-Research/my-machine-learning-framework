# SaaS plan → API → GUI parity matrix

Canonical human lock: [`saas-api.md`](saas-api.md). Source of features: Campaign SaaS plan screen map only — **no invented rows.**

| Status | Meaning |
| --- | --- |
| `ok` | OpenAPI path exists and GUI binds it |
| `api` | OpenAPI/route exists; GUI binder missing or static |
| `gap` | Plan requires human surface; HTTP and/or GUI incomplete |
| `mcp` | Plan agent/MCP-primary; GUI may show status via list/dashboard only |
| `n/a` | Explicitly out of scope |

## Auth / chrome

| Feature | Plan anchor | Method path | GUI route/control | Status |
| --- | --- | --- | --- | --- |
| Email/password login | Login Compose-local | `POST /v1/auth/login` | `/login` sign-in | ok |
| Register | Login Compose-local | `POST /v1/auth/register` | `/login` register | ok |
| GitHub OAuth start/callback | Login OAuth | `GET /v1/auth/github/start`, `POST /v1/auth/github/callback` | login (stub path) | api |
| Passkey options | Login Passkeys | `POST /v1/auth/passkey/options` | — | api |
| Current user + org + flags | Auth / Settings | `GET /v1/me` | chrome + settings | ok |
| Current org | Organizations | `GET /v1/orgs/current` | settings | ok |
| Feature flags patch | Settings / flags | `PATCH /v1/orgs/current/feature-flags` | settings flags | ok |
| Dev persona switcher | Compose persona | `POST /v1/dev/persona` | studio persona | ok |
| SSE events (no JWT query) | Live panes / train strip | `GET /v1/events` | Overview train strip poll | ok |
| Elicitation confirm (human) | Approval gate | `POST /v1/elicitation/confirm` | — | api |
| GitHub webhook | E3 git | `POST /v1/github/webhook` | — (server) | api |

## Studio home

| Feature | Plan anchor | Method path | GUI route/control | Status |
| --- | --- | --- | --- | --- |
| Ensure Demo Campaign | Login → studio TTV | `POST /v1/studio/ensure-demo` | after login | ok |
| List projects | Studio home table | `GET /v1/projects` | `/studio` list | ok |
| Get project | Open project | `GET /v1/projects/{project_id}` | open project | ok |
| Filter all\|kaggle\|standalone + search | Studio home | (client filter on list) | `/studio` filter + search | ok |
| Share from list | Studio Share | `POST /v1/projects/{id}/share` | list Share | ok |
| New project wizard | Studio New project | `POST /v1/projects` (+ optional `…/roadmap`, `…/progress` seed) | `#studio/new` DS playbook wizard | ok |
| Playbook catalog | Wizard Strategies | `GET /v1/playbook/catalog` | `#studio/new` Strategies (shared w/ CLI) | ok |
| Invite member | Studio invite | `POST /v1/projects/{id}/invite` | list Invite + TRUST | ok |
| Soft-delete / archive (owner) | Studio archive | `POST /v1/projects/{id}/archive` | list Archive | ok |
| Settings link / Logout | Studio header | `GET /v1/settings` (+ `/v1/me`) + local token clear | header Settings / Log out | ok |

## Workspace chrome

| Feature | Plan anchor | Method path | GUI route/control | Status |
| --- | --- | --- | --- | --- |
| Modes 1–6; hide Kaggle if standalone | Workspace modes | dashboard + kind on project | mode hotkeys | ok |
| Kind badge + primary goal + agent/git status | Workspace chrome | `GET …/dashboard` (+ git/cloud) | Overview header | ok |
| Back to studio list | Workspace | — | back link | ok |

## BRAIN (Overview)

| Feature | Plan anchor | Method path | GUI route/control | Status |
| --- | --- | --- | --- | --- |
| Dashboard aggregates (all plan panels typed) | Overview panels | `GET /v1/projects/{id}/dashboard` | BRAIN Overview | ok |
| Assign next mission (advise) | Overview primary CTA | `POST /v1/projects/{id}/advise` | Advise CTA | ok |
| Query project brain | Mid-mission RAG | `POST /v1/projects/{id}/brain/query` | — | api |
| Publish redacted share | TRUST / Overview share | `POST /v1/projects/{id}/share` | TRUST Share | ok |
| Public snapshot read | `/p/{org}/{slug}` | `GET /v1/public/{org_slug}/{slug}` | public page | api |
| Progress notes add/list | Daily progress | `GET/POST …/progress` | BRAIN [ record progress ] | ok |
| Dead ends list / add | Dead ends panel | `GET/POST …/dead-ends` | DEAD_ENDS mode + BRAIN panel | ok |
| Open / close lever (human) | Overview secondary | `GET/POST …/levers`, `POST …/levers/{id}/close` | BRAIN / LAB | ok |
| Missions list | Overview | `GET …/missions` | Missions panel | ok |
| Members list | TRUST | `GET …/members` | TRUST Members | ok |
| SSE live train strip | Header strip | `GET /v1/events` | train strip | ok |

## GOALS

| Feature | Plan anchor | Method path | GUI route/control | Status |
| --- | --- | --- | --- | --- |
| Goals CRUD | Goals mode | `GET/POST …/goals`, `PATCH …/goals/{id}` | GOALS mode | ok |
| Folds / ADV_AUC / splits | Goals / Overview | `GET …/dashboard` | GOALS stats | ok |

## LAB

| Feature | Plan anchor | Method path | GUI route/control | Status |
| --- | --- | --- | --- | --- |
| Research runs | LAB research | `POST /v1/projects/{id}/research-runs` | LAB Queue fold0 | ok |
| Error slices | LAB / research | `GET /v1/projects/{id}/runs/{run_id}/error_slices` | — | api |
| OOF pending → confirm | LAB / BYOC | `POST …/oof-artifacts`, `…/confirm`, `GET …`, `POST …/log-oof` | — | api |
| Ensemble optimize / promote | LAB Ensemble | `POST …/ensemble`, `POST …/ensemble/promote` | LAB Ensemble | ok |
| Autopilot start/status/pause/resume/digest/halt | Night-Shift | `POST/GET …/autopilot/*` | LAB Night controls | ok |
| Lever list / open / close (human) | LAB Levers | `GET/POST …/levers`, `POST …/close` | LAB + BRAIN | ok |

## KAGGLE (kaggle projects only; hidden if standalone)

| Feature | Plan anchor | Method path | GUI route/control | Status |
| --- | --- | --- | --- | --- |
| Intel panel | Kaggle intel | `GET …/kaggle/intel` | KAGGLE mode | ok |
| Refresh / sync | Sync now | `POST …/kaggle/refresh` | Sync now | ok |
| Import competition data | Data files | `POST …/kaggle/import-data` | Import data | ok |
| Discussions ingest | Important discussions | `POST …/kaggle/discussions` | Ingest discussion | ok |
| Package / push / diff | Submit / Final-2 | `POST …/kaggle/package\|push\|diff` | secondary actions | ok |
| Verify public notebook | Verify public NB | `POST …/kaggle/verify-notebook` | — | api |
| Seal Kaggle token | Secrets | `POST …/kaggle/token` | — | api |
| Writeup | Writeups | `POST …/writeup` | — | api |
| Promote insight → mission | Kaggle actions | MCP promote path | — | mcp |

## OPS

| Feature | Plan anchor | Method path | GUI route/control | Status |
| --- | --- | --- | --- | --- |
| Cloud accounts list | OPS Cloud | `GET /v1/orgs/current/cloud/accounts` | OPS accounts | ok |
| Connect RunPod / AWS | OPS Cloud | `POST …/cloud/connect/runpod\|aws` | OPS connect | ok |
| Disconnect / quote / launch / gpus / sweep | OPS Cloud | `POST/GET …/cloud/*` | quote+launch | ok |
| Runners list / stop / terminate | OPS Runners | `GET/POST …/runners*` | OPS Runners | ok |
| Local runner register / heartbeat / claim-job | BYOC | `POST /v1/runners/register\|heartbeat\|claim-job` | — (runner CLI) | api |
| Git plan / link status | OPS Git | `POST …/git/plan` | Plan git sync | ok |
| MCP connect snippet | Agents connect | docs / MCP URL | OPS Agent card | ok |

## TRUST

| Feature | Plan anchor | Method path | GUI route/control | Status |
| --- | --- | --- | --- | --- |
| Credits harvest / verify / export | TRUST Credits | `POST …/credits/harvest\|verify\|export` | TRUST Credits | ok |
| Members | TRUST Members | `GET …/members` + invite | TRUST Members | ok |
| Publish redacted share | TRUST Publish | `POST …/share` | Publish snapshot | ok |

## Agent / MCP

| Feature | Plan anchor | Method path / tool | GUI | Status |
| --- | --- | --- | --- | --- |
| `get_next_mission` / `complete_mission` / lease fencing | MCP B2 | MCP tools | status via dashboard missions | mcp |
| `report_mission_progress` | MCP | MCP | — | mcp |
| `propose_lever_execution` + lever_verifier | MCP E2 | MCP | — | mcp |
| `query_project_brain` | MCP + HTTP | MCP + `POST …/brain/query` | — | mcp |
| `register_external_asset` / license verify | Provenance | MCP (+ credits HTTP) | TRUST credits | mcp |

## Durability

| Concern | Plan role | Mechanism when URI set | Fallback when unset |
| --- | --- | --- | --- |
| Project data | Mongo `ProjectScopedDB` | studio/brain/projects/dashboard via Mongo | `BRAIN_STORE` |
| Idempotency-Key | Redis | Redis-backed store on API lifespan | in-memory store |
| LLM / Kaggle rate limits | Redis | Redis keys | process-local counters |
| SSE fan-out | Redis pub/sub | publish/subscribe on `/v1/events` | single-process |
| Worker queue relay | Redis | relay helpers for worker | local no-op |

## Explicitly out of scope

- Live Stripe Checkout / tax
- Multi-region active-active
- Platform-owned GPU fleet as default
- Replacing the offline single-repo contest toolkit
- Changing VQCC / contest zip rebuilds
- Local sentence-transformers / torch in api/mcp images

## Lock tests

- [`tests/test_saas_plan_parity.py`](../../tests/test_saas_plan_parity.py)
- [`tests/test_saas_dashboard_panels.py`](../../tests/test_saas_dashboard_panels.py)
- [`tests/test_saas_api_docs.py`](../../tests/test_saas_api_docs.py)
