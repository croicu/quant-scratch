# ARCHITECTURE.md

Modules, data flow, and contracts for `quant-scratch`.

## Modules

<!-- One entry per module under src/<package>/: what it owns, what it depends on. -->

### `defs` — repo-wide specification, no implementation

Pure interfaces and data contracts, owned by no single implementation package. `shared` provides
one (default) implementation of what's declared here; a CLI tool could in principle bring its own
alternative implementation instead, depending only on `defs`. Also the intended home for other
future cross-cutting non-implementation declarations (constants, etc.) — hence the general name
rather than something provider-specific.

- `protocols.py` — pure data: `StockQuote` (`ticker`, `price`, `timestamp`, `volume`,
  `provider: str`, `delayed: bool` defaulting `False`); `DayBar` (`timestamp: datetime` UTC-aware,
  `open`, `high`, `low`, `close`, `volume`, `session: str`, `incomplete: bool` defaulting `False`).
  `DayBar.timestamp` is a `datetime` rather than a `str` like `StockQuote.timestamp` — an
  intentional divergence, since bar data needs real datetime arithmetic (session inference,
  sorting, ET conversion for the chart x-axis) that a string would just force back into a parsed
  datetime anyway. `incomplete` mirrors [quant-data](https://github.com/croicu/quant-data)'s
  `OHLCV.incomplete` field one-for-one — set when the warehouse's provider couldn't supply full
  data for that bar (in practice, almost every pre/after-market bar, since quant-data's own ingest
  still pulls from Yahoo Finance and inherits its zero-volume gap outside regular hours).
  `StockQuote.provider` (required, no default — every quote must know its source) holds whichever
  provider fetched it, e.g. `"yahoo"`/`"ibkr"`; each provider stamps its own
  `shared.providers.<module>.PROVIDER_NAME` constant onto it rather than the CLI passing a name in,
  so the value can never drift from what actually produced the quote. `StockQuote.delayed` is the
  live-quote analogue of `DayBar.incomplete`: `True` when a provider could only supply delayed (not
  real-time) data. `YahooFinance`/`MockYahooFinance` never set it (stays the dataclass default
  `False` — Yahoo's `fast_info` has no comparable live/delayed distinction surfaced today).
  `ProviderBar` (`provider: str`, `bar: DayBar`) and `BarConflict` (`field_group: str`,
  `whistleblower: ProviderBar`, `candidates: list[ProviderBar]`) represent quant-reconcile's
  "stuck" queue — bars where providers disagree beyond tolerance
  ([croicu/quant-scratch#15](https://github.com/croicu/quant-scratch/issues/15)). Deliberately
  *not* a `DayBar` field: a conflict is inherently multi-valued (several providers' competing
  values for one bar) and only exists for `quant-data` — `IBKRIntraDay`/`YahooFinanceIntraDay` have
  no equivalent concept, so it isn't part of `IntraDayProvider`'s shared interface either.
  `candidates` is a list (not a single field) because `dim_provider` isn't hardcoded to exactly one
  candidate, even though today's real data is always exactly one.
- `contracts.py` — behavioral interfaces: `YahooFinanceProvider(Protocol)` — `fetch_quote(ticker) -> StockQuote`;
  `IntraDayProvider(Protocol)` — `fetch_bars(ticker, target_date) -> list[DayBar]`. `BarConflict`
  fetching (`QuantDataIntraDay.fetch_conflicts`) is *not* part of this protocol — see its own note
  below for why.

### `shared` — shared framework + default implementations

Every experiment package depends on this one for bootstrap; it owns no experiment-specific logic
and has no CLI/console script of its own.

- `diagnostics.py` — `Logger`, log sinks (`ConsoleLogSink`), telemetry levels/records. Defines
  `CATEGORY_GENERAL` (the default), `CATEGORY_PERF` ("perf"), and `CATEGORY_PERF_UI` ("perf_ui") —
  the latter two centralized here (rather than as a per-file constant like `quant_data.py`'s
  `CATEGORY_INTRADAY_FETCH` or `day_chart/cli.py`'s `CATEGORY_DATE_RANGE`) specifically so timing
  markers scattered across multiple packages can be toggled together with one `settings.json`
  `logCategories` entry (plus a `logLevel` of `"info"` or lower, since `Logger.info` is filtered by
  level too) rather than one category per module. `CATEGORY_PERF_UI` is split out from
  `CATEGORY_PERF` specifically because it's much higher-volume (one line per ~100ms event-loop poll
  while a popup is open) and only useful when actively diagnosing UI responsiveness (resize
  lag, redraw cost) — a flat sibling category for now, not a true hierarchical `perf/ui`
  subcategory, since `logCategories` has no hierarchy today. `Logger.perf(description,
  elapsed_seconds, category=CATEGORY_PERF)` is the call site for these — a thin wrapper over
  `Logger.info(f"duration: {elapsed_seconds:.3f}s - {description}", category)`, duration-first so
  markers are scannable without reading past the message (`day_chart.chart`'s `perf_counter()`-timed
  markers use it for backend-switch/render/popup-wait duration under `perf`, plus per-poll timing,
  actual `canvas.draw()` duration, and `resize_event` markers under `perf_ui`;
  `shared.providers.quant_data` for connection/query duration under `perf`; `day_chart.cli` for the
  cli-entry-to-settings-loaded/fetch-phase/CSV-write markers under `perf`). `day_chart.cli.main()`
  installs the
  `ConsoleLogSink` immediately after `Settings.load()` succeeds and before constructing
  `QuantDataIntraDay` specifically so that provider's own connection-time marker isn't silently
  swallowed by the default no-op sink that's active before `Logger.set_logger()` runs (which is
  exactly what happened before this ordering fix — the SSH tunnel/DB connection cost was being
  measured but never printed). `Logger` (the class itself, passed uninstantiated — all its public
  methods are `@staticmethod`s) is also injected into quant-data as `logger=Logger` wherever it
  accepts one (`create_postgres_provider`, `MarketData`) — it structurally satisfies quant-data's
  public `quant_data.protocols.LoggingSink` `Protocol` with no adapter code needed, since that
  Protocol was deliberately shaped to mirror this `Logger`'s own method surface
  ([quant-data#20](https://github.com/croicu/quant-data/issues/20)). This is what makes
  `shared.providers.quant_data`'s own perf markers and quant-data's *internal* ones (tunnel
  setup, `psycopg.connect()`, each query) show up interleaved in the same stream — see that
  module's own note below for what this replaced.
- `settings.py` — `Settings.load(path, local_path)` / `Settings.current()`, reads `settings.json` +
  `settings.local.json` by default; `path` is a DI'd parameter (default `./settings.json`) so
  callers/tests can point at a fixture instead. `local_path` defaults to a `settings.local.json`
  *sibling of `path`*, not a fixed repo-root path — resolved that way specifically so a caller/test
  passing a custom `path` (e.g. a fixture settings file) can't accidentally pick up whatever real
  `settings.local.json` happens to sit at the real cwd's repo root; passing `local_path` explicitly
  still overrides this. Also `PostgresSettings` (`host`, `port`, `user`, `password`, `dbname`, plus
  optional `ssh_user`/`ssh_key_path` — both-or-neither, `TaskError` if only one is set) and a
  `Settings.postgres` field, parsed from a `postgres` object under `settings.json`/
  `settings.local.json`'s `settings` key (JSON keys `sshUser`/`sshKeyPath`) — mirrors quant-data's
  own `PostgresSettings` shape exactly, including the optional SSH fields
  ([croicu/quant-data#17](https://github.com/croicu/quant-data/issues/17)). `host`/`port`/`user`/
  `password`/`dbname` aren't secret for a client connecting through an already-authenticated local
  SSH tunnel (`host`/`port` are just the local tunnel endpoint, e.g. `localhost`/`5433`; the
  `quant_reader` role has no password), so that much can live in the committed `settings.json`. The
  real box hostname and `ssh_user`/`ssh_key_path` needed for quant-data's new auto-tunnel path are
  a different matter — those go in `settings.local.json` (gitignored) only, never a committed file
  — see quant-data's `docs/DATABASE.md`'s `<ubuntu_host>`/`<ssh_user>` placeholders. Also
  `WindowSettings` (`x`, `y`) and a `Settings.window` field, parsed the same way from an optional
  `window` object — unlike `postgres`, nothing reads this from the committed `settings.json`;
  `day_chart.chart.show_chart` treats it as a `settings.local.json`-only, auto-managed value (see
  its own note below), not something a user hand-edits. `Settings.save_window_position(x, y,
  local_path=...)` is the write side — reads whatever's currently in `local_path` (if anything),
  replaces just the `window` key, and writes the whole file back, so it never clobbers unrelated
  local overrides living in the same file (e.g. `postgres.sshKeyPath`).
  Also `IBKRSettings` (`host`, `port`, `client_id`, all with defaults) and a `Settings.ibkr` field,
  parsed from an optional `ibkr` object (JSON key `clientId`) — unlike `postgres`, no required-keys
  validation: every field already has a default matching `IBKRIntraDay`'s own constructor defaults
  for this repo's one local paper-Gateway setup, so the section (or any key within it) may be
  omitted, each falling back independently rather than requiring all-or-nothing.
  Also `DatabentoSettings` (`api_key` required, `dataset` defaulting to `"DBEQ.BASIC"`) and a
  `Settings.databento` field, parsed from an optional `databento` object (JSON key `apiKey`) — like
  `postgres` and unlike `ibkr`, `api_key` has no usable default (a paid-account credential, not a
  local service), so an empty `databento` object still raises `TaskError`. Meant to live in
  `settings.local.json` only (gitignored), never the committed `settings.json`, since it's a secret.
- `errors.py` — `AppError`, `TaskError`, `telemetry_session()`
- `sessions.py` — `infer_session(timestamp_utc) -> str`, classifying a UTC timestamp into
  `"pre-market"` (4:00–9:30 ET), `"regular"` (9:30–16:00 ET), or `"after-market"` (16:00–20:00 ET);
  raises `AppError` for a timestamp outside that range. Lives directly in `shared` (not in
  `day_chart`, despite being introduced for that experiment, and not in `shared/providers/` since
  it isn't itself a provider) because it's needed to construct `DayBar` instances inside
  `shared.providers.quant_data.QuantDataIntraDay` and inside the test mock — putting it in
  `day_chart` would have made `shared` depend on an experiment package, inverting the intended
  dependency direction.
- `providers/` — one module per external data source, each providing a default implementation of
  a `defs.contracts` interface. Separated from the rest of `shared` so multiple providers can sit
  side by side without crowding a single flat file list.
  - `yahoo_finance.py` — `YahooFinance`, the default implementation of
    `defs.contracts.YahooFinanceProvider`; wraps `yfinance`, raises `AppError` on an invalid
    ticker or network failure. `stock_quote`'s default provider (a live single-quote lookup).
    Defines `PROVIDER_NAME = "yahoo"`, stamped onto every `StockQuote.provider` it returns; also
    re-exported as `stock_quote.cli.PROVIDER_YAHOO`/`day_chart.cli.PROVIDER_YAHOO` (aliases, not
    duplicate literals) for each CLI's `--provider` flag choices.

    `YahooFinanceIntraDay`, alongside it in the same file, implements
    `defs.contracts.IntraDayProvider.fetch_bars(ticker, target_date) -> list[DayBar]` by wrapping
    `yfinance.Ticker(...).history(interval="1m", prepost=True)`. Originally `day-chart`'s only
    provider; removed entirely when quant-data's warehouse took over
    ([issue #7](https://github.com/croicu/quant-scratch/issues/7) — re-fetching Yahoo directly was
    pure duplication once quant-data's own ingest already pulled from Yahoo and stored it),
    restored as a third selectable `--provider yahoo`
    ([tasks/day_chart_yahoo_provider.md](../tasks/day_chart_yahoo_provider.md) /
    [issue #14](https://github.com/croicu/quant-scratch/issues/14)) — not for its data quality (it
    has the same pre-/after-market zero-volume gap `quant-data`'s ingest inherits from it: confirmed
    315/315 pre-market bars zero-volume for a live SPY pull, identical to the historical
    Yahoo-vs-IBKR comparison that motivated `IBKRIntraDay` in the first place), but so a raw-source
    fetch can be compared directly against what's actually in the warehouse. No settings needed
    (`yfinance` takes no connection config). Carries the same known limitation forward unchanged,
    not a regression — this provider exists for comparison, not everyday use.
  - `quant_data.py` — `QuantDataIntraDay`, the default implementation of
    `defs.contracts.IntraDayProvider`. Thin wrapper around
    [quant-data](https://github.com/croicu/quant-data)'s public `MarketData` read client — imports
    only from the `quant_data` top level (`from quant_data import MarketData,
    create_postgres_provider`), per quant-data's own stable-surface contract
    ([quant-data#10](https://github.com/croicu/quant-data/issues/10)/
    [quant-scratch#8](https://github.com/croicu/quant-scratch/issues/8)): builds a provider via
    `create_postgres_provider(host=..., port=..., dbname=..., user=..., password=..., ssh_user=...,
    ssh_key_path=...)` and passes it to `MarketData(provider)` — `MarketData` itself no longer
    takes connection details directly, so it stays agnostic of Postgres specifically (a future
    non-Postgres backend wouldn't need another breaking change here). `ssh_user`/`ssh_key_path`
    default to `None` (today's direct-connect behavior, unchanged); when both are set, quant-data
    opens and manages its own SSH tunnel instead of assuming one's already running externally
    ([croicu/quant-data#17](https://github.com/croicu/quant-data/issues/17)/
    [croicu/quant-scratch#10](https://github.com/croicu/quant-scratch/issues/10)). Also passes
    `logger=Logger` to both calls ([quant-data#20](https://github.com/croicu/quant-data/issues/20))
    so quant-data's own internal timing/connection log lines land in this repo's own `Logger`
    stream. Doesn't wrap `fetch_bars` in its own perf marker — quant-data's `PostgresDatabase`
    already emits one for that identical call via the injected logger, so a second one here would
    just duplicate it. (The connection setup itself briefly regressed to a ~130s stall after
    adopting the auto-tunnel, traced to `psycopg.connect()` being handed the ambiguous hostname
    `"localhost"` instead of a concrete `"127.0.0.1"` — fixed upstream in
    [quant-data#19](https://github.com/croicu/quant-data/issues/19), confirmed back down to ~1.4s.)
    Calls `fetch_bars(ticker, target_date, target_date)` (a
    single-day range) and converts each returned `quant_data.OHLCV` into this repo's own `DayBar`,
    computing `session` via `sessions.infer_session` and carrying `incomplete` straight through.
    Normalizes `OHLCV.timestamp` to UTC-aware before use — it's been observed coming back naive
    despite being documented UTC-aware, which `.astimezone()` (used by both `infer_session` and
    the chart's ET conversion) would otherwise silently misinterpret using the local machine's
    system timezone ([quant-data#8](https://github.com/croicu/quant-data/issues/8), still open —
    keep this normalization until it's fixed upstream). A bar `infer_session` can't classify
    (outside the 4:00-20:00 ET window) fails the whole fetch with an `AppError` — quant-data#9 (a
    write-side bug silently shifting stored timestamps by the ingest session's local timezone) was
    the actual cause of bars showing up outside that window; now that it's fixed and historical
    data backfilled, an out-of-window bar again indicates a real problem worth surfacing loudly,
    not something to skip. Connects using `Settings.postgres`
    (host/port/user/password/dbname/ssh_user/ssh_key_path); raises `AppError` if that section is
    missing, if the connection fails, or if no bars are
    returned at all. Replaced
    `shared.providers.yahoo_finance.YahooFinanceIntraDay` (removed — see
    [croicu/quant-scratch#7](https://github.com/croicu/quant-scratch/issues/7)): quant-data's own
    ingest already pulls from Yahoo Finance and stores the result, so `day-chart` fetching Yahoo
    directly was pure duplication once the warehouse existed. Constructor accepts an injected
    `client` for tests, matching this repo's DI-over-monkeypatching convention for testing
    dependencies on third-party/cross-repo code.

    Also `fetch_conflicts(ticker, start_date, end_date) -> list[BarConflict]` — a second public
    method, *not* part of `IntraDayProvider` (only `quant-data` has a reconciliation concept to
    report a conflict from). Wraps `MarketData.fetch_pending_resolution_bars`, which returns one
    flat row per `(bar, field_group, provider)` — there's no grouping on the wire, so this groups
    rows back into one `BarConflict` per disputed `(timestamp, field_group)`, partitions each
    group by `PendingResolutionBar.role` (`quant_data.ProviderRole.WHISTLEBLOWER`/`.CANDIDATE`),
    and raises `AppError` if a group doesn't have exactly one whistleblower or has zero candidates
    — an unexpected shape worth surfacing loudly, not silently guessing at (mirrors the existing
    `fetch_bars` philosophy for out-of-window bars). An **empty** result is *not* an error, unlike
    `fetch_bars` — no disputes is the normal case. `day_chart.cli` calls this once for a chart's
    whole resolved date range (not per-day), only when `--provider quant-data` is selected — a
    silent no-op for `ibkr`/`yahoo`, which have nothing to dispute against. The `OHLCV` → `DayBar`
    conversion (`_ohlcv_to_daybar`) is factored out and shared with `fetch_bars`.
  - `ibkr.py` -- `IBKRIntraDay`, another `defs.contracts.IntraDayProvider` implementation, wrapping
    [`ib_async`](https://github.com/ib-api-reloaded/ib_async) (the actively-maintained community
    fork of the archived `ib_insync`) against a local IB Gateway/TWS instance. Built for
    `tasks/ibkr_fetch_historical_spy.md` to validate the IBKR historical-bars pipeline as a
    from-source alternative to `QuantDataIntraDay` -- quant-data's own ingest still pulls from
    Yahoo Finance and inherits its extended-hours zero-volume gap (see `quant_data.py`'s note
    above); IBKR's `reqHistoricalData` returns real trade volume for pre-/after-market bars too
    (confirmed against live SPY data -- see the task file's Test results). Connects and
    disconnects a fresh `IB()` per `fetch_bars` call rather than holding a connection open
    (`client_factory: Callable[[], IB]`, defaulting to `IB` itself, overridable for tests) -- no
    performance case for a shared connection when each CLI invocation calls `fetch_bars` once.
    Requests `barSizeSetting="1 min"`, `whatToShow="TRADES"`, `useRTH=False`, `durationStr="1 D"`
    ending at that session date's 20:00 ET after-market close, `formatDate=2` so returned bar
    timestamps come back timezone-aware UTC directly (no local-timezone ambiguity to normalize,
    unlike `QuantDataIntraDay`'s naive-timestamp handling). Reuses `shared.sessions.infer_session`
    for `DayBar.session`, same as `QuantDataIntraDay`; always sets `incomplete=False` since IBKR's
    `BarData` carries no such flag (unlike quant-data's `OHLCV.incomplete`) and a zero-volume
    1-minute bar here is presumed to mean "genuinely no trades that minute," not missing data.
    Defaults to `host="127.0.0.1"`, `port=4002` (IB Gateway's paper-trading API port -- this repo's
    Gateway instance runs paper, not live), `client_id=1`, all overridable via `Settings.ibkr`.
    Wired into `day_chart.cli` as the **default** provider (see below) -- IBKR has strictly more
    data than the Yahoo-sourced quant-data path, per
    [tasks/day_chart_ibkr_integration.md](../tasks/day_chart_ibkr_integration.md) /
    [issue #12](https://github.com/croicu/quant-scratch/issues/12). `connect()` passes
    `fetchFields=StartupFetch(0)` (from `ib_async.ib`) -- the library's default startup fetch
    (positions/open+completed orders/account updates) needs write-level API access, which a
    Read-Only API Gateway (the sensible setting here: no trading involved) rejects, surfacing as
    noisy stdout warnings and a "needs API write access" Gateway popup on every connection. This
    provider never touches any of that, only `reqHistoricalData`, so there's nothing to fetch at
    startup -- `StartupFetch(0)` (an empty flag set) skips it entirely, incidentally also cutting
    `connect()` from ~10s (spent on those requests timing out) down to under 10ms.

    `IBKRQuote`, alongside it in the same file (same external source, same connection lifecycle),
    implements `defs.contracts.YahooFinanceProvider.fetch_quote(ticker) -> StockQuote`. Built for
    `stock-quote`'s `--provider ibkr`
    ([tasks/stock_quote_ibkr_integration.md](../tasks/stock_quote_ibkr_integration.md) /
    [issue #13](https://github.com/croicu/quant-scratch/issues/13)). Calls `ib.reqTickers(contract)`
    for a live quote first; if that comes back with `last` unset (`NaN` -- confirmed empirically:
    this account has no real-time market-data subscription, error 10089, and IBKR does *not*
    auto-fall-back), calls `ib.reqMarketDataType(3)` and retries once, this time getting delayed
    data (~15-20 minutes, free, no subscription needed). `StockQuote.delayed` is set from the
    *actual* `ticker.marketDataType` returned (`!= 1`), not from which branch ran -- an account with
    real live entitlement would get `delayed=False` even though the code path looks identical.
    Same `client_factory`/connect-per-call/`fetchFields=StartupFetch(0)` shape as `IBKRIntraDay`.
    Unlike `day-chart`'s flip to `ibkr` as default, `stock-quote` keeps `yahoo` as the default --
    IBKR's free tier here is strictly *more delayed* than Yahoo's near-real-time quote, the
    opposite tradeoff from `day-chart`'s extended-hours-volume case, so no default change was
    warranted. Defines `PROVIDER_NAME = "ibkr"`, stamped onto every `StockQuote.provider` it
    returns -- same re-export pattern as `yahoo_finance.py`'s (`stock_quote.cli.PROVIDER_IBKR`).
  - `databento.py` -- `DatabentoIntraDay`, another `defs.contracts.IntraDayProvider` implementation,
    wrapping [`databento`](https://github.com/databento/databento-python)'s `Historical` client
    against Databento's consolidated US equities feed. A fourth `day-chart` `--provider` choice,
    alongside (not replacing) `ibkr` — added after IBKR already closed the extended-hours-volume
    gap that originally motivated evaluating Databento
    ([tasks/databento_intraday_volume.md](../tasks/databento_intraday_volume.md) /
    [issue #5](https://github.com/croicu/quant-scratch/issues/5), postponed 2026-07-25 over
    usage-based billing risk, revisited later as an additional source rather than a gap-filler).
    Requests `schema=Schema.OHLCV_1M` (1-minute bars) for the 4:00-20:00 ET session window (same
    boundary `IBKRIntraDay` uses), `dataset` defaulting to `"DBEQ.BASIC"` (Databento's
    multi-venue-consolidated feed, picked so a single exchange's tape doesn't silently
    under-report volume for a security trading across venues) but overridable per
    `Settings.databento.dataset`. `client_factory: Callable[[str], db.Historical]`, defaulting to
    `db.Historical` itself, overridable for tests — same connect-per-call-via-factory shape as
    `IBKRIntraDay`, though `Historical` itself is a thin HTTP client wrapper with no persistent
    connection to open/close. Converts the response via `DBNStore.to_df(price_type="float",
    tz="UTC")` and iterates rows (`for row_timestamp, row in frame.iterrows()`), same
    DataFrame-iteration shape as `yahoo_finance.py`'s `YahooFinanceIntraDay`. Reuses
    `shared.sessions.infer_session` for `DayBar.session`; no `incomplete` flag support (Databento's
    OHLCV records carry none). Requires a paid API key (`Settings.databento.api_key`, no usable
    default) — live-verified against a real account: `DBEQ.BASIC` does return non-zero
    extended-hours volume for SPY (0/21 zero-volume pre-market bars, 0/74 after-market, vs.
    Yahoo's 315/315), but coverage is noticeably sparser than `IBKRIntraDay`'s -- `OHLCV_1M`
    simply omits any minute with no trade rather than emitting a zero-volume bar, and `DBEQ.BASIC`
    itself only aggregates a subset of venues, not a full consolidated SIP tape (no `EQUS.SIP`/
    `EQUS.ALL`-equivalent is actually published/live on the account tested against, despite
    existing as enum values in the `databento` SDK — `DBEQ.BASIC` is the best available
    consolidated option).

    Also live-verified: Databento's `hist.databento.com` gateway returns intermittent 504s on an
    otherwise-unremarkable request (same ticker/date/dataset succeeding on one call, failing on
    the next, no reproducible pattern) — `fetch_bars` retries up to `max_attempts` (default 3,
    constructor-overridable) with a fixed `retry_delay_seconds` (default 2.0) between attempts,
    but only for `db.BentoServerError` (500-series -- Databento's own infrastructure); a
    `db.BentoClientError` (400-series -- bad API key, invalid symbol, anything that will never
    succeed on retry) falls through to the same generic `AppError`-wrapping path as any other
    exception, immediately. `sleep_fn: Callable[[float], None]`, defaulting to `time.sleep`, is
    injectable the same way `client_factory` is, so the retry unit tests never actually sleep.

### `ibkr_fetch` -- manual pipeline-validation script (not a registered CLI)

`validate.py`'s `main(argv)`: fetches one ticker/date via `IBKRIntraDay`, prints a spot-check
summary (bar count, first/last timestamp, per-session bar and zero-volume counts), and writes a
CSV via `day_chart.output.bars_to_csv` (reused as-is -- same schema, no new format). Deliberately
has no `argparse`, no `pyproject.toml` entry point, and no test coverage of its own (`IBKRIntraDay`
itself is unit-tested; this script is just a thin manual harness around it) -- run directly with
`python -m ibkr_fetch.validate [TICKER] [YYYY-MM-DD]` against a running Gateway/TWS instance.
Defaults to `SPY`/`2026-07-31`, the task's original validation scope.

### `stock_quote` — first experiment CLI

Fetches and prints the current quote for a single stock ticker. Depends on `defs` for the
`YahooFinanceProvider` interface and `StockQuote` data type, and on `shared` for the default
`YahooFinance`/`IBKRQuote` implementations plus `Settings`/`Logger`/`AppError`. No dependency on
`yfinance` directly — that's confined to `shared/providers/yahoo_finance.py`.

- `output.py` — `quote_to_csv(quote) -> str`; columns include `provider` and `delayed`
- `cli.py` — `stock-quote` entry point; `main()` takes optional `provider: YahooFinanceProvider` and
  `settings_path: Path` parameters — simple parameter-based DI, no framework, letting tests inject
  `tests.mocks.yahoo_finance.MockYahooFinance` and a fixture settings file instead of monkeypatching
  or relying on `chdir` for isolation. `--provider {yahoo,ibkr}` (default `yahoo`, *not* flipped to
  `ibkr` — see `shared/providers/ibkr.py`'s `IBKRQuote` note above for why) selects the default
  construction path via `_build_provider(provider_name, settings) -> YahooFinanceProvider` — same
  name, shape, and purpose as `day_chart.cli`'s helper: constructed only when no `provider` was
  injected, and only after `Settings.load()` succeeds (provider construction moved after settings
  loading for this reason — previously `YahooFinance()` was constructed unconditionally before
  settings were even loaded, since there was nothing to select). `yahoo` needs no settings section;
  `ibkr` reads `Settings.ibkr` (or falls back to `IBKRQuote`'s own defaults if absent, same as
  `day_chart.cli`'s `ibkr` branch). `PROVIDER_YAHOO`/`PROVIDER_IBKR` here aren't independent string
  literals — they're aliases of each provider's own `PROVIDER_NAME` (`from shared.providers import
  ibkr, yahoo_finance`), so the `--provider` flag's choices and each `StockQuote.provider`'s actual
  value structurally can't drift apart (unlike, say, `CATEGORY_QUOTE_FETCH`, which *is* duplicated
  as a matching literal across `yahoo_finance.py`/`ibkr.py` — a log category mismatch is harmless
  where a provider-identity mismatch wouldn't be).

### `day_chart` — second experiment CLI

Fetches full-day intraday bars for one or more days for a single stock ticker and generates a
price/volume chart plus a CSV export. Depends on `defs` for the `IntraDayProvider` interface and
`DayBar`/`BarConflict` data types, and on `shared` for the default `QuantDataIntraDay`
implementation plus `Settings`/`Logger`/`AppError`. No dependency on `quant_data` or
`matplotlib.pyplot` outside its own `chart.py`/`shared/providers/` — bar (and conflict) fetching is
confined to `shared/providers/quant_data.py`.

- `output.py` — `bars_to_csv(bars) -> str`; columns include `incomplete`. No `BarConflict` export —
  the pending-resolution display is chart-only by design, `bars_to_csv`/`CSV_HEADERS` untouched.
- `chart.py` — `DayChartData = tuple[date, list[DayBar]]` (one day's session date + its bars).
  `render_chart(ticker, days: list[DayChartData], conflicts: list[BarConflict] | None = None) ->
  Figure`; pure figure construction, a 2×N grid
  (N = `len(days)`) built via a single `plt.subplots(2, N, sharex="col", squeeze=False,
  dpi=100, gridspec_kw={"height_ratios": [3, 1]}, layout="constrained")` — `sharex="col"` links each
  day's own price/volume pair without linking across days (each day gets its own
  midnight-to-midnight x-axis, since the calendar dates differ), `height_ratios` keeps every day's
  own price:volume split at 3:1, and `layout="constrained"` (rather than `tight_layout()`) avoids a
  `tight_layout`/shared-axes incompatibility warning while still leaving room for
  `figure.suptitle(ticker)` above the whole grid. The small horizontal padding between day panels is
  set explicitly in pixels rather than gridspec's relative `wspace`: `dpi` is pinned to `100` so
  pixels convert predictably to inches, then `figure.get_layout_engine().set(w_pad=5/100, wspace=0)`
  fixes the day-to-day gap at 5px regardless of figure width/day count (leaving `h_pad`/`hspace` —
  the price-to-volume gap within a day — at their constrained-layout defaults, untouched). Each day
  panel gets its own date as a subplot title; only the leftmost column labels its
  y-axes ("Price"/"Volume"), to avoid repeating them across every panel. Each subplot still shades
  by session via `axvspan`. Raises `AppError` for an empty `days` list. Runs under the `Agg` backend
  (module default) so it's headless-safe in tests/CI. Doesn't currently do anything visually
  distinct for `incomplete` bars — carried through the data only for now.

  `conflicts` (default `None`, treated as empty — existing 2-arg callers are unaffected) draws one
  candlestick per `ProviderBar` in each `BarConflict`, on whichever day column matches the
  conflict's own (ET) date: red for the `whistleblower`, blue for each `candidates` entry
  (`_draw_conflict`/`_draw_candlestick`). The whistleblower candle sits at the conflict's real
  timestamp (lines up with the existing close-price line); candidate candles fan out to its right,
  offset per candidate (`_CANDLE_OFFSET_DAYS`) so multiple candidates (possible, even though
  today's real data is always exactly one) stay visually distinct instead of fully overlapping.
  Colors and each candle's own real OHLC values, not a derived envelope — resolved a real design
  ambiguity (a conflict holds *two* competing bars; which one's values to plot?) by having
  `PendingResolutionBar.role` on the quant-data side, so each candle can just render its own
  provider's actual numbers. Each candle is a wick (`axis.plot`, a vertical low-to-high line) plus
  a body (`matplotlib.patches.Rectangle`, open-to-close, tagged `gid=_CONFLICT_CANDLE_GID` since
  `axvspan`'s session shading is *also* implemented with `Rectangle` patches internally — a plain
  `isinstance` check can't tell them apart, discovered when early candlestick-count tests found
  extra patches). First candlestick rendering in this module — the regular chart is a close-price
  line only, unaffected. This is `quant-data`-only in practice (`day_chart.cli` never passes
  conflicts for `ibkr`/`yahoo`), but `chart.py` itself has no such gating — it just draws whatever
  it's given.

  `show_chart(ticker, days, conflicts=None)`
  is the interactive entry point: switches to the `TkAgg` backend, calls `render_chart`, shows the
  figure non-blocking (`plt.show(block=False)`), registers a `close_event` callback on
  `figure.canvas` that flips a flag, then polls the GUI event loop itself
  (`while not closed: figure.canvas.start_event_loop(0.1)`) until that flag flips — i.e. until the
  user actually closes the popup window — before returning. Doesn't rely on `plt.show()`'s own
  blocking mainloop — that didn't reliably block when launched under the VS Code debugger
  (debugpy), closing the popup instantly; polling the event loop directly works the same way
  regardless of that environment. Deliberately calls `figure.canvas.start_event_loop()` directly
  rather than `plt.pause()`: `pyplot.pause()` calls `show(block=False)` on every single invocation,
  and for TkAgg, `FigureManagerTk.show()` unconditionally calls `canvas.draw_idle()` once the
  window's been shown once — not gated by `figure.stale` — forcing a full redraw of the whole
  figure on every poll tick regardless of whether anything actually changed. For a 6-day chart that
  measured ~1-1.5s per poll (vs the ~0.1s requested) — the real cause of the popup feeling
  "painfully sluggish," isolated with throwaway probe scripts that ruled out the SSH tunnel, Tcl/Tk
  itself (a pure-Tkinter `after()`+`mainloop()` probe stayed within a few ms of the requested
  interval), and `figure.raise_window`'s topmost-attribute toggling before landing on this.
  Bypassing `plt.pause()` still pumps Tk's event loop (so `close_event`/resize/etc. still fire),
  just without the forced redraw — confirmed back down to ~0.1s/poll. Also wraps `figure.canvas.draw`
  itself with a timing marker (`canvas.draw()`, `perf_ui`) — capturing the actual rendering cost
  regardless of what triggered it (a resize, a poll-forced redraw, anything) — logs each individual
  poll's duration (`event-loop poll N`, `perf_ui`) rather than only a final aggregate, and logs a
  `resize_event` marker with the new canvas size (`perf_ui`, no duration — the resize's own cost
  shows up as the `canvas.draw()` marker it triggers). Debounces resize-triggered redraws: wraps
  `figure.canvas.draw_idle` so every call cancels any pending scheduled draw and reschedules one
  `_RESIZE_DEBOUNCE_MS` (200ms) later via `tk_canvas.after`/`after_cancel`, rather than letting
  every intermediate `<Configure>` event during a drag trigger its own full redraw immediately.
  Needed because matplotlib's own `draw_idle()` dedup (skip if a draw's already scheduled) doesn't
  help once each draw takes several seconds — by the time one finishes, the *next* queued resize
  event (Windows streams `WM_SIZE` throughout a drag) triggers another one from scratch instead of
  ever getting collapsed; measured 2-3 full ~5-8s redraws per single drag gesture before this,
  down to exactly one after. Also remembers the popup's screen position across runs: reads
  `Settings.window` (via its own `Settings.load()` call — `show_chart` has no `Settings` parameter,
  since `cli.py` has no CLI flag for this and nothing to thread through) and applies it to the Tk
  window with `.geometry(f"+{x}+{y}")` if it's within `_get_virtual_desktop_bounds()` — silently
  falls back to the OS default position otherwise (a different monitor setup since it was last
  saved, say). `_get_virtual_desktop_bounds()` exists specifically because `winfo_screenwidth`/
  `winfo_screenheight` only report the *primary* monitor's resolution on Windows, not the full
  virtual desktop spanning every monitor (which can have a negative origin, for one positioned
  left of or above the primary) — a saved position on a secondary monitor would otherwise always
  look "off-screen" and get silently discarded. Queries `GetSystemMetrics`
  (`SM_XVIRTUALSCREEN`/`SM_YVIRTUALSCREEN`/`SM_CXVIRTUALSCREEN`/`SM_CYVIRTUALSCREEN`) via `ctypes`
  on `win32`, falling back to `winfo_screenwidth`/`winfo_screenheight` (single-monitor bounds) on
  any other platform or if that query fails for any reason. Tracks the window's position
  live via a `<Configure>` binding on the toplevel window (updated on every move/resize) rather
  than querying it once at close time: `close_event` fires in response to the widget's own
  `<Destroy>` event, so by the time a post-close handler runs the window is already mid-teardown
  and `winfo_x()`/`winfo_y()` raise — the fix isn't "catch that exception," it's "never query a
  dying widget in the first place." Saves the last-tracked position via
  `Settings.save_window_position()` right before closing. Both the read and the write are
  best-effort (broad `except Exception`, logged as a warning, never fatal) and a no-op on any
  backend without a real GUI window (`getattr(figure.canvas.manager, "window", None)` is `None`
  for Agg, used in tests) — this is a nicety, never something the popup should fail over. Kept
  separate from `render_chart` specifically so unit tests can exercise figure construction without
  ever touching a GUI backend.
- `cli.py` — `day-chart` entry point; `main()` takes optional `provider: IntraDayProvider`,
  `settings_path: Path`, `output_dir: Path`, and `show_chart: ShowChartFn` (`Callable[[str,
  list[DayChartData], list[BarConflict]], None]`) parameters — same parameter-based DI pattern as `stock_quote.cli`
  (tests inject a non-GUI stand-in for `show_chart`, same reason `provider` is injected instead of
  hitting a real database/Gateway). `--provider {ibkr,quant-data,yahoo,databento}` (default `ibkr`)
  selects which data source backs the default construction path — a real behavior change from when
  quant-data was the only option, deliberate: IBKR has strictly more data (real extended-hours
  volume) than the Yahoo-sourced quant-data path (see `shared/providers/ibkr.py`'s note above and
  [issue #12](https://github.com/croicu/quant-scratch/issues/12)). `yahoo`
  (`YahooFinanceIntraDay`, restored per [issue #14](https://github.com/croicu/quant-scratch/issues/14))
  is the third option, added purely for comparing a raw-source fetch against what's actually in the
  quant-data warehouse — not a data-quality improvement (see `shared/providers/yahoo_finance.py`'s
  note above). `databento` (`DatabentoIntraDay`, see `shared/providers/databento.py`'s note above) is
  the fourth, an additional paid source rather than a default change — IBKR already covers the
  extended-hours-volume need. The default provider can't be constructed before settings are loaded
  (`ibkr` needs `Settings.ibkr`, `quant-data` needs `Settings.postgres`, `databento` needs
  `Settings.databento`, `yahoo` needs nothing), so construction happens *after* `Settings.load()`
  succeeds, via `_build_provider(provider_name, settings) -> IntraDayProvider` — a small pure
  function factored out specifically so a unit test can assert the right provider *class* gets
  constructed (with what settings-derived arguments) without ever touching a real connection:
  `IBKRIntraDay.__init__` doesn't connect either way (connect-per-`fetch_bars`-call, see its own
  note above), `YahooFinanceIntraDay.__init__` takes no arguments at all, and `DatabentoIntraDay.
  __init__` only stores its api key/dataset (the actual HTTP client is constructed lazily inside
  `fetch_bars` via `client_factory`), so constructing any of the three in a test is already
  offline-safe; `QuantDataIntraDay.__init__` does connect eagerly, so no test exercises its
  construction path for real, same as before this change. `_build_provider` raises `AppError` if
  the provider-specific required settings are missing (`quant-data` requires `Settings.postgres`;
  `databento` requires `Settings.databento`; `ibkr`/`yahoo` have no required settings — `ibkr`'s
  absent `Settings.ibkr` just means every field falls back to its own default, and `yahoo` reads no
  settings at all). `output_dir` has no CLI flag
  (`--output-dir` was deliberately deferred); it exists purely as a test seam, the same role
  `settings_path` plays — it now only affects where the CSV lands, since the chart itself is shown
  in a popup rather than saved. Owns `resolve_session_date(date_argument, today)` — resolves the
  `--date` argument to a concrete session date, defaulting to today or rolling back to the prior
  Friday if today is a weekend, and raising `AppError` for a malformed, future, or weekend date —
  used when neither `--start-date` nor `--end-date` is given. Also owns
  `resolve_date_range(start_date_argument, end_date_argument, today)` — used instead of
  `resolve_session_date` whenever either range flag is given (`--date` is ignored in that case):
  `--end-date` alone defaults its start to the same day (so `--end-date X` alone behaves like
  `--date X`); `--start-date` alone defaults its end to today's `resolve_session_date`-style default;
  both given must satisfy `start <= end` (`AppError` otherwise). Individual range bounds are only
  format/future-validated, *not* weekend-rejected like `resolve_session_date` — a range legitimately
  spans weekends, which `main()` then skips. In range mode with `--provider ibkr`, a resolved range
  longer than `MAX_IBKR_RANGE_DAYS` (30) is rejected with `AppError` before any `fetch_bars` call —
  a margin under IBKR's documented 60-requests/10-minutes historical-data pacing ceiling that a
  per-day fetch loop could otherwise plausibly cross for a large range (a live probe of 7 rapid
  same-contract requests found no violation well below this cap, but 60+ at once is untested; see
  [tasks/day_chart_ibkr_integration.md](../tasks/day_chart_ibkr_integration.md)). No such cap
  applies to `quant-data` (no external pacing constraint on Postgres reads). For each resolved day,
  `main()` calls `provider.fetch_bars` individually; in range mode (2+ days), a per-day `AppError`
  (weekend, holiday, not-yet-ingested) is caught, logged via `Logger.warning` (category
  `date_range`), and that day is dropped from the chart rather than failing the whole command —
  only if *every* day in the range comes back empty does the command fail. In single-day mode, a
  fetch failure still propagates directly as before (unchanged). The CSV export flattens all
  charted days' bars into one file — `<TICKER>_<DATE>_data.csv` for a single day,
  `<TICKER>_<START>_<END>_data.csv` (the requested range's bounds, not just the days that actually
  had data) for a range. When `--provider quant-data` is selected, `main()` also calls
  `active_provider.fetch_conflicts(ticker, ...)` — once for the whole resolved date range (single
  day or range mode both pass through the same call, since `fetch_conflicts` already accepts a
  range), *always*, no separate opt-in flag — and threads the result through to `show_chart` as its
  third argument. A silent no-op (`conflicts = []`) for `ibkr`/`yahoo`/`databento`: nothing to
  dispute for a raw single-source fetch. `fetch_conflicts` isn't part of `IntraDayProvider`, so this call is
  gated on `arguments.provider == PROVIDER_QUANT_DATA` (the flag), not on the injected/constructed
  provider's type — consistent with how the `ibkr` range cap above is also gated on the flag rather
  than an `isinstance` check ([issue #15](https://github.com/croicu/quant-scratch/issues/15)).

### Test doubles (`tests/`)

- `tests/mocks/yahoo_finance.py` — `MockYahooFinance`, structurally implements the same
  `fetch_quote(ticker) -> StockQuote` shape as the real provider (no explicit inheritance from the
  `Protocol` — that's the point of structural typing). Reads fixture quotes from
  `tests/data/yahoo_finance_quotes.json`; raises `AppError` for a ticker not in the fixture, same
  contract as the real implementation.
- `tests/mocks/quant_data.py` — `MockQuantDataIntraDay`, the same structural-typing approach for
  `fetch_bars(ticker, target_date) -> list[DayBar]`; reads fixture bars from
  `tests/data/quant_data_bars.json` (each entry carries its own `incomplete` value; defaults
  `False` if omitted) and infers each bar's `session` via `shared.sessions.infer_session`, same as
  the real `QuantDataIntraDay`. Note this mocks quant-scratch's own `IntraDayProvider` shape
  end-to-end (for `day_chart` CLI-level tests) — it's a different, lower-level thing from
  `tests/unit/test_quant_data_provider.py`'s `FakeMarketData`, which mocks quant-data's
  `MarketData` client specifically to unit-test `QuantDataIntraDay`'s own conversion logic. Also
  has `fetch_conflicts(ticker, start_date, end_date) -> list[BarConflict]`, always returning `[]` —
  no fixture data for conflicts yet, since CLI-level tests only need the method to exist (`main()`
  always calls it for `--provider quant-data`); the real grouping/role-partitioning/validation
  logic is covered directly against `QuantDataIntraDay` in `test_quant_data_provider.py` instead.
- `tests/data/settings.json` — fixture settings file, DI'd into `Settings.load(path=...)` via
  `stock_quote.cli.main`'s (and `day_chart.cli.main`'s) `settings_path` parameter, so CLI tests
  don't depend on cwd isolation. Deliberately has no `postgres` section — exercises the "missing
  config" error path; day-chart's happy-path CLI tests inject a `provider` directly instead of
  relying on settings-driven construction (which would require a real database connection, and
  unit tests must run offline). Also has no `ibkr` section, which is fine either way — unlike
  `postgres`, that's a legitimate ("use all defaults") state rather than an error path, and since
  `IBKRIntraDay.__init__` never connects, a test exercising real default-provider construction
  (e.g. an oversized-range rejection that never reaches `fetch_bars`) can let it build for real
  without violating the offline-unit-test rule.
- `tests/unit/test_ibkr_quote.py`'s `_ticker(...)` helper — not a mock module under `tests/mocks/`
  (this one's private to that single test file), but worth flagging: `ib_async.Ticker.__post_init__`
  silently resets `last`/`volume`/`bid`/`ask`/etc. back to its own NaN sentinel unless
  `created=True` is also passed to the constructor. Discovered the hard way (a test constructing
  `Ticker(last=150.25, ...)` directly got `last=nan` back, not 150.25) — a real
  `ib_async`-specific quirk, not a general dataclass-testing concern: `ib_async.BarData` (used the
  same way in `test_ibkr_provider.py`) has no `__post_init__` and needs no equivalent workaround.

## Data flow

`stock-quote TICKER [--provider {yahoo,ibkr}]` → `cli._build_provider` (skipped if a `provider` was
injected) selects `shared.providers.yahoo_finance.YahooFinance` (default) or
`shared.providers.ibkr.IBKRQuote` from `Settings.ibkr` → injected `YahooFinanceProvider.fetch_quote`
(real, `yahoo`: a `yfinance` network call; real, `ibkr`: a connect-per-call `ib_async` request
against a local IB Gateway/TWS instance, live-first with an automatic delayed-data fallback; test:
`tests.mocks.yahoo_finance.MockYahooFinance`, a fixture lookup) → `StockQuote` →
`output.quote_to_csv` → stdout.

`day-chart TICKER [--date ... | --start-date ... --end-date ...] [--provider {ibkr,quant-data,yahoo,databento}]`
→ `cli._build_provider` (skipped if a `provider` was injected) selects `shared.providers.ibkr.IBKRIntraDay`
(default), `shared.providers.quant_data.QuantDataIntraDay`,
`shared.providers.yahoo_finance.YahooFinanceIntraDay`, or `shared.providers.databento.DatabentoIntraDay`
from `Settings.ibkr`/`Settings.postgres`/nothing/`Settings.databento` respectively → `cli.resolve_session_date`
(single day) or `cli.resolve_date_range` (either range flag given, plus a 30-day cap check when the
provider is `ibkr`) → one `list[date]` → per-date injected `IntraDayProvider.fetch_bars` (real,
`ibkr`: `IBKRIntraDay`, a connect-per-call `ib_async` request against a local IB Gateway/TWS
instance; real, `quant-data`: `QuantDataIntraDay`, wrapping a `quant_data.MarketData` read against
the Postgres warehouse; real, `yahoo`: `YahooFinanceIntraDay`, a direct `yfinance` network call;
real, `databento`: `DatabentoIntraDay`, a `databento.Historical.timeseries.get_range` HTTP request
against Databento's consolidated equities feed; all four tag each bar via
`shared.sessions.infer_session`; test: `tests.mocks.quant_data.MockQuantDataIntraDay`, a fixture
lookup) — in range mode, a per-day `AppError` is logged as a warning and that day dropped rather
than failing the whole command — → `list[DayChartData]` (`(date, list[DayBar])` per charted day).
When `--provider quant-data`, also → `QuantDataIntraDay.fetch_conflicts` (once for the whole
resolved range; silent no-op → `[]` for `ibkr`/`yahoo`/`databento`) → `list[BarConflict]`. Both → injected
`show_chart` (real: `chart.show_chart`, a blocking popup window rendering red/blue candlesticks for
any conflicts; test: a non-GUI stand-in) and, after flattening every charted day's bars into one
list, `output.bars_to_csv` (→ `<TICKER>_<DATE>_data.csv` for a single day,
`<TICKER>_<START>_<END>_data.csv` for a range; written to `output_dir`, CWD by default —
`BarConflict` data never reaches the CSV, chart-only by design).

## Contracts

<!-- protocols.py: persisted/shared data contracts (pure data).
     contracts.py: runtime behavioral interfaces (Protocol classes). -->

`protocols.py`/`contracts.py` live in the repo-wide `defs` package (see Modules above), not inside
any single implementation package — they're the specification every provider (real or mock)
conforms to, independent of which one is wired in.

- `defs.protocols.StockQuote` — pure data, no behavior; the CSV formatting in `stock_quote/output.py`
  operates on it rather than living on the dataclass itself.
- `defs.contracts.YahooFinanceProvider` — behavioral interface implemented by
  `shared.providers.yahoo_finance.YahooFinance` (production, `stock-quote`'s default provider),
  `shared.providers.ibkr.IBKRQuote` (production, selectable via `--provider ibkr`), and
  `tests.mocks.yahoo_finance.MockYahooFinance` (tests).
- `defs.protocols.DayBar` — pure data, no behavior; the CSV formatting in `day_chart/output.py` and
  the chart rendering in `day_chart/chart.py` both operate on it rather than living on the
  dataclass itself.
- `defs.contracts.IntraDayProvider` — behavioral interface implemented by
  `shared.providers.ibkr.IBKRIntraDay` (production, `day-chart`'s default provider),
  `shared.providers.quant_data.QuantDataIntraDay` (production, selectable via `--provider
  quant-data`), `shared.providers.yahoo_finance.YahooFinanceIntraDay` (production, selectable via
  `--provider yahoo`, for source-vs-warehouse comparison),
  `shared.providers.databento.DatabentoIntraDay` (production, selectable via `--provider
  databento`, requires a paid API key), and `tests.mocks.quant_data.MockQuantDataIntraDay` (tests).
- `defs.protocols.ProviderBar`/`BarConflict` — pure data, no behavior; grouped/produced by
  `QuantDataIntraDay.fetch_conflicts` and rendered (candlesticks) by `day_chart/chart.py`. Not part
  of `IntraDayProvider` — no behavioral interface governs these, since only `QuantDataIntraDay`
  has a reconciliation concept to report a conflict from; `IBKRIntraDay`/`YahooFinanceIntraDay`
  have no equivalent method at all, not an empty/stub one.
