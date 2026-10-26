# Remember, ingest, and search

How-to. Put a lesson where `advise` and `analyze` can retrieve it. Memory is one SQLite file, `recipes/memory.db`, unless you pass `--db`. The dump beside it is `memory_dump.jsonl`. Both database files are gitignored.

## Store a rule

```bash
python -m mymlfw remember \
  --tag blend,cv \
  --rule "Center prompts inside the training fold." \
  --evidence "fold 0 leaked the prompt mean"
```

The same tag set and the same rule are stored once. `--notes` is an alias for `--db`.

## Store an episode

```bash
python -m mymlfw episode add \
  --contest demo \
  --task "prompt centering" \
  --actions "moved the mean into the fold" \
  --outcome worked \
  --lesson "center prompts inside the training fold" \
  --evidence "prompt_mean" \
  --tag cv
```

`--outcome worked` is a lesson you record after the run. `advise` does not write this row. A newer worked row with the same tags and evidence supersedes an older failed row. `--supersedes` takes an episode id such as `4` or `ep_4`.

Recall prints retrieved lessons for a task:

```bash
python -m mymlfw episode recall --task "prompt centering" --data-dir data
```

## Index a tree

```bash
python -m mymlfw ingest --path /path/to/contest --mode auto
```

| `--mode` | What is stored |
| --- | --- |
| `docs` | Markdown, reStructuredText, YAML, JSON, and `experiments.csv` |
| `repo` | Those files plus Python and notebooks |
| `auto` | `repo` when the tree contains `.py` or `.ipynb`, otherwise `docs` |

`advise` uses a narrower pass than `docs`: markdown, reStructuredText, and `experiments.csv` only. A sibling `config.json` is not copied during advise.

Files whose names look like secrets, `.env`, or keys are skipped. A notebook whose source exceeds 256KB after outputs are stripped is skipped. `--sync` refreshes roots already in the database and drops a root that is gone. An unchanged sha256 does not rewrite chunks.

## Search

```bash
python -m mymlfw search "GroupKFold" --type code_pattern
```

The query can be the positional argument or `--query`. The default `--type` is `code_pattern`. Hits include `source_path`, `line_start`, `line_end`, and a snippet.

## What retrieval will not repeat

`analyze` drops a retrieved worked episode or field note when every variable token in its evidence and tags is already a ledger variable. `lora_r=64` is one token, so it matches a ledger variable written the same way. A note with an extra token stays. A note with no tokens stays. A lesson that retrieval did not return does not fill the slot.
