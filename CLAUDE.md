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

## Cross-Repo Coordination

This repo has a real data-contract relationship with
[croicu/quant-data](https://github.com/croicu/quant-data) (the market-data warehouse — schema,
migrations, and eventually ingest/read tooling): quant-data is the producer, quant-scratch (and any
future consumer repos) is the client. Coordination happens via GitHub issues, not a changelog file
— unlike the template-propagation model in "Template Sync" above, which suits a one-to-many static
template but not an active two-way contract between two independently-evolving repos.

**Placement rule**: a cross-repo issue lives in whichever repo owns the actionable follow-up, not
necessarily where the need originated:
- **quant-data ships a breaking or notable change** (schema migration, changed contract, a
  deprecated column) → open an issue in **quant-scratch** (and any other consumer repo) announcing
  it, since that's where the reacting work happens.
- **quant-scratch needs something from quant-data** (new ticker/column support, a schema change, a
  bug in returned data) → open an issue in **quant-data** requesting it, since that's where the
  building work happens.

**Conventions**:
- Label every cross-repo issue `cross-repo` (alongside the normal `status:*` label) so these
  threads are filterable apart from each repo's own internal work.
- Always cross-link: the issue body must reference the originating repo/issue/commit (e.g. "See
  croicu/quant-data#12" or "Needed for croicu/quant-scratch's day-chart work"), so either side is
  navigable from the other.
- Use `gh issue create --repo <owner>/<repo>` to open a cross-repo issue directly from wherever
  you're working — no need to switch working directories first.

**Future: multiple consumers.** Not built yet — quant-scratch is the only consumer so far. See
quant-data's `CLAUDE.md` for the planned design (a consumer registry, fan-out issues, and a
rollout-tracking issue) once a second consumer repo actually exists.

## Collaboration rules

- Before implementing any feature or non-trivial change, ask clarifying questions until the intent is unambiguous.
- If anything is unclear or could be interpreted multiple ways, ask — do not assume and implement.
- After finishing a change, stop and let the user review/test it while it's still visible as an uncommitted diff in the editor (e.g. VS Code's Source Control view) — don't run `git add`/`git commit` right after finishing an edit. Wait for explicit go-ahead before committing.

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

- **Provider comparison view** — [tasks/provider_comparison_view.md](tasks/provider_comparison_view.md) (brainstorm, 2026-08-02). Side-by-side comparison across `ibkr`/`quant-data`/`yahoo` (or `ibkr`/`yahoo` for `stock-quote`) instead of one provider per run. Open questions: scope (day-chart, stock-quote, or both), mechanism (`--providers` flag + extended chart grid, a CSV-shape change, or a dedicated new comparison tool), partial-failure handling, IBKR pacing interaction.

