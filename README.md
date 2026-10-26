# mymlfw

Campaign, cross-validation, blend, submission, and kernel toolkit for ML and Kaggle work.

## Install

```bash
pip install -e .
pip install -e '.[train]'
```

`pip install -e .` covers the ledger, metrics, GroupKFold, blends, submit gate, kernel builder, engines, and cloud templates. The `train` extra adds torch, transformers, peft, and safetensors. Tests that need those packages skip when the extra is absent.

## Phases

Each phase has one test module. Run that module before starting the next phase.

1. `pytest tests/test_phase1_package.py` — import, version command, JSON errors.
2. `pytest tests/test_phase2_campaign.py` — ledger, probe guard, profile, metrics.
3. `pytest tests/test_phase3_cv_blend.py` — folds, alignment, pools, weights, shift.
4. `pytest tests/test_phase4_submit.py` — zip, preflight, scale report, sanitizer.
5. `pytest tests/test_phase5_kernel.py` — notebook payload, subprocess, length sort, wheels.
6. `pytest tests/test_phase6_heads.py` — shrunk twin and soft-target fit.
7. `pytest tests/test_phase7_train.py` — dry-run, GRPO, soup, probe guard.
8. `pytest tests/test_phase8_engines.py` — text, ranked, agent, portfolio, benchmark.
9. `pytest tests/test_phase9_cloud.py` — approval gate and launch script.
10. `pytest tests/test_phase10_scaffold.py` — new contest, recipes, archive.

`pytest` runs the full suite.

## Knowledge flywheel

`archive-contest` writes `## proven_wins` (largest `cv_delta` first) and `## known_traps` (`kill` and `confirmed-large-gap`, most negative `cv_delta` first). `--recipe <id>` appends those lists onto that recipe card.

`profile-data` always adds a `## recommended` section. Recipe `signatures` pick up to two cards from the data fingerprint.

`remember` appends a tagged rule to `recipes/memory.db` (or `--db` / `--notes`). The same tag set and rule are stored once. `recipes --match` searches those notes.

`promote-plugin` copies a CPU-only plugin into `contrib/` after its sibling test passes and an import scan accepts it. `new-contest` creates `custom_plugins/` for that contract.

`sync-docs` refreshes the `llms.txt` index between `<!-- mymlfw-index -->` markers. The file stays at or under 1500 whitespace-delimited tokens. A longer draft raises `LLMSTXT_TOO_LONG` and leaves the previous file unchanged.
