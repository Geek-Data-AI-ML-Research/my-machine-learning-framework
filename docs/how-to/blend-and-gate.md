# Blend and gate a submission

How-to. Fit blend weights on out-of-fold predictions, then refuse a submission that fails the ledger, the hash, or the kernel rules.

## Align and weight

Each branch is a `.npz` prediction bundle. Branches must share ids. Class order mismatches raise `CLASS_ORDER_MISMATCH`. The suggested fix is `blend reorder-classes`.

```bash
python -m mymlfw blend optimize \
  --oof branch_a.npz \
  --oof branch_b.npz \
  --labels y.csv \
  --manifest manifest.json \
  --metric log_loss
```

`--metric` is `log_loss`, `accuracy`, or `balanced_accuracy`. Add `--l2` to change the default `0.05`.

Check redundancy before you keep a branch:

```bash
python -m mymlfw blend diversity \
  --oof branch_a.npz --cv 0.81 \
  --oof branch_b.npz --cv 0.80
```

`--strict` turns a high-redundancy warning into an error.

## Check train against test

```bash
python -m mymlfw check-shift \
  --train data/train.csv \
  --test data/test.csv \
  --numeric feature_1
```

A detected shift returns `SHIFT_DETECTED`. The analyzer also adds `check_shift` to its retrieval query when the train and test column sets differ.

## Gate the file

Register the probe first. `kill` and `confirmed-large-gap` return `PROBE_CLOSED`. The kernel document must set `enable_internet` to false. `gate.json`, `leak.json`, and `runtime.json` must each carry the artifact sha256.

```bash
python -m mymlfw preflight \
  --require-scale-report \
  --ledger ledger/experiments.csv \
  --experiment-id exp_002 \
  --artifact submission.parquet \
  --gate gate.json \
  --leak leak.json \
  --runtime runtime.json \
  --kernel kernel/kernel-metadata.json \
  --scale-report scale.json
```

Build the scale report from the train table:

```bash
python -m mymlfw simulate-test \
  --train data/train.csv \
  --rows 25000 \
  --sample-seconds 1 \
  --out scale.json
```

Check the submission shape:

```bash
python -m mymlfw submit check --kind id_label --file submission.csv --classes a,b
```

`--kind ranked` checks a candidate list. The default cap is 25.

## Kernel payload

```bash
python -m mymlfw kernel build \
  --src kernel/src \
  --out contest.ipynb \
  --payload worker.py
```

A payload whose name contains `weight`, or a `.npz` payload, raises `PAYLOAD_KIND`. Payloads over 512000 bytes raise `PAYLOAD_TOO_LARGE`. Ship weights as a dataset, not inside the notebook.

`pack-deps` prints a download plan only when you pass `--dry-run`. A live download raises `PACK_DEPS_LIVE`.