## Pending Tasks
- **IBKR historical-data pipeline** — [tasks/ibkr_fetch_historical_spy.md](tasks/ibkr_fetch_historical_spy.md) / [issue #11](https://github.com/croicu/quant-scratch/issues/11) (testing, 2026-08-01). `IBKRIntraDay` (`src/shared/providers/ibkr.py`), validated live against SPY 7/31/2026 (960 clean 1-min bars, real extended-hours volume). Now wired into `day-chart` — see below. Not yet formally closed.
- **day-chart / IBKR integration** — [tasks/day_chart_ibkr_integration.md](tasks/day_chart_ibkr_integration.md) / [issue #12](https://github.com/croicu/quant-scratch/issues/12) (testing, 2026-08-02). `day_chart.cli` now has a `--provider {ibkr,quant-data,yahoo}` flag (third choice added later — see below), **defaulting to `ibkr`** (a deliberate behavior change — IBKR has strictly more data than the Yahoo-sourced quant-data path). New optional `ibkr` `settings.json` section (`Settings.ibkr`/`IBKRSettings`, all fields defaulted, mirrors `postgres` minus the required-keys validation, shared by `stock-quote` below). Range mode caps `--provider ibkr` at 30 days (`AppError` before any requests) as a margin under IBKR's documented pacing limits — a live probe (7 rapid same-contract requests) found no violation well below this cap, but it's an untested-but-documented ceiling, not a measured one. Verified live end-to-end (`day-chart SPY --date 2026-07-31` with no flags → 960-bar CSV via the real Gateway) and the cap rejection (a 61-day range → clean exit 1). `IBKRIntraDay.connect()` also now passes `fetchFields=StartupFetch(0)` — silences a Read-Only-API-mode rejection + Gateway popup from `ib_async`'s default startup account/order fetch (irrelevant to historical bars), and incidentally cut connect time from ~10s to ~10ms.
- **stock-quote / IBKR integration** — [tasks/stock_quote_ibkr_integration.md](tasks/stock_quote_ibkr_integration.md) / [issue #13](https://github.com/croicu/quant-scratch/issues/13) (testing, 2026-08-02). New `IBKRQuote` (`src/shared/providers/ibkr.py`) implementing `YahooFinanceProvider.fetch_quote`; `stock-quote` gains the same `--provider {yahoo,ibkr}` flag, but **stays defaulted to `yahoo`** — unlike day-chart's case, IBKR isn't a strict improvement here (confirmed empirically: real-time quotes need a paid subscription this account doesn't have, error 10089; free tier is delayed ~15-20min vs. Yahoo's near-real-time). `IBKRQuote` tries live first, falls back to delayed automatically, and reports which actually happened via a `StockQuote.delayed` field. Follow-up same day: also added `StockQuote.provider: str` (required, no default) so output/CSV records *which* provider answered — each provider stamps its own `PROVIDER_NAME` constant, and `stock_quote.cli.PROVIDER_YAHOO`/`PROVIDER_IBKR` are now aliases of those (not independent literals), so the `--provider` flag can't drift from a quote's self-reported source. Caught a real `ib_async` quirk along the way: `Ticker.__post_init__` silently resets `last`/`volume`/etc. back to NaN unless `created=True` is passed to the constructor. 98/98 tests pass; verified live (both providers return correct quotes with correct `provider`/`delayed` columns).
- **day-chart / Yahoo provider restored** — [tasks/day_chart_yahoo_provider.md](tasks/day_chart_yahoo_provider.md) / [issue #14](https://github.com/croicu/quant-scratch/issues/14) (testing, 2026-08-02). `YahooFinanceIntraDay` (originally removed in issue #7 when `day-chart` switched to quant-data) restored as a third `--provider yahoo` choice — purely for comparison (checking whether a metric's absence is a real source gap vs. an ingest gap), not data quality: has the same documented pre-/after-market zero-volume gap `quant-data`'s ingest inherits from it (confirmed live: 315/315 pre-market bars zero-volume for SPY 7/31/2026, exact match to the original finding). Default stays `ibkr`; purely additive. User's stated long-term plan — default eventually flips to `quant-data` once the warehouse is fully populated — is a separate future change, not started. 103/103 tests pass.
- **quant-data: IBKR ingest provider** (cross-repo) — [croicu/quant-data#21](https://github.com/croicu/quant-data/issues/21) (brainstorm, 2026-08-02). Requested in quant-data (that's where the building work happens, per this file's Cross-Repo Coordination section) so the warehouse itself eventually has real extended-hours volume, closing the gap `day-chart`'s `--provider ibkr` default currently works around from this side. Builds on quant-data's own precursor schema work ([quant-data#18](https://github.com/croicu/quant-data/issues/18), closed) and its `tasks/ibkr-provider-reconciliation.md` brainstorm (run IBKR alongside Yahoo and reconcile, not swap). Issue body shares what was already learned here — `ib_async` over `ib_insync`, the `fetchFields=StartupFetch(0)` fix, port/request-shape details, untested-at-ingest-scale pacing caveat. No `quant-scratch` code involved; purely a cross-repo ask.
- **Databento intraday volume provider** — [tasks/databento_intraday_volume.md](tasks/databento_intraday_volume.md) / [issue #5](https://github.com/croicu/quant-scratch/issues/5) (postponed 2026-07-25 in favor of IBKR)
- **Local chunked data cache (FirstRateData)** — [tasks/local_data_cache_firstratedata.md](tasks/local_data_cache_firstratedata.md) / [issue #6](https://github.com/croicu/quant-scratch/issues/6) (postponed 2026-07-25 in favor of IBKR)

## Completed Tasks
- **Stock Quote CLI Tool** — [issue #1](https://github.com/croicu/quant-scratch/issues/1)
- **Yahoo provider componentization** — [issue #2](https://github.com/croicu/quant-scratch/issues/2)
- **Day trading chart CLI tool** — [issue #4](https://github.com/croicu/quant-scratch/issues/4)
- **Bootstrap `quant-data` warehouse repo** — schema, migrations, and docs seeded into a new
  standalone repo, [croicu/quant-data](https://github.com/croicu/quant-data) (cloned locally as
  `./quant-data/`, gitignored here — not part of this repo's history). Originated from this repo's
  `tasks/bootstrap_quant_data.md` and `tasks/database_layer.md` (both retired, content now lives in
  `quant-data`).
- **Switch `day-chart` to quant-data's `MarketData` read client** — [issue #7](https://github.com/croicu/quant-scratch/issues/7).
  New `shared/providers/quant_data.py`'s `QuantDataIntraDay` replaces the removed
  `YahooFinanceIntraDay` (quant-data's own ingest already covers that Yahoo fetch, so day-chart
  fetching it again directly was pure duplication). `DayBar` gained an `incomplete` field mirroring
  quant-data's `OHLCV.incomplete`. `stock_quote`'s `YahooFinance` (live quote lookup) is untouched —
  quant-data has no live-quote equivalent. Required first fixing a real cross-repo bug (both repos'
  top-level `defs`/`shared` package names collided once installed together) — see
  [quant-data#7](https://github.com/croicu/quant-data/issues/7), verified independently from this
  side before closing.

## Task Template
https://github.com/croicu/quant-scratch/blob/main/tasks/new_task.md