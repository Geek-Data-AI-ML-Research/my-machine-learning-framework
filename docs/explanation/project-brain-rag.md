# Project Brain RAG (Adaptive DSS)

Why Campaign SaaS advise is not chat-with-docs: the corpus is non-stationary campaign state. Numeric SNR and dead-end lessons outrank prose. Epoch-toxic advice is rescored down.

## Closed loop

1. **Encode** — `complete_mission` writes a contrastive episode card (semantic summary + epoch / family / SNR), not a raw log chunk. Embeddings go through `saas/llm.py` only.
2. **Retrieve** — expand the query with goal titles + `error_slices`, fuse lexical + vector ranks (Mongo `$rankFusion` when ready, else app-side RRF), rescore by epoch × SNR × utility, then fill three buckets (A promotes, B dead ends, C kaggle/intel).
3. **Decide** — structured advise always exits through `citation_firewall` (strip hallucinated ULIDs, inject `[DB-VERIFIED …]` badges).
4. **Learn** — cited IDs on promote/kill update `utility_weight`; every ~10 closed missions consolidate pinned axioms.

## Cold start

With few local experiments, Tier2 archetype playbooks keyed by a dataset fingerprint (task, size buckets, cat ratio, skew, metric, ADV regime) blend into bucket C and fade as Tier1 memory grows past ~5–12 experiments.

## Guardrails

- Never return advise without the citation firewall.
- Do not gate `propose_lever` on cosine alone — use `lever_verifier`.
- Tenant filters belong in the vector index definition, not post-filters.
- Integrity/leakage scrub strips connection strings and API-key shaped secrets from briefs.

## Surfaces

| Surface | Path / tool |
| --- | --- |
| HTTP advise | `POST /v1/projects/{id}/advise` |
| HTTP brain query | `POST /v1/projects/{id}/brain/query` |
| MCP | `advise_project`, `query_project_brain` |

Offline contest advise (`python -m mymlfw advise`) remains the SQLite/worktree path documented in [Advise a contest](../how-to/advise-a-contest.md).
