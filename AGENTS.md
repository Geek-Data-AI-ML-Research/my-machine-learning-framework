# AGENTS.md

mymlfw 0.1.0. Read `llms.txt` before editing a contest. Human documentation is [docs/index.md](docs/index.md).

Campaign SaaS work: also read partitioned AGENTS under `src/mymlfw/saas/`, `src/mymlfw/saas/db/`, `src/mymlfw/saas/rag/`, `src/mymlfw/mcp/`, and `web/`. Web agents: `npx skills add bas3line/ascii`.

## Commands

- Tests: `python -m pytest -q` from this checkout. Use the project virtualenv when it exists: `.venv/bin/python -m pytest -q`.
- CLI: `python -m mymlfw`. Failures are one JSON object on stderr with `error_code` and `suggested_fix`.
- Refresh the recipe block inside `llms.txt`: `python -m mymlfw sync-docs`. Keep the file at or under 1500 whitespace tokens. The checkout copy and `src/mymlfw/resources/llms.txt` stay identical.
- SaaS local stack: `make dev` (or `just up`) from checkout — Compose binds mongo/redis/minio to `127.0.0.1` only.

## Rules that override a local shortcut

The `DO NOT` lines in `llms.txt` are binding. In particular, call `mymlfw.cv.run_oof` instead of writing a GroupKFold loop.

- `src/mymlfw/rag/` does not import `mymlfw.train` or `mymlfw.engines`. Read engine class names with `ast.parse`.
- Engine class names are `TextBlendEngine`, `RankedCandidateEngine`, `AgentZipEngine`, `PortfolioEngine`, and `BenchmarkEngine`.
- `advise` needs a git checkout that has commits and a clean tracked tree. Untracked files do not make the tree dirty.
- `advise` does not insert episodes. The agent records the outcome later with `episode add`.
- Do not install torch unless the task is the train extra. Two tests skip without it.

## Anti-drift (Campaign SaaS)

Binding for SaaS/api/mcp/web work. History and shortcut fixes never weaken these. Mirror lives in partitioned AGENTS.md; CI AST enforces a subset.

### Global DO

- Call `Depends(get_project_db)` / accept `ProjectScopedDB` for all project data; use **prefixed ULIDs**.
- Driver: **`pymongo.AsyncMongoClient` only** (never Motor).
- Mutating API/MCP: **Idempotency-Key**; side effects via **outbox** + worker.
- Embeddings / LLM: only through **`saas/llm.py`** (external providers + spend caps).
- Ensemble / Autopilot / RAG math on control plane: **NumPy/SciPy only**—no torch in api/mcp images.
- MCP tools: thin → saas services; business logic never inside `mcp/` handlers.
- ascii.rest: **Motion = Active State**; kit for live metrics; `mono` logos; hex-only colors; one inverted CTA.
- Agents **must** `register_external_asset` when pulling HF/Kaggle/paper/kernel assets.
- Ship incomplete C–E3 behind **`feature_flags`**; keep OpenAPI + TS types in lockstep.
- Before closing a phase: tick every item in that phase’s Section checklist; do not mark done if any box is skipped.

### Global DO NOT

- Do **not** touch `db["experiments"]` / raw `AsyncDatabase` from routes, MCP, or services outside `saas/db/`.
- Do **not** post-filter `$vectorSearch` for tenancy—filters belong **in the search index definition**.
- Do **not** block `propose_lever` on cosine similarity alone—use **`lever_verifier`**.
- Do **not** return advise without **`citation_firewall`**.
- Do **not** open a second lever while one is `open` (partial unique index + **`active_execution_lock`**).
- Do **not** accept `complete_mission` / progress without matching **lease fencing token** (`attempt_count`).
- Do **not** embed unbounded `nodes[]` on `autopilot_sessions`—use `autopilot_nodes` collection.
- Do **not** auto-submit to Kaggle from Autopilot overnight.
- Do **not** mark MinIO artifacts `ready` without confirm HEAD; do **not** run full-N×C×M ensemble in-api above ceiling.
- Do **not** cache 5xx/429 under Idempotency-Key; do **not** allow NaN/Inf in metric fields.
- Do **not** resolve SPDX online synchronously inside `complete_mission` (cache sync + outbox async).
- Do **not** validate SSRF only in-app DNS—block private IPs at egress **TCP connect**.
- Do **not** allow `kaggle_submit` / final ensemble promote / git push of submission trees when any **`used_in_final_ensemble`** credit is `BLOCKED_*`.
- Do **not** invent SPDX IDs—resolve via registry APIs through egress (or mark `UNVERIFIED_LICENSE`).
- Do **not** put sentence-transformers/torch weights in api/mcp/worker images.
- Do **not** run user training inside the `api`/`mcp` containers—dispatch to a **runner**.
- Do **not** return RunPod/AWS secrets in MCP/API responses; do **not** skip $/hr quote before first provision.
- Do **not** let LLMs emit raw bash `cli_steps`—only `template_id` + typed args; server renders with `shlex.quote`.
- Do **not** dispatch `verify_public_notebook` to local IDE agents—`--network none` sandbox runner only.
- Do **not** confirm elicitation with agent/PAT tokens—human web session / Passkey / TOTP only.
- Do **not** store PATs/MCP/runner tokens reversible—hash only; envelope only for upstream 3rd-party secrets.
- Do **not** put JWT/PAT in SSE query strings; do **not** publish Mongo/Redis/MinIO on `0.0.0.0`.
- Do **not** store embeddings as `list[float]`—use **`BinaryVector` FLOAT32** via `pack_embedding_f32`.
- Do **not** store money/quotas as `float`—use **`cost_micros` Int64** (or Decimal128).
- Do **not** store token/audit hashes as hex strings—use **`bytes` binData**.
- Do **not** use naive datetimes—client CodecOptions **tz_aware UTC**; never compare naive vs aware.
- Do **not** pass `session=` inconsistently—use **`session.bind()` + `with_transaction`** for multi-doc ACID.
- Do **not** invent new JSON field names—extend `schemas.py` + regenerate OpenAPI first.
- Do **not** import `mymlfw.train` / engines from `saas/rag/` (AST-parse engine names only, same as existing rag rule).
- Do **not** replace ascii.rest with Tailwind UI / Chart.js / Material.
- Do **not** animate idle dashboards (`matrix-rain`, looping fireworks, marquee on Overview).
- Do **not** skip Section checklists when “almost done.”

### Drift detection (CI / pre-commit)

- AST fail: `AsyncDatabase` / `.raw_db[` / unscoped `aggregate` outside `saas/db/`.
- AST fail: `import torch` under `api/`, `mcp/`, `saas/` (except optional runner/train extras).
- AST fail: Mongo queries inside `mcp/` modules.
- Contract: `openapi.json` must match `schemas.py` (generated check).

## Where to change behavior

| Change | Look at |
| --- | --- |
| Ledger and probe guard | `src/mymlfw/campaign/ledger.py` |
| Recipe match | `src/mymlfw/campaign/match.py` |
| Retrieval and advise | `src/mymlfw/rag/` |
| CLI flags | `src/mymlfw/__main__.py` |
| Agent index | `llms.txt` and the packaged copy beside it |
| SaaS Mongo / ScopedCollection | `src/mymlfw/saas/db/` |
| SaaS API contracts | `src/mymlfw/saas/schemas.py`, `contracts/openapi.json` |
| FastAPI gateway | `src/mymlfw/api/` |
| MCP handlers | `src/mymlfw/mcp/` |
| SaaS web console | `web/` |
