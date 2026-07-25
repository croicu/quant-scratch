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

- `protocols.py` — pure data: `StockQuote` (`ticker`, `price`, `timestamp`, `volume`);
  `DayBar` (`timestamp: datetime` UTC-aware, `open`, `high`, `low`, `close`, `volume`, `session: str`).
  `DayBar.timestamp` is a `datetime` rather than a `str` like `StockQuote.timestamp` — an
  intentional divergence, since bar data needs real datetime arithmetic (session inference,
  sorting, ET conversion for the chart x-axis) that a string would just force back into a parsed
  datetime anyway.
- `contracts.py` — behavioral interfaces: `YahooFinanceProvider(Protocol)` — `fetch_quote(ticker) -> StockQuote`;
  `IntraDayProvider(Protocol)` — `fetch_bars(ticker, target_date) -> list[DayBar]`

### `shared` — shared framework + default implementations

Every experiment package depends on this one for bootstrap; it owns no experiment-specific logic
and has no CLI/console script of its own.

- `diagnostics.py` — `Logger`, log sinks (`ConsoleLogSink`), telemetry levels/records
- `settings.py` — `Settings.load(path, local_path)` / `Settings.current()`, reads `settings.json` +
  `settings.local.json` by default; both paths are DI'd parameters (default `./settings.json` /
  `./settings.local.json`) rather than hardcoded, so callers/tests can point at a fixture instead
