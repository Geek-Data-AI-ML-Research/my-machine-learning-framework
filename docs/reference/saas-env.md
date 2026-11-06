# SaaS environment and flags

Reference for Campaign SaaS (API, MCP, worker, Compose). Prefix is `MYMLFW_` unless noted. See also [Connect cloud runners](../how-to/connect-cloud-runners.md).

## Process

| Variable | Default | Meaning |
| --- | --- | --- |
| `MYMLFW_ENV` | `dev` | `prod` / `production` fail-closed on missing KEK |
| `MYMLFW_MONGO_URI` | localhost Atlas-local style | AsyncMongoClient URI |
| `MYMLFW_MONGO_DB` | `mymlfw` | Database name |
| `MYMLFW_REDIS_URL` | `redis://127.0.0.1:6379/0` | Idempotency-Key store, LLM/Kaggle rate limits, SSE pub/sub, queue relay. Empty → in-memory fallbacks. Compose maps Redis to host `127.0.0.1:6380` (container still 6379); use `redis://127.0.0.1:6380/0` from the host |
| `MYMLFW_CORS_ORIGINS` | local web origins | Comma-separated |

## Auth

| Variable | Default | Meaning |
| --- | --- | --- |
| `MYMLFW_GITHUB_OAUTH_STUB` | `true` | Dev callback mints a local user |
| `MYMLFW_GITHUB_CLIENT_ID` | empty | Required when stub is false |
| `MYMLFW_GITHUB_CLIENT_SECRET` | empty | Required when stub is false |
| `MYMLFW_SESSION_SECRET` | dev string | Cookie signing (change in prod) |

## Secrets envelope

| Variable | Default | Meaning |
| --- | --- | --- |
| `MYMLFW_KEK_V{n}` | unset | SHA-256 → AES-256-GCM key material |
| `MYMLFW_KEK_VERSION` | `1` | Active KEK version |
| `MYMLFW_REQUIRE_KEK` | unset | `1` forces KEK even in non-prod |

Cipher algorithm at rest: `aes-256-gcm`. Legacy `aes-256-gcm-stub` blobs still decrypt once.

## Object storage

| Variable | Default | Meaning |
| --- | --- | --- |
| `MYMLFW_MINIO_ENDPOINT` | `http://127.0.0.1:9000` | Path-style MinIO URL |
| `MYMLFW_MINIO_BUCKET` | `mymlfw` | Bucket |
| `MYMLFW_MINIO_ACCESS_KEY` | `mymlfw` | Access key |
| `MYMLFW_MINIO_SECRET_KEY` | `mymlfwsecret` | Secret |
| `MYMLFW_MINIO_REGION` | `us-east-1` | Region label |
| `MYMLFW_MINIO_LIVE` | unset | `1` force live HEAD/PUT; `0` force memory; pytest → memory; else live when endpoint set |

Confirm never marks an OOF artifact `ready` without a successful HEAD.

## Cloud providers

| Variable | Default | Meaning |
| --- | --- | --- |
| `MYMLFW_CLOUD_MOCK` | unset | `1` mock transports; `0` live; pytest → mock; else live |
| `MYMLFW_CLOUD_RUNNERS` | `0` | CLI/MCP bootstrap when org policy not synced |
| `MYMLFW_ORG_ID` | CLI default ULID | Org for CLI cloud commands |
| `MYMLFW_RUNPOD_API_BASE` | `https://rest.runpod.io/v1` | RunPod REST base |
| `MYMLFW_RUNNER_IMAGE` | pytorch CUDA image | Pod image |
| `MYMLFW_RUNPOD_DISK_GB` | `50` | Container disk |
| `MYMLFW_RUNPOD_VOLUME_GB` | `20` | Volume |
| `MYMLFW_AWS_AMI_ID` | unset | Required for live AWS launch |
| `MYMLFW_AWS_SUBNET_ID` | unset | Optional |
| `MYMLFW_AWS_SECURITY_GROUP_ID` | unset | Optional |
| `MYMLFW_LEVER_LLM` | unset | `1` requires `saas.llm.judge_lever_mutation` |
| `MYMLFW_AUTOPILOT_ALLOW_UNATTESTED` | unset | `1` allows Autopilot `/tick` without runner `job_token` (tests/dev only) |
| `MYMLFW_LLM_BASE_URL` | unset | OpenAI-compatible base; empty → local hash/template |
| `MYMLFW_LLM_API_KEY` | unset | Bearer for embed/chat when base URL set |
| `MYMLFW_EMBED_MODEL` | `text-embedding-3-small` | Remote embed model id |
| `MYMLFW_CHAT_MODEL` | `gpt-4o-mini` | Remote chat model id |

## Kaggle Public API

Live intel sync and competition data import (`POST …/kaggle/refresh`, `POST …/kaggle/import-data`). Docs: https://www.kaggle.com/docs/api. Compose mounts `~/.kaggle` read-only and a `kaggle_data` volume at `/data/kaggle`. The API service is also on the `edge` network so it can reach `www.kaggle.com`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `KAGGLE_API_TOKEN` / `MYMLFW_KAGGLE_API_TOKEN` | unset | Bearer `KGAT_…` (preferred). Falls back to `~/.kaggle/access_token` |
| `KAGGLE_USERNAME` + `KAGGLE_KEY` | unset | Legacy Basic auth / `kaggle.json` |
| `MYMLFW_KAGGLE_DATA_DIR` | `/data/kaggle` | Where `import-data` writes competition zips (`{project_id}/`) |

Project-sealed tokens (`POST …/kaggle/token`) take precedence over env when present. Never return ciphertext or plaintext tokens in API responses.

## Org feature flags (API)

`PATCH /v1/orgs/current/feature-flags` body fields (all optional booleans):

| Flag | Default | Gates |
| --- | --- | --- |
| `cloud_runners` | `false` | Connect / quote / launch / sweep |
| `night_shift` | `false` | Autopilot overnight |
| `kaggle_sync` | `false` | Reserved |
| `git_sync` | `false` | Reserved |
| `mcp_oauth` | `false` | Reserved |

Entitlement `max_cloud_micros_day` caps quoted spend (0 = unlimited in the current schema default path for some helpers; register defaults to `0`).

## MCP tools (cloud)

Org `feature_flags.cloud_runners` must already be true (API PATCH). Mutators require `idempotency_key`.

| Tool | Mutating | Notes |
| --- | --- | --- |
| `connect_cloud_provider` | yes | `api_key` or `role_arn`; never echoed |
| `disconnect_cloud_provider` | yes | |
| `list_cloud_accounts` | no | |
| `list_cloud_gpus` | no | |
| `quote_cloud_launch` | no | |
| `launch_cloud_runner` | yes | Needs `cost_estimate_micros_hr` + `idempotency_key` |
| `stop_cloud_runner` | yes | `terminate=true` optional; needs `idempotency_key` |
| `list_org_runners` | no | Resource `mymlfw://orgs/{id}/runners` |

Auth: `Authorization: Bearer` / `MYMLFW_MCP_PAT` preferred over tool `pat`. Scopes `mcp:worker` / `mcp:cloud` / `mcp:admin`. HTTP bind refuses `0.0.0.0`.

## Make targets

| Target | Action |
| --- | --- |
| `make up` / `make dev` | Compose up |
| `make down` | Compose down |
| `make openapi` | Regenerate `contracts/openapi.json` |
| `make anti-drift` | AST + OpenAPI presence checks |
| `make test` | `pytest -q` |
