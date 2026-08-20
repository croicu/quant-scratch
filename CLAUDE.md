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
- **Massive as a second candidate provider in quant-data** (cross-repo) — [tasks/massive_candidate_provider.md](tasks/massive_candidate_provider.md) (brainstorm, 2026-08-16), cross-repo tracking issue [croicu/quant-data#44](https://github.com/croicu/quant-data/issues/44). Describes work for quant-data's own ingest/reconciliation pipeline (adding `massive` as a second `dim_provider` candidate role, alongside `ibkr`), not quant-scratch itself — the task file lives here only because this session had quant-scratch open. Intended as a Claude Chat conversation starter; move/copy into quant-data's own `tasks/` folder once picked up there. Open questions: multi-candidate reconciliation logic (today's arbitration has only ever handled whistleblower-vs-one-candidate), Massive's ingest/backfill cadence given its rate limits, backfill bound (2-year free-tier lookback), whether the canonical table should track which provider "won" each bar.

## Pending Tasks
- **Databento intraday volume provider** — [tasks/databento_intraday_volume.md](tasks/databento_intraday_volume.md) / [issue #5](https://github.com/croicu/quant-scratch/issues/5) (postponed 2026-07-25 in favor of IBKR)
- **Local chunked data cache (FirstRateData)** — [tasks/local_data_cache_firstratedata.md](tasks/local_data_cache_firstratedata.md) / [issue #6](https://github.com/croicu/quant-scratch/issues/6) (postponed 2026-07-25 in favor of IBKR)

## Completed Tasks
- **day-chart: consume quant-data's WAP/trade-count/bid-ask/midpoint fields** (cross-repo) — [issue #28](https://github.com/croicu/quant-scratch/issues/28) (closed), [PR #29](https://github.com/croicu/quant-scratch/pull/29), cross-repo [croicu/quant-data#60](https://github.com/croicu/quant-data/issues/60)/[#61](https://github.com/croicu/quant-data/issues/61) (both closed). quant-data#61 shipped 8 new nullable `OHLCV` fields: `wap`/`trade_count` (winner-gated — copied from whichever provider won that bar's OHLC reconciliation) and `avg_bid`/`avg_ask`/`midpoint_open/high/low/close` (IBKR-sourced, no arbitration needed since it's the sole quote source today). Synced the `quant-data` pin and force-reinstalled. `QuoteBar` (see the entry below) extended with the 4 midpoint fields; new `QuantDataIntraDay.fetch_quote_bars` reads the enrichment fields straight out of `fetch_bars`'s own cached `OHLCV` objects — no second `MarketData.fetch_bars` call, same "reuse what you already fetched" pattern as `MassiveIntraDay`'s cache. `day-chart`'s CSV export gains the columns for `--provider quant-data`; the chart gains the same third bid/ask panel `--provider ibkr` already has (quant-data can populate `avg_bid`/`avg_ask` too, unlike `massive`, which keeps the CSV-only treatment). Midpoint stays CSV-only for every provider. 225/225 tests pass; live-verified against the real warehouse — after catching and fixing a real environment drift along the way (the warehouse host had moved `CroicuWS1` → `CroicuWS2`, and the new box needed a Postgres password that wasn't previously required) — a full SPY session came back with `avg_bid`/`avg_ask`/midpoint populated on all 960 bars and `wap`/`trade_count` null on all 960, exactly matching #61's converged winner-gating design.
- **day-chart: IBKR/Massive WAP, trade count, and IBKR bid/ask** — [issue #26](https://github.com/croicu/quant-scratch/issues/26) (closed), [PR #27](https://github.com/croicu/quant-scratch/pull/27). Confirmed live this account has full IBKR access to `TRADES` (already used) plus `BID_ASK`/`BID`/`ASK`/`MIDPOINT`, and that Massive's free Basic tier has no bid/ask/NBBO product at any price point (`/v3/quotes` 403s "not entitled"). New shared `QuoteBar` type (renamed from `IBKRQuoteBar` once Massive became a second real consumer of the identical shape) carries `wap`/`trade_count`/`avg_bid`/`avg_ask`, deliberately kept off `DayBar` so it stays pure OHLCV across every provider. `IBKRIntraDay.fetch_quote_bars` issues a second `TRADES` call (re-reading WAP/count, already returned but previously discarded) plus a `BID_ASK` call, left-joined on `TRADES` timestamps (confirmed live the two calls can return different bar counts for the same window). `MassiveIntraDay.fetch_quote_bars` reads `vw`/`n` out of `fetch_bars`'s own cached response instead of a second HTTP call, since the free tier is hard rate-limited to 5 calls/minute. `day-chart`'s CSV export gains the four columns for `--provider ibkr`/`massive`; the chart gains a third bid/ask panel for `--provider ibkr` only (`massive`/`yahoo` layouts stay untouched, a deliberate choice — WAP/trade count aren't interesting to visualize). Also fixed two related `day-chart` issues found while testing: CSV timestamps switched from UTC ISO-8601 to plain `YYYY-MM-DD HH:MM:SS` in ET (Excel doesn't parse the former as a real datetime, imports it as text), and `--provider massive`'s no-flags-given default now resolves one day further back (the free tier has zero same-day data, confirmed live via a 403 — not just delayed, genuinely unavailable). 218/218 tests pass; live-verified against both the real IBKR Gateway (867-bar SPY session, confirmed 3-panel chart) and the real Massive API (confirmed exactly 1 HTTP call total for both `fetch_bars`+`fetch_quote_bars` combined, validating the no-duplicate-call design).
- **Excel/Postgres SSH tunnel automation (`open-quant-data`)** — [issue #19](https://github.com/croicu/quant-scratch/issues/19) (closed), [PR #20](https://github.com/croicu/quant-scratch/pull/20). New `src/open_quant_data/` CLI package (`open-quant-data SPREADSHEET`) starts the saved `quant-tunnel` PuTTY SSH tunnel (skipping relaunch if already up, `-N -batch` for automation), opens the given `.xlsx`, and blocks until Ctrl+C so Excel has something to refresh against — replacing the manual "start PuTTY, then open Excel" routine for querying `quant-data`'s Postgres warehouse via Power Query/ODBC. Takes the spreadsheet path as a CLI argument rather than a hardcoded constant; `.vscode/launch.json` exposes a dropdown (`pickString` input) for which known workbook to open. Workbooks split between `public/reports/` (checked into git, stable/never-refreshed examples like `sample.xlsx`) and new gitignored `local/reports/` (real, actively-refreshed dashboards) — Power Query embeds the fetched result set inside the `.xlsx` on every refresh, so a frequently-changing workbook would otherwise bloat git history on every commit (confirmed: a real refreshed dashboard came back at 769K for one ticker/one week of 1-minute bars). No secret ever touches a committed file: the real SSH endpoint (`CroicuWS1`) lives only in the locally-saved PuTTY session, referenced everywhere else only by name (`quant-tunnel`); the ODBC DSN (`quant-data-tunnel`) likewise stores connection details in Windows, not the workbook — Windows' `Add-OdbcDsn` cmdlet additionally refuses to store `UID`/`PWD` in a DSN's registry entry at all, so Excel prompts for credentials at connect time. 164/164 tests pass (14 new, offline — subprocess/socket/sleep/opener all injected); live-verified end-to-end against the real warehouse (tunnel → ODBC DSN → Power Query → an actual SPY candlestick chart in Excel). Caught and fixed a real test bug along the way: an early version of the happy-path CLI test didn't inject a fake file-opener and ended up actually launching Excel against a placeholder text file mid-test-run.
- **day-chart: rejected-whistleblower bar candlesticks** (cross-repo) — [issue #17](https://github.com/croicu/quant-scratch/issues/17) (closed), cross-repo announcement [issue #16](https://github.com/croicu/quant-scratch/issues/16) (closed). quant-data#32 replaced `OHLCV.incomplete: bool` with `OHLCV.data_quality: DataQuality` (`ACCEPTED`/`INCOMPLETE`/`REJECTED`) and added `MarketData.fetch_rejected_whistleblower_bars` — `DayBar.incomplete` now derives from `data_quality != ACCEPTED` (both `INCOMPLETE` and `REJECTED` collapse into `True`), and new `QuantDataIntraDay.fetch_rejected_bars` reuses `ProviderBar` (identical shape to `RejectedWhistleblowerBar`, no new type needed). `--provider quant-data` now always draws one orange candlestick per rejected bar alongside the existing red/blue conflict candlesticks. **Caught and fixed a real bug against live data**: rejected candles initially reused the conflict-candidate offset (`_CANDLE_OFFSET_DAYS`, 1.2min — safe for a conflict's still-pending whistleblower minute, which has no resolved black candle to collide with) but a rejected bar's minute *already* has one, so the >1-minute offset visually dragged it onto the *next* minute's candle. Fixed with a dedicated sub-minute `_REJECTED_OFFSET_DAYS`, covered by a regression test. Pin synced twice (`5d4af2e` → `b696961`) as quant-data's own outlier-detection check (croicu/quant-data#32) went from schema-only to live-calibrated against production data (188/23,938 whistleblower bars rejected, 0.79%). 152/152 tests pass; live-verified against real `REJECTED` data for SPY (4, all at the 16:00 ET boundary)/DOG (141)/RWM (16)/SH (1), including the positioning fix re-confirmed against real DOG data after the bugfix — not just mocks/fixtures.
- **IBKR provider suite** — [issue #11](https://github.com/croicu/quant-scratch/issues/11) (`IBKRIntraDay`, validated live against SPY 7/31/2026: 960 clean 1-min bars, real extended-hours volume — only 20/330 pre-market bars zero-volume vs. Yahoo's 315/315), [issue #12](https://github.com/croicu/quant-scratch/issues/12) (wired into `day-chart` as `--provider {ibkr,quant-data,yahoo}`, **defaulting to `ibkr`** — a deliberate behavior change; new optional `ibkr` `settings.json` section shared with `stock-quote`; range mode caps `--provider ibkr` at 30 days as an untested-but-documented margin under IBKR's pacing ceiling), [issue #13](https://github.com/croicu/quant-scratch/issues/13) (new `IBKRQuote` for `stock-quote`'s `--provider {yahoo,ibkr}`, **stays defaulted to `yahoo`** since IBKR's free tier is delayed here, not a strict improvement like `day-chart`'s case; live-first-then-delayed-fallback; added `StockQuote.provider`/`delayed` fields, each provider's `PROVIDER_NAME` aliased into both CLIs' `--provider` choices so they can't drift), [issue #14](https://github.com/croicu/quant-scratch/issues/14) (`YahooFinanceIntraDay` restored as a third `day-chart` choice, purely for source-vs-warehouse comparison, not data quality — default stays `ibkr`). `IBKRIntraDay`/`IBKRQuote.connect()` pass `fetchFields=StartupFetch(0)`, silencing a Read-Only-API-mode Gateway popup and cutting connect time from ~10s to ~10ms. Caught a real `ib_async` quirk along the way: `Ticker.__post_init__` resets `last`/`volume`/etc. to NaN unless `created=True` is passed. 103/103 tests pass; every piece verified live against the real Gateway, not just fakes.
- **quant-data: IBKR ingest provider synced + verified** (cross-repo) — [croicu/quant-data#21](https://github.com/croicu/quant-data/issues/21) (closed). Requested in quant-data per this file's Cross-Repo Coordination convention; quant-data built a fetch-only `IBKRIntraDay` + wired both providers into `quant-ingest`/staging + `quant-reconcile` (their own #22/#24/#25). Synced `pyproject.toml`'s `quant-data` pin (`dbec9fa7` → `e86c902a`), confirmed no API-surface changes (identical `create_postgres_provider`/`MarketData` signatures, 103/103 tests unmodified), and verified live against real reconciled data: `day-chart --provider quant-data` for SPY 7/31 now matches `--provider ibkr`'s data quality (20/315 zero-volume pre-market bars, `incomplete=False` throughout) instead of the old 315/315 Yahoo-only gap. **User's stated long-term plan** (`day-chart`'s default eventually flipping from `ibkr` to `quant-data`) is still not started — this was one ticker/date verified, not a full coverage audit.
- **day-chart: pending-resolution (disputed) bar candlesticks** — [issue #15](https://github.com/croicu/quant-scratch/issues/15) (closed). `--provider quant-data` now always fetches quant-reconcile's "stuck" queue (`QuantDataIntraDay.fetch_conflicts`, new `defs.protocols.ProviderBar`/`BarConflict` types — deliberately not a `DayBar` field, since only quant-data has a reconciliation concept) and draws one red candlestick (whistleblower's own OHLC) plus one blue candlestick per candidate (each candidate's own OHLC, plurality-safe) on the chart — resolved via `PendingResolutionBar.role` (quant-data#27) rather than quant-scratch guessing an envelope. Chart-only, no CSV export. Silent no-op for `ibkr`/`yahoo`. 123/123 tests pass; live-verified against 3 real disputed SPY bars (16:00 ET boundary, 2026-07-28/29/30) end-to-end, including the actual candlestick render (correct colors/positions). Required re-syncing the `quant-data` pin twice more mid-task (`e86c902a` → `cd22e858` → `81e1d4e2`) as the API's `role` shape settled.
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