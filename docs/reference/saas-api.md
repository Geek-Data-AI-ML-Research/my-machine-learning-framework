# Campaign SaaS API → GUI lock

Machine-readable OpenAPI: [`contracts/openapi.json`](../../contracts/openapi.json). Regenerate with `make openapi`. This page is the human **parity matrix**: every in-scope Studio feature has an HTTP path and a GUI binder in [`web/public/app.js`](../../web/public/app.js). Agent-only MCP tools stay MCP unless the Studio screen map also shows them to a human.

Durability (when URIs set): project data via Mongo `ProjectScopedDB`; Idempotency-Key / rate limits / SSE via Redis. In-memory fallbacks remain for unit tests when URIs are unset.

| Status | Meaning |
| --- | --- |
| `ok` | OpenAPI path + GUI binder |
| `api` | Route exists; GUI binder intentionally deferred / stub |
| `mcp` | MCP-primary; GUI shows status only |
| `n/a` | Out of scope |

## Auth / chrome

| Feature | Plan anchor | Method path | GUI | Status |
| --- | --- | --- | --- | --- |
| Login | Compose-local | `POST /v1/auth/login` | `#login` | ok |
| Register | Compose-local | `POST /v1/auth/register` | `#login` register | ok |
| Me / settings | Settings | `GET /v1/me`, `GET /v1/settings` | chrome + `#settings` | ok |
| Feature flags | Settings | `PATCH /v1/orgs/current/feature-flags` | settings | ok |
| Dev persona | Compose | `POST /v1/dev/persona` | studio persona | ok |
| SSE train strip | Overview live | `GET /v1/events` | BRAIN strip poll | ok |

## Studio home

| Feature | Plan anchor | Method path | GUI | Status |
| --- | --- | --- | --- | --- |
| Ensure demo | TTV | `POST /v1/studio/ensure-demo` | after login | ok |
| List / filter / search | Studio home | `GET /v1/projects` | `#studio` | ok |
| New project wizard | New project | `POST /v1/projects` | `#studio/new` | ok |
| Invite | Invite | `POST /v1/projects/{id}/invite` | list + TRUST | ok |
| Archive | Soft-delete | `POST /v1/projects/{id}/archive` | list Archive | ok |
| Share from list | Share | `POST /v1/projects/{id}/share` | list Share | ok |

## BRAIN (Overview)

| Feature | Plan anchor | Method path | GUI | Status |
| --- | --- | --- | --- | --- |
| Dashboard panels (typed; empty OK) | Overview table | `GET /v1/projects/{id}/dashboard` | BRAIN panels | ok |
| Assign next mission | Primary CTA | `POST /v1/projects/{id}/advise` | Assign next mission | ok |
| Record progress | Secondary | `GET/POST …/progress` | [ record progress ] | ok |
| Dead ends | Panel + list | `GET/POST …/dead-ends` | Dead ends panel | ok |
| Open / close lever | Secondary | `GET/POST …/levers`, `…/close` | [ open lever ] | ok |
| Missions list | Status | `GET …/missions` | Missions panel | ok |
| Sync git (plan) | Secondary | `POST …/git/plan` | [ sync git ] → OPS | ok |
| Open Kaggle | Secondary | (mode switch) | [ open Kaggle ] | ok |

DashboardResponse panels: `goals`, `scores`, `levers`, `ensemble`, `compute`, `paradigms`, `strategies`, `research`, `missions`, `dead_ends`, `daily_progress`, `kaggle`, `git`, `brain`.

## GOALS

