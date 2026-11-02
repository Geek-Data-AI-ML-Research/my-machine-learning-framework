# SaaS package (`src/mymlfw/saas/`)

Campaign SaaS control plane: tenants, project brain services, ensemble/autopilot/provenance stubs, LLM gateway. Read root `AGENTS.md` Anti-drift first. Phase checklists live in the Campaign SaaS plan (Section checklists).

## DO

- Accept `ProjectScopedDB` / `Depends(get_project_db)` for all project data; use **prefixed ULIDs**.
- Driver access only via `saas/db/` (`pymongo.AsyncMongoClient` — never Motor).
- Mutating paths: **Idempotency-Key** + **outbox** for side effects.
- Embeddings / LLM only through **`saas/llm.py`** (external providers + spend caps).
- Ensemble / Autopilot / RAG math: **NumPy/SciPy only** — no torch in api/mcp images.
- Ship incomplete C–E3 behind **`feature_flags`**; extend `schemas.py` + regenerate OpenAPI before new JSON fields.
- Agents **must** `register_external_asset` when pulling HF/Kaggle/paper/kernel assets.

## DO NOT

- Do **not** touch raw `AsyncDatabase` / `db["experiments"]` outside `saas/db/`.
- Do **not** put sentence-transformers/torch weights here or in api/mcp/worker images.
- Do **not** run user training inside api/mcp — dispatch to a **runner**.
- Do **not** invent field names without `schemas.py` + OpenAPI first.
- Do **not** import `mymlfw.train` / engines from `saas/rag/` (AST-parse engine names only).
- Do **not** store embeddings as `list[float]`, money as float USD, or naive datetimes.
- Do **not** open a second lever while one is `open`; use `active_execution_lock`.
- Do **not** auto-submit to Kaggle from Autopilot.
- Do **not** return advise without `citation_firewall` (when advise lands).
- Do **not** let LLMs emit raw bash `cli_steps` — only `template_id` + typed args.

## Where to change

| Change | Look at |
| --- | --- |
| Mongo client / ScopedCollection / indexes | `saas/db/` |
| API contracts | `saas/schemas.py`, `contracts/openapi.json` |
| Project brain RAG | `saas/rag/` (+ its AGENTS.md) |
| Ensemble / autopilot / provenance | `ensemble.py`, `autopilot.py`, `provenance.py` (later phases) |
