# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mission

This repo is a scratch space for validating the assumptions underlying strategies and models developed in [quant-research](https://github.com/croicu/quant-research) — the public-facing repo where those findings and strategies are presented. It houses a collection of short, focused experiments — each typically built around its own command-line tool under `src/` — oriented around a single theme: understanding the signals and correlations between financial market parameters. Scripts here are exploratory and disposable by design — quick numerical checks, backtests of specific claims, and sanity tests of assumptions — rather than production-quality or long-lived code.

## Conversation Scope & Outcomes

**One conversation per task.** Each conversation covers a single task from brainstorm through implementation.
Once cc completes the work and you're satisfied, the conversation closes. New tasks = new conversations.

Conversations with Claude follow a structured workflow across chat and code interfaces:

### Brainstorm Phase (Claude Chat)
- **Scope**: Design the feature, explore tradeoffs, converge on decisions
- **Who**: Primarily you + Claude Chat (this interface)
- **Expected outcome**: A populated `tasks/<task-name>.md` file (using the `new_task.md` template)
  with problem statement + design decisions, ready for implementation
- **Deliverable**: Markdown task spec to drop in `./tasks/` folder
- **Conversation status**: Close after delivery, or keep open if immediate feedback is needed

### Implementation Phase (Claude Code)
- **Scope**: Build the feature per the task spec
- **Who**: Claude Code (separate interface/tab)
- **Expected outcome**: Working code following architecture conventions, passing tests, docs updated
- **Deliverable**: Code pushed/ready to merge
- **Conversation status**: This chat stays open for iterations — you can request changes, Claude Chat
  coordinates feedback back to Claude Code

### Iteration Loop (Both)
- If Claude Code's output needs refinement:
  - You describe the issue in this chat
  - Claude Chat clarifies/updates the task spec or provides feedback
  - Claude Code implements the changes
  - Repeat until satisfied
- If no further changes needed: close this conversation after merge

### Key principle
- **Chat** owns the spec and design; **Code** owns the implementation. Both can stay in sync via this open conversation.

## Template Sync

- **Source**: [croicu/tpl-py](https://github.com/croicu/tpl-py)
- **Synced to**: 2026-07-25T02:12:39Z (set by `tasks/repo_setup.md` at instantiation time; left
  unset in `tpl-py`'s own master copy of this file, since the source has nothing to sync
  against)

This repo is either `tpl-py` itself or was generated from it. `tpl-py`'s `ADDENDUM.md` is a
curated, timestamped log of changes meant for downstream instances (new/changed rules,
base-module fixes, obsoleted patterns) — routine housekeeping doesn't get an entry. Which
protocol below applies depends on which repo you're in.

### Reading the addendum (applies in an instance)

1. Fetch `tpl-py`'s `ADDENDUM.md` over plain HTTPS (e.g. `WebFetch` against the raw content
   URL) — no `gh` CLI, no `git clone`, no persistent git remote required.
2. Compare each row's timestamp against this repo's `Synced to` value above.
3. For rows newer than that, fetch only that entry's individual file under `addendum/` (not the
   whole history) and decide whether/how to apply it here.
4. After applying (or deliberately skipping) everything newer, bump `Synced to` above to the
   latest entry's timestamp.

### Writing an addendum entry (applies only in `tpl-py` itself)

1. When making a change meant for downstream instances, add a new file under `addendum/`
   (filename prefixed with an ISO timestamp) describing what changed, why, and what an instance
   should do about it.
2. Append a row to `ADDENDUM.md`'s table (timestamp, title, filename).

## Collaboration rules

- Before implementing any feature or non-trivial change, ask clarifying questions until the intent is unambiguous.
- If anything is unclear or could be interpreted multiple ways, ask — do not assume and implement.

### Task workflow

Tasks are tracked as GitHub issues in this repo, status via labels: `status:brainstorm`,
`status:implementation`, `status:testing`, `status:ready-to-submit`. There is no `status:done`
label — reaching Done means closing the issue. (These labels don't exist on a freshly-created
repo — create them with `gh label create` before the first task needs one.)

For any non-trivial feature or change, follow these stages:

1. **Brainstorm** — copy `tasks/new_task.md` to `tasks/<task-name>.md` with the problem statement; update it with conclusions as the design discussion progresses. This is scratch space for live back-and-forth — an issue isn't required at this stage, but a lightweight tracking issue labeled `status:brainstorm` can be opened for backlog visibility if wanted; either way, `tasks/<task-name>.md` (not the issue) stays the working document until the design converges.
2. **Implementation** — open a GitHub issue (`gh issue create`) with the converged problem statement + conclusions as the body, labeled `status:implementation`. Write the code. `tasks/<task-name>.md` is no longer the source of truth once the issue exists — trim it to a one-line pointer at the issue (or delete it) rather than maintaining both.
3. **Testing** — relabel the issue `status:testing`. Verify correctness; post test results and any open issues as an issue comment.
4. **Ready to Submit** — relabel `status:ready-to-submit`. Run lint + tests; confirm docs are up to date; post a closing summary comment.
5. **Done** — close the issue after merge. Delete `tasks/<task-name>.md` once the issue is closed — the issue (body + comments) is the sole source of truth from that point on, so there's no reason to keep a stale duplicate on disk. (Only applies when a real issue holds the full history; a Done task with no issue keeps its local file.)

