# SaaS DB (`src/mymlfw/saas/db/`)

Zero-trust Mongo layer. **Only** this package may hold `AsyncMongoClient` / raw collection access for project data. Routes and MCP must use `ProjectScopedDB` / `ScopedCollection`.

## DO

- Use `create_saas_mongo_client`: `CodecOptions(tz_aware=True, tzinfo=UTC)`, Decimal128 registry, `compressors=zstd`, majority W/R.
- Force `workspace_id` + `project_id` + `deleted_at: None` on every ScopedCollection read/write.
- Strip `workspace_id` / `project_id` / `_id` from `$set`; reject `$`-operator keys from untrusted filters.
- Prepend `$match` on aggregations; `$regex` only via `re.escape` + length cap.
- Multi-doc ACID: `session.bind()` + `await session.with_transaction(cb)`.
- Embeddings via `pack_embedding_f32` → BinaryVector FLOAT32.
- Indexes: ESR tenant keys; one-open-lever partial unique; partial outbox active-only; soft-delete TTL.
- Money/quotas as `*_micros` Int64; hashes/DEKs as binData bytes.

## DO NOT

- Do **not** export raw `AsyncDatabase` to routes/MCP/services outside this package.
- Do **not** post-filter `$vectorSearch` for tenancy — filters belong in the search index.
- Do **not** store embeddings as `list[float]`, money as float, hashes as hex strings, or naive datetimes.
- Do **not** use Motor.
- Do **not** pass `session=` inconsistently outside `with_transaction` + `bind()`.

## BSON type table (canonical)

| Concept | Forbidden | Required |
| --- | --- | --- |
| IDs | bare ObjectId / UUIDv4 | Prefixed ULID strings (`prj_`, `exp_`, …) |
| Embeddings | `list[float]` BSON array | `BinaryVector` FLOAT32 (subtype 9); scalar quantize + storedSource on vector index |
| Timestamps | naive / ISO strings | BSON Date + CodecOptions tz_aware UTC |
| Money / quotas | `float` USD | `Int64` micros (or Decimal128) |
| Metrics | NaN/Inf | Finite float (`allow_inf_nan=False`) |
| Hashes / DEKs | hex/base64 strings | `bytes` binData |
| Metering | standard collection | **Time-series** `usage_events` |
| Multi-doc txn | manual `session=` everywhere | `session.bind()` + `with_transaction` |

## Modules

| File | Role |
| --- | --- |
| `client.py` | `create_saas_mongo_client`, `pack_embedding_f32` |
| `tenant_repo.py` | `ScopedCollection` |
| `project_db.py` | `ProjectScopedDB` (+ claim fencing fields stub) |
| `indexes.py` | `ensure_saas_indexes` |
| `outbox.py` | outbox_events helpers |
| `migrations.py` | schema_version migration runner stub |
