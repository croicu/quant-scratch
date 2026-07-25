# ARCHITECTURE.md

Modules, data flow, and contracts for `quant-scratch`.

## Modules

<!-- One entry per module under src/<package>/: what it owns, what it depends on. -->

### `shared` — shared framework

Every experiment package depends on this one for bootstrap; it owns no experiment-specific logic
and has no CLI/console script of its own.

- `diagnostics.py` — `Logger`, log sinks (`ConsoleLogSink`), telemetry levels/records
- `settings.py` — `Settings.load()` / `Settings.current()`, reads `settings.json` + `settings.local.json`
- `errors.py` — `AppError`, `TaskError`, `telemetry_session()`
- `protocols.py` / `contracts.py` — empty scaffolding for future shared data/behavior contracts

### `stock_quote` — first experiment CLI

Fetches and prints the current quote for a single stock ticker. Depends on `shared` for
`Settings`/`Logger`/`AppError`.

- `protocols.py` — `StockQuote` dataclass (`ticker`, `price`, `timestamp`, `volume`)
- `fetcher.py` — `fetch_quote(ticker) -> StockQuote`, wraps `yfinance`; raises `AppError` on an
  invalid ticker or network failure
- `output.py` — `quote_to_csv(quote) -> str`
- `cli.py` — `stock-quote` entry point

## Data flow

`stock-quote TICKER` → `fetcher.fetch_quote` (yfinance network call) → `StockQuote` →
`output.quote_to_csv` → stdout.

## Contracts

<!-- protocols.py: persisted/shared data contracts (pure data).
     contracts.py: runtime behavioral interfaces (Protocol classes). -->

- `stock_quote.protocols.StockQuote` — pure data, no behavior; the CSV formatting in `output.py`
  operates on it rather than living on the dataclass itself.
