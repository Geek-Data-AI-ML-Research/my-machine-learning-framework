# First contest

Tutorial. You finish with a contest directory, one pending probe, and an analyzer report. No torch, no Kaggle account, and no git remote.

## Install

From this repository:

```bash
pip install -e .
python -m mymlfw version
```

The version line is `0.1.0`.

## Scaffold

```bash
python -m mymlfw new-contest demo --dest .
```

That creates `demo/` with an empty ledger, a kernel skeleton, `engine.py`, and `bin/preflight_submit.sh`. The layout is listed in [Contest layout](../reference/contest-layout.md).

## Register one change

A probe names one variable and the public-score band you expect before you train.

```bash
python -m mymlfw probe register \
  --ledger demo/ledger/experiments.csv \
  --experiment-id exp_001 \
  --baseline-id base \
  --variable lora_r=16 \
  --band-low 0.70 \
  --band-high 0.80
```

The new row has verdict `pending`. A second probe with the same variable and the same band is rejected. Details are in [Record a probe](../how-to/record-a-probe.md).

## Ask what to do next

```bash
python -m mymlfw analyze --dir demo
```

Success is JSON on stdout. `next_steps` holds at most five items. On this empty contest the report has no kill and no train table. After you add `data/train.csv` and a scored ledger, the same command uses those files. The command writes nothing in `demo/` unless you pass `--out`.

## What this tutorial did not do

`advise` needs a git commit and is covered in [Advise a contest](../how-to/advise-a-contest.md). Training needs `pip install -e '.[train]'` and is not part of this path. The package records a public score. It does not submit to Kaggle.
