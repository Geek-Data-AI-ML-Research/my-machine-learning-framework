# SaaS RAG (`src/mymlfw/saas/rag/`)

Project Brain adaptive DSS (contrastive cards, `$rankFusion`, rescoring, lever verifier, citation firewall). Same rule as offline `mymlfw.rag/`: **do not** import train/engines.

## DO

- Read engine class names with `ast.parse` only (never import `mymlfw.train` / `mymlfw.engines`).
- Route retrieval through ScopedCollection; tenant/epoch filters **in** the vector index definition.
- Prefer `$rankFusion` when indexes READY; else app-side RRF (`1/(60+rank)`).
- Pipe every advise LLM output through `citation_firewall.enforce_citation_firewall` (when advise lands).
- Use `lever_verifier` before blocking/allowing `propose_lever` (not cosine alone).
- Embeddings only via `saas/llm.py` + `pack_embedding_f32`.

## DO NOT

- Do **not** import `mymlfw.train` or `mymlfw.engines`.
- Do **not** post-filter `$vectorSearch` for tenancy.
- Do **not** return advise without citation firewall.
- Do **not** block `propose_lever` on cosine similarity alone.
- Do **not** put local embedding weights / torch in this package.

## Phase note

Wave 1 ships package + AGENTS only. Full DSS lands in Phase E; stubs may exist earlier.
