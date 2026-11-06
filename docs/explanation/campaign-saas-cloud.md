# Campaign SaaS cloud providers

Explanation of why RunPod/AWS sit behind org flags, sealed credentials, and quote-before-launch — separate from the local `mymlfw cloud launch` script renderer in the core package.

## Two “cloud” surfaces

| Surface | Package | What it does |
| --- | --- | --- |
| Contest CLI renderer | `mymlfw.cloud` | Writes a shell script. Needs `CLOUD_APPROVAL`. Does not start a machine. |
| Campaign SaaS providers | `mymlfw.saas.providers` | Seals keys, quotes micros/hr, creates/stops remotes via live transports. |

Agents and operators using the Studio API or MCP should use the SaaS path. The contest renderer stays for offline notebook / BYOC script workflows.

## Why mock exists

Unit tests and `MYMLFW_CLOUD_MOCK=1` use in-memory transports so CI never bills. Production and Compose leave mock off: once the user seals a RunPod API key or AWS role ARN, `LiveRunPodTransport` / `LiveAwsTransport` run. Pytest sets `PYTEST_CURRENT_TEST`, which forces mock even if `MYMLFW_CLOUD_MOCK=0`.

## Why quote before create

AGENTS anti-drift requires a $/hr quote before first provision. Launch compares `cost_estimate_micros_hr` to the current catalog offer. A mismatch forces a re-quote instead of silently accepting a stale price.

## Why credentials are sealed

API and MCP responses never return provider secrets. At rest the envelope is AES-256-GCM under `MYMLFW_KEK_V{n}`. Production refuses to seal without a KEK (`MYMLFW_ENV=production` or `MYMLFW_REQUIRE_KEK=1`).

## Why flags default off

`cloud_runners` and `night_shift` stay false on new orgs so a stock Compose stack does not spend. Owners enable them with `PATCH /v1/orgs/current/feature-flags`. Autopilot still must not auto-submit to Kaggle.

## Local runner first

Day-3 default is a local BYOC runner (`mymlfw runner` / `POST /v1/runners/register`). Cloud pods are optional capacity behind the same `/v1/orgs/current/runners` list and fair-share picker (local ready → cheapest fitting GPU).
