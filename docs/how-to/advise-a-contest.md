# Advise a contest

How-to. Open a git worktree that contains an advice brief and the next five steps. The contest checkout needs at least one commit. Tracked changes must be committed or stashed. Untracked files are allowed.

## Run

From the contest directory, or pass its path:

```bash
python -m mymlfw advise --dir . --task "next experiment"
```

`--db` selects the SQLite file. The default is `recipes/memory.db` in the framework checkout. That file is gitignored.

On success, stdout JSON includes:

| Field | Meaning |
| --- | --- |
| `worktree_dir` | Sibling directory `<contest>-advise-<id>` |
| `branch` | `mymlfw/advise-<contest>-<id>` |
| `engine_class` | One of the five engine names |
| `files_written` | Files created in the worktree |
| `next_command` | `pytest && ./bin/preflight_submit.sh` when that script was written, otherwise `pytest` |

The brief is `docs/MYMLFW_ADVICE.md` in the worktree. Its headings are fixed: traps, playbook, learned patterns, then candidate files. `# NEXT STEPS` is inserted above the `episode add` command.

## What the worktree contains

- `engine_mymlfw.py`, a subclass of the matched engine. It does not import training code.
- A relative symlink `data` when the source contest has a data directory, plus `.mymlfw/data_dir` with the original path.
- `bin/preflight_submit.sh` when the source or destination already has a `bin/` directory, or when a retrieved note mentions preflight.
- A `mymlfw` dependency in `pyproject.toml` or `requirements.txt` when those files exist.

`recipes/memory.db` is not created inside the worktree. If worktree creation fails after `git worktree add`, the worktree is removed and the branch is deleted.

## Read the same advice without a branch

```bash
python -m mymlfw analyze --dir . --task "next experiment"
```

`analyze` does not create a worktree and does not write the contest unless you pass `--out`.

## Record the outcome yourself

`advise` does not insert an episode. After cross-validation or preflight, run the `episode add` command at the bottom of the brief. Set `--outcome` to `worked`, `failed`, or `partial`.

## Remove a worktree

```bash
python -m mymlfw advise --dir . --clean --id SHORTID
```

`SHORTID` is the id in the branch name. `--clean` does not require a clean tracked tree.

## Errors you will hit first

| `error_code` | Fix named by the CLI |
| --- | --- |
| `GIT_REQUIRED` | Run advise inside an existing git checkout. |
| `GIT_NO_COMMITS` | `git commit -m 'initial'` |
| `DIRTY_TREE` | Commit or stash tracked changes. |
| `ADVICE_EXISTS` | Remove an old advise worktree and retry. |