| Feature | Plan anchor | Method path | GUI | Status |
| --- | --- | --- | --- | --- |
| Goals CRUD | Goals mode | `GET/POST …/goals`, `PATCH …/goals/{id}` | GOALS mode | ok |
| Sources CRUD | Sources tab | `GET/POST …/sources`, `PATCH/DELETE …/sources/{id}` | SOURCES mode | ok |
| Roadmap strategies | Roadmap tab | `GET/POST …/roadmap`, `PATCH/DELETE …/roadmap/{id}` | ROADMAP mode | ok |
| Project git link | Git tab | `GET/PUT/DELETE …/git`, `POST …/git/refresh` | GIT mode | ok |
| MCP gap reports | Ops | `GET/POST /v1/orgs/current/mcp-gaps` + MCP `report_mcp_gap` | Ops → MCP gaps | ok |
| Folds / ADV_AUC | Goals / Overview | `GET …/dashboard` (+ `ProjectSummary.folds`) | GOALS stats | ok |

## LAB

| Feature | Plan anchor | Method path | GUI | Status |
| --- | --- | --- | --- | --- |
| Research runs | LAB research | `POST …/research-runs` | Queue fold0 smoke | ok |
| Levers list / close | LAB Levers | `GET …/levers`, `POST …/close` | LAB table | ok |
| Ensemble plan/optimize | LAB Ensemble | `POST …/ensemble` | Optimize / plan | ok |
| Night-Shift start/pause/resume/digest/halt | Autopilot | `…/autopilot/*` | LAB night controls | ok |

## KAGGLE (kaggle projects only)

| Feature | Plan anchor | Method path | GUI | Status |
| --- | --- | --- | --- | --- |
| Intel | Kaggle intel | `GET …/kaggle/intel` | KAGGLE mode | ok |
| Sync now | Sync | `POST …/kaggle/refresh` | Sync now | ok |
| Import data | Competition files | `POST …/kaggle/import-data` | Import data | ok |
| Discussion ingest | Takeaway | `POST …/kaggle/discussions` | Ingest discussion | ok |
| Diff / package / push | Submit tools | `POST …/kaggle/diff\|package\|push` | secondary actions | ok |
| Hidden if standalone | Mode nav | — | mode filter | ok |

## OPS

| Feature | Plan anchor | Method path | GUI | Status |
| --- | --- | --- | --- | --- |
| MCP connect snippet | Agents | — (URL + PAT docs) | OPS Agent card | ok |
| Campaign sync playbook | Agents | MCP prompt `campaign_sync` + [agent-mcp-campaign-sync](../how-to/agent-mcp-campaign-sync.md) | OPS Agent card | ok |
| Cloud accounts / connect | Cloud | `GET/POST …/cloud/*` | OPS Cloud | ok |
| GPUs / quote / launch | Cloud | `GET …/gpus`, `…/quote`, `POST …/launch` | quote+launch | ok |
| Runners stop/terminate | Runners | `GET/POST …/runners*` | OPS Runners | ok |
| Git plan | Git | `POST …/git/plan` | Plan git sync | ok |

## TRUST

| Feature | Plan anchor | Method path | GUI | Status |
| --- | --- | --- | --- | --- |
| Credits harvest/verify/export | Credits | `POST …/credits/harvest\|verify\|export` | TRUST Credits | ok |
| Members list / invite | Members | `GET …/members`, `POST …/invite` | TRUST Members | ok |
| Publish share | Share | `POST …/share` | Publish snapshot | ok |

## Agent / MCP (status only in Studio)

| Feature | Surface | Status |
| --- | --- | --- |
| claim / complete mission + lease fencing | MCP | mcp |
| propose_lever_execution | MCP | mcp |

## Out of scope

Stripe, multi-region, platform GPU fleet, offline contest toolkit replacement, VQCC zip changes, torch/sentence-transformers in api/mcp images.

## Lock tests

- [`tests/test_saas_plan_parity.py`](../../tests/test_saas_plan_parity.py) — matrix paths exist in OpenAPI + `app.js` binder strings.
- [`tests/test_saas_dashboard_panels.py`](../../tests/test_saas_dashboard_panels.py) — Overview panels typed on `DashboardResponse`.
- [`tests/test_saas_mongo_redis.py`](../../tests/test_saas_mongo_redis.py) — durability when services up.