## Before committing

Run these before every commit:

```bash
ruff format src/ tests/
ruff check src/ tests/
pytest
```

## Documentation rule

After any change that affects the public interface, CLI, or file formats, update the relevant docs:

- `CLAUDE.md` — commands, architecture notes
- `docs/ARCHITECTURE.md` — modules, data flow, contracts
- `docs/PROTOCOL.md` — CLI signature, file format schemas
- `.vscode/launch.json` — add a debug configuration for each CLI tool's entry point

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run the stock-quote experiment
stock-quote AAPL

# Lint
ruff check src/ tests/
ruff format src/ tests/

# Test
pytest
pytest tests/unit/test_foo.py::test_bar   # single test
```

## Architecture conventions

1. Internal processing uses strongly typed dataclasses.
2. `protocols.py` contains persisted/shared data contracts — pure data only, no behavior. Behavior that operates on protocol types belongs in a dedicated entity/service layer, not on the protocol classes themselves.
3. `contracts.py` contains runtime behavioral interfaces (`Protocol` classes for things like workers/executors), not data.
4. `protocols.py`/`contracts.py` live in the repo-wide `defs` package (`src/defs/`), not inside any single implementation package — they're the specification, not owned by whichever package happens to implement them (e.g. `shared`).
5. Unit tests (`tests/unit/`) must run offline. Integration tests (`tests/integration/`) may hit real external services — deliberately not offline, since fully DI'ing the transport layer for a small component wasn't judged worth the engineering cost. `pytest.ini`'s `testpaths = tests` covers both, so integration tests run as part of the default `pytest` invocation.
6. Prefer explicit, readable Python over clever abstractions.

## Logging

- **Use `Logger`** (`from shared.diagnostics import Logger`) — not bare `print()`.
- **All features log success and errors** — no silent success, no swallowed errors.
- **Message length by severity**:
  - **Success (info)** — short: feature started, feature ended.
  - **Recoverable issues (warning)** — medium: enough context to understand what went wrong and why it was non-fatal.
  - **Errors (error/fatal)** — detailed: full context needed to reproduce and diagnose.
- **Level guide**:
  - `Logger.info` — normal notable events (start, end, success, counts)
  - `Logger.warning` — recoverable problems (retries, skipped items)
  - `Logger.error` / `Logger.fatal` — unrecoverable failures
- **Categories** — every `Logger` method takes an optional `category: str = "general"`, filterable via `settings.json`'s `logCategories` (an open string, not a closed enum — `diagnostics.py` only defines `CATEGORY_GENERAL` as a starting constant). Console output is `[LEVEL][category] message`. **Effective default depends on `debug`**: if `settings.json`'s `logCategories` is left empty/absent, `debug: false` resolves it to `["general"]` (only `general` shown), `debug: true` resolves it to `[]` (unfiltered, show everything); an explicit non-empty `logCategories` always overrides this regardless of `debug`. **`excludedCategories`** is a complementary deny-list, only in effect when the resolved `logCategories` is `[]` (the true unfiltered `debug: true` state) — inert against an explicit non-empty `logCategories` or the plain `debug: false` default.

## Coding Style

- **Protocols are pure data** — `protocols.py` holds dataclasses only. No methods, no logic. Behavior lives in a separate entity/service layer.
- **Explicit over brief** — if two implementations are equivalent, choose the one that is easier to read and debug, even if it is longer.
- **No list/dict/set comprehensions** — use explicit `for` loops. Comprehensions obscure control flow and make multi-step logic harder to follow.
- **No lambdas** — use named functions or plain `for` loops. Lambdas hide intent and cannot be stepped through in a debugger.
- **Import count as SRP signal** — more than 5–10 imports in a file is a hint that the file may be doing too much. Not a hard rule, but worth pausing to consider whether responsibilities should be split.

## New Task

## Pending Tasks
- **Databento intraday volume provider** — [tasks/databento_intraday_volume.md](tasks/databento_intraday_volume.md) (brainstorm; blocked on manual Databento signup/API key)

## Completed Tasks
- **Stock Quote CLI Tool** — [issue #1](https://github.com/croicu/quant-scratch/issues/1)
- **Yahoo provider componentization** — [issue #2](https://github.com/croicu/quant-scratch/issues/2)
- **Day trading chart CLI tool** — [issue #4](https://github.com/croicu/quant-scratch/issues/4)

## Task Template
https://github.com/croicu/quant-scratch/blob/main/tasks/new_task.md