- `errors.py` — `AppError`, `TaskError`, `telemetry_session()`
- `sessions.py` — `infer_session(timestamp_utc) -> str`, classifying a UTC timestamp into
  `"pre-market"` (4:00–9:30 ET), `"regular"` (9:30–16:00 ET), or `"after-market"` (16:00–20:00 ET);
  raises `AppError` for a timestamp outside that range. Lives directly in `shared` (not in
  `day_chart`, despite being introduced for that experiment, and not in `shared/providers/` since
  it isn't itself a provider) because it's needed to construct `DayBar` instances inside
  `shared.providers.yahoo_finance.YahooFinanceIntraDay` and inside the test mock — putting it in
  `day_chart` would have made `shared` depend on an experiment package, inverting the intended
  dependency direction.
- `providers/` — one module per external data source, each providing a default implementation of
  a `defs.contracts` interface. Separated from the rest of `shared` so multiple providers (Yahoo
  today; a future local-CSV or Databento provider) can sit side by side without crowding a single
  flat file list.
  - `yahoo_finance.py` — `YahooFinance`, the default implementation of
    `defs.contracts.YahooFinanceProvider`; wraps `yfinance`, raises `AppError` on an invalid
    ticker or network failure. Also `YahooFinanceIntraDay`, the default implementation of
    `defs.contracts.IntraDayProvider`; wraps `yfinance.Ticker(...).history(interval="1m",
    prepost=True)` for a single day, tags each bar's session via `sessions.infer_session`, and
    raises `AppError` on an invalid ticker, network failure, or no bars returned (covers both an
    out-of-range date and a genuine data gap — no separate pre-check for yfinance's ~30-day
    1-minute lookback limit).

### `stock_quote` — first experiment CLI

Fetches and prints the current quote for a single stock ticker. Depends on `defs` for the
`YahooFinanceProvider` interface and `StockQuote` data type, and on `shared` for the default
`YahooFinance` implementation plus `Settings`/`Logger`/`AppError`. No dependency on `yfinance`
directly — that's confined to `shared/providers/yahoo_finance.py`.

- `output.py` — `quote_to_csv(quote) -> str`
- `cli.py` — `stock-quote` entry point; `main()` takes optional `provider: YahooFinanceProvider` and
  `settings_path: Path` parameters (defaulting to `shared.providers.yahoo_finance.YahooFinance()` and
  `Settings.load()`'s own default path respectively) — simple parameter-based DI, no framework,
  letting tests inject `tests.mocks.yahoo_finance.MockYahooFinance` and a fixture settings file
  instead of monkeypatching or relying on `chdir` for isolation

### `day_chart` — second experiment CLI

Fetches full-day intraday bars for a single stock ticker and generates a price/volume chart plus a
CSV export. Depends on `defs` for the `IntraDayProvider` interface and `DayBar` data type, and on
`shared` for the default `YahooFinanceIntraDay` implementation plus `Settings`/`Logger`/`AppError`.
No dependency on `yfinance` or `matplotlib.pyplot` outside its own `chart.py` — bar fetching is
confined to `shared/providers/yahoo_finance.py`.

- `output.py` — `bars_to_csv(bars) -> str`
- `chart.py` — `render_chart(ticker, session_date, bars, output_path)`; two-subplot matplotlib
  figure (price line on top, volume bars below), x-axis converted to US/Eastern for display
  (storage/CSV stay UTC), each subplot shaded by session via `axvspan`. Raises `AppError` for an
  empty `bars` list. Uses the `Agg` backend so it runs headless in tests/CI.
- `cli.py` — `day-chart` entry point; `main()` takes optional `provider: IntraDayProvider`,
  `settings_path: Path`, and `output_dir: Path` parameters (defaulting to
  `shared.providers.yahoo_finance.YahooFinanceIntraDay()`, `Settings.load()`'s own default path, and CWD
  respectively) — same parameter-based DI pattern as `stock_quote.cli`. `output_dir` has no CLI
  flag (`--output-dir` was deliberately deferred); it exists purely as a test seam, the same role
  `settings_path` plays. Also owns `resolve_session_date(date_argument, today)` — resolves the
  `--date` argument to a concrete session date, defaulting to today or rolling back to the prior
  Friday if today is a weekend, and raising `AppError` for a malformed, future, or weekend date.

### Test doubles (`tests/`)

- `tests/mocks/yahoo_finance.py` — `MockYahooFinance`, structurally implements the same
  `fetch_quote(ticker) -> StockQuote` shape as the real provider (no explicit inheritance from the
  `Protocol` — that's the point of structural typing). Reads fixture quotes from
  `tests/data/yahoo_finance_quotes.json`; raises `AppError` for a ticker not in the fixture, same
  contract as the real implementation. Also `MockYahooFinanceIntraDay`, the same structural-typing
  approach for `fetch_bars(ticker, target_date) -> list[DayBar]`; reads fixture bars from
  `tests/data/day_bars.json` and infers each bar's `session` via `shared.sessions.infer_session`,
  same as the real `YahooFinanceIntraDay`.
- `tests/data/settings.json` — fixture settings file, DI'd into `Settings.load(path=...)` via
  `stock_quote.cli.main`'s (and `day_chart.cli.main`'s) `settings_path` parameter, so CLI tests
  don't depend on cwd isolation.

## Data flow

`stock-quote TICKER` → injected `YahooFinanceProvider.fetch_quote` (real: `shared.providers.yahoo_finance.YahooFinance`,
a `yfinance` network call; test: `tests.mocks.yahoo_finance.MockYahooFinance`, a fixture lookup) →
`StockQuote` → `output.quote_to_csv` → stdout.

`day-chart TICKER [--date ...]` → `cli.resolve_session_date` → injected
`IntraDayProvider.fetch_bars` (real: `shared.providers.yahoo_finance.YahooFinanceIntraDay`, a `yfinance`
network call tagging each bar via `shared.sessions.infer_session`; test:
`tests.mocks.yahoo_finance.MockYahooFinanceIntraDay`, a fixture lookup) → `list[DayBar]` → both
`chart.render_chart` (→ `<TICKER>_<DATE>_chart.png`) and `output.bars_to_csv` (→
`<TICKER>_<DATE>_data.csv`), both written to `output_dir` (CWD by default).

## Contracts

<!-- protocols.py: persisted/shared data contracts (pure data).
     contracts.py: runtime behavioral interfaces (Protocol classes). -->

`protocols.py`/`contracts.py` live in the repo-wide `defs` package (see Modules above), not inside
any single implementation package — they're the specification every provider (real or mock)
conforms to, independent of which one is wired in.

- `defs.protocols.StockQuote` — pure data, no behavior; the CSV formatting in `stock_quote/output.py`
  operates on it rather than living on the dataclass itself.
- `defs.contracts.YahooFinanceProvider` — behavioral interface implemented by both
  `shared.providers.yahoo_finance.YahooFinance` (production) and `tests.mocks.yahoo_finance.MockYahooFinance` (tests).
- `defs.protocols.DayBar` — pure data, no behavior; the CSV formatting in `day_chart/output.py` and
  the chart rendering in `day_chart/chart.py` both operate on it rather than living on the
  dataclass itself.
- `defs.contracts.IntraDayProvider` — behavioral interface implemented by both
  `shared.providers.yahoo_finance.YahooFinanceIntraDay` (production) and
  `tests.mocks.yahoo_finance.MockYahooFinanceIntraDay` (tests).
