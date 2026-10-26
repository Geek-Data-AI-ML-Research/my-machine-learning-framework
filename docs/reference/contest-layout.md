# Contest layout

Reference for the tree `python -m mymlfw new-contest NAME --dest DIR` creates.

| Path | Role |
| --- | --- |
| `ledger/experiments.csv` | Probe ledger. Header only until the first `probe register`. |
| `ledger/hypotheses.yaml` | `probes: []` placeholder. |
| `STATUS.md` | One-line contest status. |
| `docs/AGENT_HANDOFF.md` | Tells an agent to read `llms.txt`, then the ledger. |
| `llms.txt` | Copy of the framework index at scaffold time. |
| `configs/train.yaml` | Example LoRA config. |
| `engine.py` | `ContestEngine` subclass of `TextBlendEngine`. |
| `kernel/kernel-metadata.json` | Kernel metadata with internet disabled. |
| `kernel/src/cell0_overview.md` | First notebook cell source. |
| `kernel/src/cell1_stage.py` | Payload placeholders. |
| `kernel/src/cell2_run.py` | Worker cell. |
| `kernel/src/cell3_fuse.py` | Fuse cell. |
| `bin/preflight_submit.sh` | Calls `python -m mymlfw preflight --require-scale-report`. |
| `cloud/launch.sh` | Calls `cloud launch` and writes `cloud/rendered.sh`. |
| `custom_plugins/README.md` | Contract for a CPU-only plugin and its sibling test. |

Add tables yourself. The analyzer looks for the first hit among `data/train.csv`, `data/train.parquet`, `train.csv`, `train.parquet`, and `items.jsonl`. The test table is the first hit among `data/test.csv`, `data/test.parquet`, `test.csv`, and `test.parquet`. A `.parquet` file satisfies a required `.csv` name when resolving a data directory.

Data directory order for `resolve_data_dir`:

1. `MYMLFW_DATA_DIR` when set.
2. The path recorded in `.mymlfw/data_dir`.
3. `<contest>/data`.
4. `/kaggle/input` and its child directories, when that directory exists.
5. The contest directory itself.

`advise` adds the symlink and the `.mymlfw/data_dir` marker. It also writes `docs/MYMLFW_ADVICE.md` and `engine_mymlfw.py` in the worktree. Those two files are not part of `new-contest`.
