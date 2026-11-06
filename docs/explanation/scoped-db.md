# Scoped Mongo

`ProjectScopedDB` is the only project-data handle routes and services should accept. `ScopedCollection` forces `workspace_id` + `project_id`, strips `$` operators from untrusted filters, and prepends `$match` on aggregates. Embeddings are `BinaryVector` FLOAT32 via `pack_embedding_f32`. The vector index definition (tenant filters, scalar quantization, storedSource) is `src/mymlfw/saas/db/vector_index.json`. When that index is not READY, retrieval uses app-side RRF.
