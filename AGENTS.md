# AGENTS.md

mymlfw 0.1.0. Read `llms.txt` before editing a contest. Human documentation is [docs/index.md](docs/index.md).

## Commands

- Tests: `python -m pytest -q` from this checkout. Use the project virtualenv when it exists: `.venv/bin/python -m pytest -q`.
- CLI: `python -m mymlfw`. Failures are one JSON object on stderr with `error_code` and `suggested_fix`.
- Refresh the recipe block inside `llms.txt`: `python -m mymlfw sync-docs`. Keep the file at or under 1500 whitespace tokens. The checkout copy and `src/mymlfw/resources/llms.txt` stay identical.

## Rules that override a local shortcut

The `DO NOT` lines in `llms.txt` are binding. In particular, call `mymlfw.cv.run_oof` instead of writing a GroupKFold loop.

- `src/mymlfw/rag/` does not import `mymlfw.train` or `mymlfw.engines`. Read engine class names with `ast.parse`.
- Engine class names are `TextBlendEngine`, `RankedCandidateEngine`, `AgentZipEngine`, `PortfolioEngine`, and `BenchmarkEngine`.
- `advise` needs a git checkout that has commits and a clean tracked tree. Untracked files do not make the tree dirty.
- `advise` does not insert episodes. The agent records the outcome later with `episode add`.
- Do not install torch unless the task is the train extra. Two tests skip without it.

## Where to change behavior

| Change | Look at |
| --- | --- |
| Ledger and probe guard | `src/mymlfw/campaign/ledger.py` |
| Recipe match | `src/mymlfw/campaign/match.py` |
| Retrieval and advise | `src/mymlfw/rag/` |
| CLI flags | `src/mymlfw/__main__.py` |
| Agent index | `llms.txt` and the packaged copy beside it |
