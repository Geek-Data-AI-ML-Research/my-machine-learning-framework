# mymlfw documentation

Version 0.1.0. These pages follow the [Diátaxis](https://diataxis.fr/) split: a tutorial to learn the loop, how-to guides for one task, reference for lookup, and explanation for why the pieces are separated.

| If you are | Start here |
| --- | --- |
| New to the package | [Tutorials](#tutorials) |
| Doing one job | [How-to guides](#how-to-guides) |
| Checking a flag, column, or path | [Reference](#reference) |
| Deciding whether a change belongs in this package | [Explanation](#explanation) |
| A coding agent | [`llms.txt`](../llms.txt) and [`AGENTS.md`](../AGENTS.md) |
| The published marketing site | [`site/index.html`](../site/index.html) → GitHub Pages |

Install with `pip install -e .` from the repository root. Python 3.11 or newer. The command is `python -m mymlfw`. A failure is one JSON object on stderr.

## Tutorials

Learning-oriented. Follow the page in order.

- [First contest](tutorials/first-contest.md) — install, scaffold a contest, register one probe, read the analyzer.

## How-to guides

Task-oriented. Each page assumes the tutorial is done.

- [Record a probe](how-to/record-a-probe.md)
- [Advise a contest](how-to/advise-a-contest.md)
- [Blend and gate a submission](how-to/blend-and-gate.md)
- [Remember, ingest, and search](how-to/use-memory.md)
- [Run the Campaign SaaS stack](how-to/run-campaign-saas.md)
- [Connect cloud runners (RunPod / AWS)](how-to/connect-cloud-runners.md)
- [MCP walking skeleton](how-to/mcp-walking-skeleton.md)
- [Keep a Studio project updated via MCP](how-to/agent-mcp-campaign-sync.md)

## Reference

Information-oriented. Tables, not a narrative.

- [CLI](reference/cli.md)
- [Contest layout](reference/contest-layout.md)
- [Ledger](reference/ledger.md)
- [SaaS environment and flags](reference/saas-env.md)
- [SaaS plan → API → GUI parity](reference/saas-plan-parity-matrix.md)

## Explanation

Understanding-oriented. Read these before changing a boundary.

- [Architecture](explanation/architecture.md)
- [Invariants](explanation/invariants.md)
- [Campaign SaaS cloud providers](explanation/campaign-saas-cloud.md)
- [Project Brain RAG](explanation/project-brain-rag.md)
- [GM cockpit](explanation/gm-cockpit.md)
- [Scoped Mongo](explanation/scoped-db.md)
- [Night shift](explanation/night-shift.md)
