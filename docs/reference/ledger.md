# Ledger

Reference for `ledger/experiments.csv`. Columns, in order:

| Column | Written by |
| --- | --- |
| `date` | `probe register`, as `YYYY-MM-DD`. |
| `experiment_id` | `probe register`. Reusing an id for a different variable raises `DUPLICATE_EXPERIMENT`. |
| `baseline_id` | `probe register`. Required. |
| `variable` | `probe register`. One name, including a form such as `lora_r=64`. |
| `change_count` | Always `1`. Any other count raises `SECOND_VARIABLE`. |
| `cv_mean` | `probe update-cv`. |
| `cv_std` | `probe update-cv` when `--cv-std` is passed. |
| `cv_delta` | Recomputed when `cv_mean` is set, against the baseline row. |
| `expected_band_low` | `probe register`. |
| `expected_band_high` | `probe register`. |
| `public_score` | `probe score`. |
| `cv_lb_gap` | Absolute gap between `cv_mean` and `public_score` when both exist. |
| `artifact_sha256` | `probe sha`, and preflight when the cell is still empty. |
| `verdict` | `pending` at registration. See below. |
| `note` | `--note` on register or verdict. |

## Verdicts

| Value | Meaning |
| --- | --- |
| `pending` | Registered, not closed. |
| `promote-candidate` | Kept. Archive lists it under proven wins when `cv_delta` is set. |
| `kill` | Do not repeat. Preflight returns `PROBE_CLOSED`. |
| `confirmed-large-gap` | Public score was outside the registered band. Preflight returns `PROBE_CLOSED`. |

`probe score` sets `confirmed-large-gap` by itself when the public score is outside the band. Other verdicts are set with `probe verdict`. `BAD_VERDICT` names anything outside the four values.

A probe is identified by the variable string plus the two band edges. Registering that identity again raises `DUPLICATE_PROBE`, including while the first row is still `pending`. The same `experiment_id` and the same identity returns the existing pending row.

Pending rows are not retrieval chunks. A non-pending `kill` or `confirmed-large-gap` is a trap. `promote-candidate` is a win.

## Archive order

`archive-contest` writes `## proven_wins` with the largest `cv_delta` first, and `## known_traps` from `kill` and `confirmed-large-gap` with the most negative `cv_delta` first.
