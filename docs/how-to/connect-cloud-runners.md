# Connect cloud runners (RunPod / AWS)

How-to. Seal your own credentials, quote micros/hr, then launch. Local BYOC runners stay the default until you connect a provider. **Quote before create** — launch without matching `cost_estimate_micros_hr` is rejected.

Prerequisites: [Run the Campaign SaaS stack](run-campaign-saas.md) and `feature_flags.cloud_runners=true` on the org.

## Connect RunPod (API)

```bash
curl -s -X POST http://127.0.0.1:8001/v1/orgs/current/cloud/connect/runpod \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Idempotency-Key: connect-rp-1' \
  -H 'Content-Type: application/json' \
  -d '{"api_key":"'"$RUNPOD_API_KEY"'"}'
```

The response never includes the API key. Credentials are sealed with AES-256-GCM (`MYMLFW_KEK_V1` required in production).

## Connect AWS BYOC (API)

```bash
curl -s -X POST http://127.0.0.1:8001/v1/orgs/current/cloud/connect/aws \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Idempotency-Key: connect-aws-1' \
  -H 'Content-Type: application/json' \
  -d '{"role_arn":"arn:aws:iam::123456789012:role/mymlfw-runner","region":"us-east-1"}'
```

The API mints an immutable `external_id` for STS AssumeRole. Put that ExternalId on the trust policy. Control-plane AWS credentials must be able to call AssumeRole into your ARN.

Before the first AWS launch, set a GPU AMI (and optional network) on the API/worker:

| Variable | Required |
| --- | --- |
| `MYMLFW_AWS_AMI_ID` | yes |
| `MYMLFW_AWS_SUBNET_ID` | optional |
| `MYMLFW_AWS_SECURITY_GROUP_ID` | optional |

## Quote then launch

```bash
curl -s 'http://127.0.0.1:8001/v1/orgs/current/cloud/gpus?provider=runpod' \
  -H "Authorization: Bearer $TOKEN"

curl -s 'http://127.0.0.1:8001/v1/orgs/current/cloud/quote?provider=runpod&gpu_type=NVIDIA%20GeForce%20RTX%204090' \
  -H "Authorization: Bearer $TOKEN"

curl -s -X POST http://127.0.0.1:8001/v1/orgs/current/cloud/launch \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Idempotency-Key: launch-1' \
  -H 'Content-Type: application/json' \
  -d '{"provider":"runpod","gpu_type":"NVIDIA GeForce RTX 4090","cost_estimate_micros_hr":440000}'
```

`cost_estimate_micros_hr` must match the quote exactly. Stop or terminate with:

```bash
curl -s -X POST "http://127.0.0.1:8001/v1/orgs/current/runners/$RUNNER_ID/stop" \
  -H "Authorization: Bearer $TOKEN" -H 'Idempotency-Key: stop-1'
```

## CLI

Requires `MYMLFW_CLOUD_RUNNERS=1` (fail-closed). Live calls use the same sealed-key path as the API when `MYMLFW_CLOUD_MOCK` is unset.

```bash
export MYMLFW_CLOUD_RUNNERS=1
export MYMLFW_ORG_ID=org_…
python -m mymlfw cloud connect --provider runpod --api-key "$RUNPOD_API_KEY"
python -m mymlfw cloud gpus --provider runpod
python -m mymlfw cloud launch --provider runpod --gpu-type 'NVIDIA GeForce RTX 4090' --quote-only
python -m mymlfw cloud launch --provider runpod --gpu-type 'NVIDIA GeForce RTX 4090'
python -m mymlfw cloud stop --runner-id rnr_…
```

## MCP

Tools (never return secrets): `connect_cloud_provider`, `disconnect_cloud_provider`, `list_cloud_accounts`, `list_cloud_gpus`, `quote_cloud_launch`, `launch_cloud_runner`, `stop_cloud_runner`, `list_org_runners`.

Authenticate with `Authorization: Bearer` or `MYMLFW_MCP_PAT` (prefer env/header). Every mutating tool **requires** `idempotency_key` (or an `Idempotency-Key` header). Enable `cloud_runners` via the owner API — MCP does not elevate org flags. PAT scopes: `mcp:worker` and/or `mcp:cloud`.

## Mock vs live

| Condition | Behavior |
| --- | --- |
| `MYMLFW_CLOUD_MOCK=1` | In-memory transports (no spend) |
| pytest (`PYTEST_CURRENT_TEST`) | Mock |
| Credentials sealed + mock off | Live RunPod REST / AWS EC2 |

Unit tests never bill. Compose sets `MYMLFW_CLOUD_MOCK=0` so a real key spends.

## Errors you will hit first

| Code / HTTP | Fix |
| --- | --- |
| `feature_disabled` / 403 | `PATCH …/feature-flags` with `cloud_runners: true` |
| `quote_required` / `quote_mismatch` | Re-quote; pass exact `cost_estimate_micros_hr` |
| `kek_missing` | Set `MYMLFW_KEK_V1` in production |
| `cloud_budget_exceeded` | Raise `max_cloud_micros_day` entitlement |
| AWS launch without AMI | Set `MYMLFW_AWS_AMI_ID` |
