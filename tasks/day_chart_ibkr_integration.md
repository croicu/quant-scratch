# day-chart-ibkr-integration

## Status: Testing

## Problem statement

`day-chart` currently only ever constructs `shared.providers.quant_data.QuantDataIntraDay`
(`day_chart/cli.py`'s `main()`, hardcoded) — the `IntraDayProvider` it depends on reads from the
quant-data warehouse, which itself still ingests from Yahoo Finance and inherits Yahoo's
documented pre-/after-market zero-volume gap (`DayBar.incomplete=True` for almost every extended-
hours bar; see `quant_scratch_intraday_data_status` history and
`docs/ARCHITECTURE.md`'s `defs.protocols` note).

`shared.providers.ibkr.IBKRIntraDay` (built and validated in
[tasks/ibkr_fetch_historical_spy.md](ibkr_fetch_historical_spy.md) /
[issue #11](https://github.com/croicu/quant-scratch/issues/11)) implements the same
`IntraDayProvider` contract and, confirmed against live SPY data, returns real trade volume
through pre-/after-market — exactly the gap `day-chart` exists to study at session transitions.
It's currently only reachable standalone via `ibkr_fetch.validate`, not through `day-chart` itself.

This task is about actually wiring it in, without silently changing what every existing
`day-chart` invocation does today (quant-data must stay the default).

## Design decisions

- Carries forward the already-settled design from
  [tasks/ibkr_tws_extended_hours.md](ibkr_tws_extended_hours.md), realized in `IBKRIntraDay` as
  built: connect-per-call lifecycle, `shared.sessions.infer_session` reuse, no credential-handling
  concern (host/port/client_id aren't secrets).
- `IBKRIntraDay` always sets `DayBar.incomplete=False` (no analog to quant-data's flag) — that's
  existing, already-shipped behavior from the provider itself, not something this task changes.
- **Provider selection**: `day_chart.cli` gets a `--provider {ibkr,quant-data}` flag. **Default is
  `ibkr`**, not `quant-data` — user call: IBKR has strictly more data (real extended-hours volume)
  than the Yahoo-sourced quant-data path, so once this integration itself proves out cleanly, IBKR
  should be what every plain `day-chart TICKER` invocation uses. `quant-data` stays fully available
  via `--provider quant-data` as a fallback (e.g. if the local Gateway isn't running, or for
  historical dates further back than IBKR's lookback window). This is a real behavior change for
  existing users of the command — accepted deliberately, not an oversight.
- **IBKR connection settings**: adds an `ibkr` section to `settings.json`/`settings.local.json`
  (`Settings.ibkr: IBKRSettings | None`), mirroring the `postgres` section's shape. Deliberately
  **not** identical validation behavior, though: `postgres` requires all keys because it has no
  sensible built-in default (a real host has to be named somewhere); `ibkr`'s fields
  (`host`/`port`/`client_id`) all keep `IBKRIntraDay`'s existing constructor defaults
  (`127.0.0.1`/`4002`/`1`) when the section — or individual keys within it — are absent, since
  those defaults are already genuinely usable for the one local paper-Gateway setup this repo
  targets. The section exists to let a future different setup (a different port, a live-vs-paper
  Gateway, a second client ID for running two tools at once) override those defaults, not because
  today's defaults need replacing.
- **Range mode + IBKR pacing limits — resolved empirically**: probed the live paper Gateway
  directly (throwaway script, not part of the repo) with 7 back-to-back `reqHistoricalData` calls
  for SPY (same contract, ~2.6s total, including two weekend end-dates that IBKR correctly snapped
  back to the prior session) — zero pacing-violation errors, all 7 returned clean 960-bar days.
  This covers `day-chart`'s realistic range-mode workload (a handful of days to a couple weeks)
  with no throttling needed. IBKR's documented ceiling of 60 requests/10 minutes is still real and
  untested at that scale, though (a multi-month range could plausibly hit it) — rather than adding
  artificial per-call delay (unneeded given the burst result above), `day_chart.cli` adds an
  upfront day-count cap on `--start-date`/`--end-date` ranges specifically when `--provider ibkr`
  is selected, rejecting an oversized range with a clear `AppError` before making any requests.
  Chose **30 trading days** as the cap — comfortably under the 60-request ceiling even counting
  `qualifyContracts` and connection-setup calls alongside one `reqHistoricalData` per day, with
  headroom for the fact this isn't a *proven* threshold, just a documented one never directly
  tested at scale. `quant-data`-backed ranges are unaffected (no such cap — no external pacing
  constraint applies to Postgres reads).
- **Test coverage shape**: since `IBKRIntraDay.__init__` doesn't connect (only `fetch_bars` does —
  connect-per-call, see the provider's own design), constructing one in a test is already offline-
  safe with no mocking needed. `day_chart.cli` gets a small pure `_build_provider(provider_name,
  settings) -> IntraDayProvider` helper, factored out of `main()`, so a unit test can assert the
  right *class* gets constructed (and with what settings-derived arguments) without ever calling
  `fetch_bars` or touching a real connection.

## Implementation plan

1. `shared/settings.py`: add `IBKRSettings` (`host: str = "127.0.0.1"`, `port: int = 4002,
   client_id: int = 1`) and `Settings.ibkr: IBKRSettings | None = None`, parsed from an optional
   `ibkr` object in `settings.json`/`settings.local.json` — unlike `postgres`, no required-keys
   validation; any subset of keys may be given, each falling back to `IBKRSettings`'s own default
   when absent.
2. `day_chart/cli.py`:
   - New `--provider {ibkr,quant-data}` argument (default `ibkr`) on `CliArguments`/`parse_args`.
   - New `_build_provider(provider_name, settings) -> IntraDayProvider` helper: `ibkr` constructs
     `IBKRIntraDay(host=..., port=..., client_id=...)` from `settings.ibkr` (or all defaults if
     `settings.ibkr is None`); `quant-data` constructs `QuantDataIntraDay(...)` from
     `settings.postgres` as today (raising `AppError` if that section is missing — unchanged).
     `main()` calls this only when no `provider` was injected (DI path for tests unchanged).
   - Range-mode day-count cap: when `is_range_mode` and the resolved provider is `ibkr`, raise
     `AppError` up front if `len(session_dates) > 30`, before any `fetch_bars` calls.
3. Tests:
   - `tests/unit/test_settings.py`: `ibkr` section parsing — absent (all defaults), partial
     override (one key given, others default), fully specified.
   - `tests/unit/test_day_chart_cli.py`: `_build_provider` returns an `IBKRIntraDay`/
     `QuantDataIntraDay` instance as appropriate; default (`--provider` omitted) is `ibkr`; the
     30-day range cap raises `AppError` for `ibkr` and is a no-op for `quant-data` at the same
     range size.
4. Docs: `docs/PROTOCOL.md` (`--provider` flag, new `ibkr` settings section), `docs/ARCHITECTURE.md`
   (`day_chart.cli`'s provider-selection logic, updated data-flow description), `CLAUDE.md` (Pending
   Tasks entry).

## Test results

Implemented as planned (all four steps). 86/86 tests pass (`ruff format`/`ruff check` clean).

**Live verification** against the running paper Gateway (port 4002):

- `day-chart SPY --date 2026-07-31` with **no `--provider` flag** (confirming the new `ibkr`
  default actually takes effect via the real `settings.json`, which has no `ibkr` section — all
  connection defaults) → real Gateway connection, `exit_code=0`, wrote a 960-bar CSV (961 lines
  incl. header) matching the earlier standalone validation in
  [tasks/ibkr_fetch_historical_spy.md](ibkr_fetch_historical_spy.md) exactly. Popup itself wasn't
  exercised interactively (headless shell) — verified via an injected no-op `show_chart` instead;
  `day_chart/chart.py` itself is unchanged by this task.
- `day-chart SPY --start-date 2026-06-01 --end-date 2026-07-31` (61 days, `--provider` omitted so
  still `ibkr`) → rejected up front with the 30-day cap's `AppError`, `exit_code=1`, before any
  `fetch_bars` call — confirms the cap fires on the real CLI path, not just in the unit test.

**One test-authoring bug caught and fixed along the way**: an early version of the
"`quant-data`-provider is unaffected by the cap" test forgot to inject a no-op `show_chart`, so it
fell through to the real interactive matplotlib popup and blocked the test run for ~3.5 minutes
waiting for a window-close event that never came in a headless run. Fixed by adding
`show_chart=lambda ticker, days: None`, matching every other range-mode CLI test's pattern — full
suite dropped from 218s back to ~4s. Worth remembering for any future `day_chart.cli.main()` test
that doesn't inject `provider` and hits the real fetch path: always inject `show_chart` too, or the
test can hang indefinitely rather than fail cleanly.

**Not covered by this task**: a real range-mode run against IBKR beyond the 7-request live probe —
the 30-day cap is a documented-but-unmeasured safety margin, not empirically validated at the scale
that would actually approach it.
