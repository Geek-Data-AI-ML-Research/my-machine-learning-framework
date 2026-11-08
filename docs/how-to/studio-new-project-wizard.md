# Start a Studio project with the DS playbook wizard

How-to. Create a Campaign SaaS project so the first roadmap is EDA → validation → dumb baseline → features — never “pick GPT first.”

## When to use this

- You opened Studio after `make up` and need a real campaign (not only Demo).
- You want Kaggle and commercial projects to share the same first ~60% of process, then diverge.

## Open the wizard

1. Start the stack: [Run the Campaign SaaS stack](run-campaign-saas.md).
2. Open Studio (`http://127.0.0.1:5175/` or the host port you use).
3. Sign in / register (Compose sets GitHub OAuth stub for local).
4. Click **New project** → route `#studio/new`.

## Steps (in order)

| Step | You choose | Why |
| --- | --- | --- |
| **Venue** | Name + Commercial / standalone **or** Kaggle | Same early loop; last 40% goals differ (ROI/latency vs LB squeeze). |
| **Data** | Tabular · Text · Vision · Sequential | Sets the *recommended* baseline family only — still no heavy model yet. |
| **CV** | StratifiedKFold · Time+group · GroupKFold | Leak-free yardstick before any feature or model claim. Venue suggests a default. |
| **Baseline** | LightGBM / Logistic / XGB / CatBoost + goal threshold | 15–60s CPU baseline and importance leak alarm — not a neural net. |
| **Links** | Kaggle slug (required if Kaggle) · optional git | Tokens stay in Settings / Kaggle — not in the project name. |
| **Create** | Review + optional roadmap seed | Writes the project, then seeds playbook artifacts. |

The sticky **Expert coach** panel restates the rule for the current step.

## What create writes

Uses existing APIs only (no new JSON fields):

1. `POST /v1/projects` — name, kind (`standalone` \| `kaggle`), primary goal, optional `kaggle_competition` / `git_remote`.
2. If **Seed Stages 1–5 on Roadmap** is checked (default):
   - five `POST /v1/projects/{id}/roadmap` strategies (priorities 10–50): EDA → CV lock → dumb baseline → domain features → Kaggle squeeze **or** commercial deploy path;
   - one `POST /v1/projects/{id}/progress` note locking venue / modality / CV / baseline / threshold.
3. Studio navigates to **Roadmap** (planned filter) so the next agent turn starts on Stage 1.

Uncheck the seed box only when you intentionally want an empty roadmap.

## After create

- **Roadmap** — execute Stage 1 before changing Stage 2 folds.
- **Kaggle** projects — sync LB from the Kaggle mode when the API token is sealed ([run-campaign-saas](run-campaign-saas.md#kaggle-sync-optional)).
- **Agents** — mint a PAT and follow [Keep a Studio project updated via MCP](agent-mcp-campaign-sync.md); do not invent a parallel process that skips the seeded stages.

## Anti-patterns

- Starting with a large LLM / vision net before Stages 1–3.
- Changing CV after Stage 2 without recording a new plan and dead-ending the old split.
- Using Kaggle-style stratified folds on live time-series commercial labels (or the reverse) without documenting why.
