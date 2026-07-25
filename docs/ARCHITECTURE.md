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

- `protocols.py` — pure data: `StockQuote` (`ticker`, `price`, `timestamp`, `volume`)
- `contracts.py` — behavioral interfaces: `YahooFinanceProvider(Protocol)` — `fetch_quote(ticker) -> StockQuote`

### `shared` — shared framework + default implementations

Every experiment package depends on this one for bootstrap; it owns no experiment-specific logic
and has no CLI/console script of its own.

- `diagnostics.py` — `Logger`, log sinks (`ConsoleLogSink`), telemetry levels/records
- `settings.py` — `Settings.load(path, local_path)` / `Settings.current()`, reads `settings.json` +
  `settings.local.json` by default; both paths are DI'd parameters (default `./settings.json` /
  `./settings.local.json`) rather than hardcoded, so callers/tests can point at a fixture instead
- `errors.py` — `AppError`, `TaskError`, `telemetry_session()`
- `yahoo_finance.py` — `YahooFinance`, the default implementation of `defs.contracts.YahooFinanceProvider`;
  wraps `yfinance`, raises `AppError` on an invalid ticker or network failure

### `stock_quote` — first experiment CLI

Fetches and prints the current quote for a single stock ticker. Depends on `defs` for the
`YahooFinanceProvider` interface and `StockQuote` data type, and on `shared` for the default
`YahooFinance` implementation plus `Settings`/`Logger`/`AppError`. No dependency on `yfinance`
directly — that's confined to `shared/yahoo_finance.py`.

- `output.py` — `quote_to_csv(quote) -> str`
- `cli.py` — `stock-quote` entry point; `main()` takes optional `provider: YahooFinanceProvider` and
  `settings_path: Path` parameters (defaulting to `shared.yahoo_finance.YahooFinance()` and
  `Settings.load()`'s own default path respectively) — simple parameter-based DI, no framework,
  letting tests inject `tests.mocks.yahoo_finance.MockYahooFinance` and a fixture settings file
  instead of monkeypatching or relying on `chdir` for isolation

### Test doubles (`tests/`)

- `tests/mocks/yahoo_finance.py` — `MockYahooFinance`, structurally implements the same
  `fetch_quote(ticker) -> StockQuote` shape as the real provider (no explicit inheritance from the
  `Protocol` — that's the point of structural typing). Reads fixture quotes from
  `tests/data/yahoo_finance_quotes.json`; raises `AppError` for a ticker not in the fixture, same
  contract as the real implementation.
- `tests/data/settings.json` — fixture settings file, DI'd into `Settings.load(path=...)` via
  `stock_quote.cli.main`'s `settings_path` parameter, so CLI tests don't depend on cwd isolation.

## Data flow

`stock-quote TICKER` → injected `YahooFinanceProvider.fetch_quote` (real: `shared.yahoo_finance.YahooFinance`,
a `yfinance` network call; test: `tests.mocks.yahoo_finance.MockYahooFinance`, a fixture lookup) →
`StockQuote` → `output.quote_to_csv` → stdout.

## Contracts

<!-- protocols.py: persisted/shared data contracts (pure data).
     contracts.py: runtime behavioral interfaces (Protocol classes). -->

`protocols.py`/`contracts.py` live in the repo-wide `defs` package (see Modules above), not inside
any single implementation package — they're the specification every provider (real or mock)
conforms to, independent of which one is wired in.

- `defs.protocols.StockQuote` — pure data, no behavior; the CSV formatting in `stock_quote/output.py`
  operates on it rather than living on the dataclass itself.
- `defs.contracts.YahooFinanceProvider` — behavioral interface implemented by both
  `shared.yahoo_finance.YahooFinance` (production) and `tests.mocks.yahoo_finance.MockYahooFinance` (tests).
