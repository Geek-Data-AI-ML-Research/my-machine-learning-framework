# mymlfw

Local toolkit for ML and Kaggle contests. Version 0.1.0. It keeps one experiment ledger, checks blends and submissions, and gives a coding agent a memory of what already failed. The same repo also ships a **Campaign SaaS** control plane (API, Studio web, MCP, worker) for multi-project campaigns.

This repository is the documentation and the package. Human reading starts at [docs/index.md](docs/index.md). Coding agents read [llms.txt](llms.txt), then [AGENTS.md](AGENTS.md).

## Install (local CLI)

Requires Python 3.11 or newer.

```bash
python -m venv .venv
.venv/bin/pip install -e .
```

That install covers the ledger, metrics, GroupKFold, blends, the submit gate, the kernel builder, the five engines, cloud script rendering, and retrieval. Tests that import torch skip until the train extra is installed:

```bash
.venv/bin/pip install -e '.[train]'
```

For SaaS Python extras (API / MCP / worker outside Compose):

```bash
.venv/bin/pip install -e '.[saas,dev]'
```

## Campaign SaaS — Docker setup

Bring up the full local stack (MongoDB, Redis, object store, API, worker, Studio web, MCP) with Docker Compose. Data-plane ports bind **`127.0.0.1` only**.

### Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- Optional: a [Kaggle API token](https://www.kaggle.com/docs/api) if you want live competition sync

### Start

From the repository root:

```bash
make up
# same as: make dev
# or:      docker compose -f deploy/docker-compose.yml up --build -d
```

Compose project name is **`mymlfw`** (expand that group in Docker Desktop → Containers). First boot builds the API/web images; later starts reuse the cache.

| URL / host port | Service |
| --- | --- |
| `http://127.0.0.1:8001/health` | API (host **8001** → container 8000) |
| `http://127.0.0.1:5175/` | Studio web console |
| `http://127.0.0.1:8100/mcp` | MCP (streamable HTTP) |
| `127.0.0.1:27017` | MongoDB |
| `127.0.0.1:6380` | Redis (host **6380** → container 6379) |
| `http://127.0.0.1:9000` | Object store (S3 API; Silo / MinIO-compatible) |
| `http://127.0.0.1:9001/` | Object store console (`mymlfw` / `mymlfwsecret`) |

Stop the stack:

```bash
make down
# or: docker compose -f deploy/docker-compose.yml down
```

### First login (local)

Compose sets `MYMLFW_GITHUB_OAUTH_STUB=true`, so you can register without a GitHub OAuth app:

1. Open Studio: [http://127.0.0.1:5175/](http://127.0.0.1:5175/)
2. Or register via API:

```bash
curl -s -X POST http://127.0.0.1:8001/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"password123","display_name":"You"}'
```

Save `access_token` from the response. Demo campaign data is seeded after login.

### Agent MCP

1. In Studio: **Settings → Agent PAT** — mint a PAT
2. Point Cursor/Claude at `http://127.0.0.1:8100/mcp` with `Authorization: Bearer <pat>`

Playbook: [Keep a Studio project updated via MCP](docs/how-to/agent-mcp-campaign-sync.md).

### Optional: Kaggle token before `make up`

```bash
export KAGGLE_API_TOKEN="$(tr -d '[:space:]' < ~/.kaggle/access_token)"
make up
```

Compose also mounts `~/.kaggle` read-only into the API container.

### More detail

- [Run the Campaign SaaS stack](docs/how-to/run-campaign-saas.md) — ports, feature flags, advise curls
- [Connect cloud runners](docs/how-to/connect-cloud-runners.md) — RunPod / AWS after sealing keys
- [SaaS environment reference](docs/reference/saas-env.md)
- Compose file: [`deploy/docker-compose.yml`](deploy/docker-compose.yml)

## Tests

```bash
.venv/bin/python -m pytest -q
# or: make test
```

Phase modules run from `tests/test_phase1_package.py` through `tests/test_phase16_analyze.py`. Retrieval wiring is `tests/test_rag_wiring.py`. SaaS anti-drift: `make anti-drift`.

## Web page (marketing)

[site/index.html](site/index.html) is the GitHub Pages page. It loads [ascii.rest](https://ascii.rest/) 0.4.0 for the title and the typed command line. `.github/workflows/pages.yml` publishes the `site/` directory on every push to `main`.

In the repository settings, set Pages to **GitHub Actions**. After the first green deploy the address is `https://<owner>.github.io/<repo>/`.

## First CLI command

```bash
.venv/bin/python -m mymlfw version
```

The contest walkthrough is [docs/tutorials/first-contest.md](docs/tutorials/first-contest.md).
