# mymlfw

Local toolkit for ML and Kaggle contests. Version 0.1.0. It keeps one experiment ledger, checks blends and submissions, and gives a coding agent a memory of what already failed.

This repository is the documentation and the package. Human reading starts at [docs/index.md](docs/index.md). Coding agents read [llms.txt](llms.txt), then [AGENTS.md](AGENTS.md).

## Install

Requires Python 3.11 or newer.

```bash
pip install -e .
```

That install covers the ledger, metrics, GroupKFold, blends, the submit gate, the kernel builder, the five engines, cloud script rendering, and retrieval. Tests that import torch skip until the train extra is installed:

```bash
pip install -e '.[train]'
```

## Tests

```bash
python -m pytest -q
```

Phase modules run from `tests/test_phase1_package.py` through `tests/test_phase16_analyze.py`. Retrieval wiring is `tests/test_rag_wiring.py`.

## Web page

[site/index.html](site/index.html) is the GitHub Pages page. It loads [ascii.rest](https://ascii.rest/) 0.4.0 for the title and the typed command line. `.github/workflows/pages.yml` publishes the `site/` directory on every push to `master`.

In the repository settings, set Pages to **GitHub Actions**. After the first green deploy the address is `https://<owner>.github.io/mymlfw/`.

## First command

```bash
python -m mymlfw version
```

The contest walkthrough is [docs/tutorials/first-contest.md](docs/tutorials/first-contest.md).
