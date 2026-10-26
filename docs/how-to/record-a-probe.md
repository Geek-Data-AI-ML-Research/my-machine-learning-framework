# Record a probe

How-to. Update `ledger/experiments.csv` so the next run changes one variable and preflight can accept it.

## Register

`baseline_id` is the experiment this row changes. `change_count` stays 1. Both band edges are required.

```bash
python -m mymlfw probe register \
  --ledger ledger/experiments.csv \
  --experiment-id exp_002 \
  --baseline-id exp_001 \
  --variable lora_r=64 \
  --band-low 0.75 \
  --band-high 0.85 \
  --note "rank 64 against the rank-16 baseline"
```

Column meanings are in [Ledger](../reference/ledger.md).

## After cross-validation

```bash
python -m mymlfw probe update-cv \
  --ledger ledger/experiments.csv \
  --experiment-id exp_002 \
  --cv-mean 0.81 \
  --cv-std 0.01
```

`cv_delta` is recomputed from the baseline row.

## After a public score

```bash
python -m mymlfw probe score \
  --ledger ledger/experiments.csv \
  --experiment-id exp_002 \
  --public-score 0.79
```

If the public score falls outside the registered band, the verdict becomes `confirmed-large-gap`.

## Close the row

```bash
python -m mymlfw probe verdict \
  --ledger ledger/experiments.csv \
  --experiment-id exp_002 \
  --verdict promote-candidate \
  --note "keep rank 64"
```

Allowed verdicts are `pending`, `kill`, `promote-candidate`, and `confirmed-large-gap`. `kill` and `confirmed-large-gap` make a later preflight return `PROBE_CLOSED`.

## Pin the artifact

```bash
python -m mymlfw probe sha \
  --ledger ledger/experiments.csv \
  --experiment-id exp_002 \
  --artifact submission.parquet
```

Preflight checks this hash against the file you pass it.
