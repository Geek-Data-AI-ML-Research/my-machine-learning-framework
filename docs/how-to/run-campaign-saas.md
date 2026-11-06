# Run the Campaign SaaS stack

How-to. Bring up the local control plane (API, web, Mongo, Redis, MinIO, worker) without spending on RunPod or AWS until you connect credentials.

## Install

From the repository root:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[saas,dev]"
```

## Start Compose

```bash
make up
```

That runs `docker compose -f deploy/docker-compose.yml up --build -d`. Compose project name is `mymlfw` (see top-level `name:` in the file); expand **mymlfw** in Docker Desktop → Containers. Bindings stay on `127.0.0.1` only.

Host ports below avoid common clashes with other local Compose projects (e.g. Iridium on 5173/6379/8080, or a process on 8000). Container-internal ports are unchanged.

| URL / host port | Service |
| --- | --- |
| `http://127.0.0.1:8001/health` | API (host 8001 → container 8000) |
| `http://127.0.0.1:5175/` | Web console (host 5175 → container 80) |
| `http://127.0.0.1:8100/mcp` | MCP (host 8100 → container 8100; starts with the stack) |
| `127.0.0.1:6380` | Redis (host 6380 → container 6379) |
| `http://127.0.0.1:9001/` | Object store console (`mymlfw` / `mymlfwsecret`; Compose uses `pgsty/silo` because Docker Hub `minio/minio` was removed) |

MCP shares Mongo with the API. Mint a PAT in Studio **Settings → Agent PAT**, then point Cursor/Claude at `http://127.0.0.1:8100/mcp` with `Authorization: Bearer <pat>`. Playbook: [Keep a Studio project updated via MCP](agent-mcp-campaign-sync.md).

Stop with `make down`. In Docker Desktop → Containers, expand the **mymlfw** project group.

## Kaggle sync (optional)

Export a [Kaggle API token](https://www.kaggle.com/docs/api) before `make up` (or restart `api` after setting it):

```bash
export KAGGLE_API_TOKEN="$(tr -d '[:space:]' < ~/.kaggle/access_token)"
make up
```

Compose passes `KAGGLE_API_TOKEN` into the API container (also mounts `~/.kaggle` read-only) and stores downloaded competition zips under the `kaggle_data` volume. For a kaggle project:

```bash
curl -s -X POST "http://127.0.0.1:8001/v1/projects/$PROJECT_ID/kaggle/refresh" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"live": true}'

curl -s -X POST "http://127.0.0.1:8001/v1/projects/$PROJECT_ID/kaggle/import-data" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"download": true}'
```

## Register and enable cloud runners

```bash
curl -s -X POST http://127.0.0.1:8001/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"password123","display_name":"You"}'
```

Save `access_token` from the JSON body. Feature flags default off. Turn on billable cloud:

```bash
curl -s -X PATCH http://127.0.0.1:8001/v1/orgs/current/feature-flags \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"cloud_runners": true}'
```

Optional: `"night_shift": true` for Autopilot overnight loops.

## What Compose already sets

| Variable | Value in Compose |
| --- | --- |
| `MYMLFW_MINIO_LIVE` | `1` |
| `MYMLFW_MINIO_ENDPOINT` | `http://minio:9000` |
| `MYMLFW_CLOUD_MOCK` | `0` (live transports once you seal keys) |
| `MYMLFW_GITHUB_OAUTH_STUB` | `true` (local login without GitHub app) |

Full env table: [SaaS environment](../reference/saas-env.md).

## Project Brain advise (Phase E)

After login, Demo Campaign is seeded. Structured advise always runs the citation firewall:

```bash
curl -s -X POST "http://127.0.0.1:8001/v1/projects/$PROJECT_ID/advise" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"$PROJECT_ID\",\"task\":\"next dropout probe\"}"
```

Mid-mission 3-bucket retrieval:

```bash
curl -s -X POST "http://127.0.0.1:8001/v1/projects/$PROJECT_ID/brain/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"$PROJECT_ID\",\"query\":\"dropout SNR\",\"scope\":\"all\"}"
```

MCP tools: `advise_project`, `query_project_brain`. Design notes: [Project Brain RAG](../explanation/project-brain-rag.md).

## Next

Connect a provider and launch a runner: [Connect cloud runners](connect-cloud-runners.md).
