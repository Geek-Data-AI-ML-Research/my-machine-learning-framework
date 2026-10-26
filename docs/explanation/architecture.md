# Architecture

Explanation of why mymlfw is split the way it is. Version 0.1.0. It is a local, single-user package. It is not a training service and it does not call Kaggle, AWS, or RunPod.

## Layers

The CLI in `src/mymlfw/__main__.py` is the only process boundary. Library calls raise `MymlfwError`. The CLI prints `to_dict()` as one JSON object.

| Layer | Packages | Job |
| --- | --- | --- |
| Campaign | `campaign`, `metrics`, `cv` | Ledger, data profile, recipe match, GroupKFold through `cv.run_oof`. |
| Decision | `blend`, `submit`, `sanitize` | Align predictions, weight them, and refuse a bad submission. |
| Delivery | `kernel`, `engines`, `cloud` | Build an offline notebook, run one of five engines, render a launch script. |
| Memory | `rag`, `scaffold` | SQLite retrieval, episodes, the worktree brief, the read-only analyzer. |
| Train | `train` | Optional. Dry-run checks ship in the core install. A backward pass needs the `train` extra. |

`rag` does not import `train` or `engines`. The analyzer learns the engine class by parsing the file. That keeps a retrieval import from pulling in torch.

## Recipe match

Six cards live in `recipes/*.yaml` and in the packaged copy under `src/mymlfw/resources/recipes/`. `profile-data` asks `recommend_recipes` for at most two cards. A card scores only when a signature agrees with the profile. `circuit-portfolio` sets `has_text_col` and `has_group_col` to false, so a profile never gives it a positive score. The analyzer still maps that card to `PortfolioEngine` when a caller names it.

The static map is:

| Card | Engine |
| --- | --- |
| `closed-set-llm-id` | `TextBlendEngine` |
| `grouped-text` | `TextBlendEngine` |
| `ranking` | `RankedCandidateEngine` |
| `code-agent` | `AgentZipEngine` |
| `circuit-portfolio` | `PortfolioEngine` |
| `benchmark` | `BenchmarkEngine` |

## Retrieval

`Store` is SQLite with WAL and FTS5. Tokens keep `_`, `@`, `=`, and `-`, so `lora_r=64` survives indexing. Ranking is reciprocal rank fusion of BM25 and character TF-IDF (character n-grams 3 through 5). Character hits below cosine 0.08 are dropped. A hit too close to an already chosen chunk (character cosine above 0.85) is skipped. Age breaks ties. It is not added into the score.

`retrieve` fills four slots: two recipes, three negative chunks, three positive chunks, and two code or document chunks. Query expansion adds group-CV terms, class-balance terms, length terms, or `check_shift` terms from the train and test frames. `analyze` passes both frames.

`advise` indexes the contest's markdown, reStructuredText, and `experiments.csv` before it retrieves. It then opens a git worktree, writes the brief, and calls `analyze` so `# NEXT STEPS` describes the files just written. The episode row is left for the agent.

## What the package will not decide

A public leaderboard number is an input to `probe score`. The package can refuse a closed probe and can tell the agent which variable not to repeat. It cannot submit that file or claim the score moved.
