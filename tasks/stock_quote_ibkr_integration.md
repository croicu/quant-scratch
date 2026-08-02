# stock-quote-ibkr-integration

## Status: Testing

## Problem statement

`day-chart` now supports `--provider {ibkr,quant-data}` ([tasks/day_chart_ibkr_integration.md](day_chart_ibkr_integration.md) / [issue #12](https://github.com/croicu/quant-scratch/issues/12)).
User request: give `stock-quote` the same `--provider` treatment.

Unlike `day-chart`'s case, no IBKR-backed live-quote provider exists yet —
`shared.providers.ibkr.IBKRIntraDay` implements `IntraDayProvider` (historical bars), a different
interface than `stock-quote`'s `YahooFinanceProvider.fetch_quote(ticker) -> StockQuote`. This task
is a real new build, not just CLI wiring.

## Design decisions

- **Market data entitlement — resolved empirically**: probed the live paper Gateway (throwaway
  script, not part of the repo) via `ib.reqTickers(contract)`. Real-time data failed outright
  (error 10089: "Requested market data requires additional subscription for API... Delayed market
  data is available", ticker came back all-NaN — no automatic fallback happens). Calling
  `ib.reqMarketDataType(3)` first and retrying got real delayed data (SPY last=744.20,
  volume≈62.4M, `marketDataType=3`). Delayed data works with **no subscription** on this account;
  live requires one IBKR doesn't have configured here.
- **`IBKRQuote.fetch_quote`**: tries live first (no explicit `reqMarketDataType` call, the API's
  own default), and only calls `reqMarketDataType(3)` + retries if the first attempt came back
  empty (`last` is NaN) — handles both this account (falls back to delayed) and a hypothetically
  entitled one (stays live) correctly, rather than hardcoding delayed. Reports which actually
  happened via the new `StockQuote.delayed` field (see below) — set from the real
  `ticker.marketDataType` returned (`!= 1` means not live), not assumed from which branch ran.
- **New `StockQuote.delayed: bool = False` field** (`defs/protocols.py`), mirroring the existing
  `DayBar.incomplete` pattern. `YahooFinance`/`MockYahooFinance` never set it explicitly (stays the
  dataclass default `False` — Yahoo's `fast_info` has no comparable delayed/live distinction
  surfaced today). `stock_quote/output.py`'s CSV gains a `delayed` column.
- **Default provider stays `yahoo`** — deliberately *not* mirroring `day-chart`'s flip to `ibkr`.
  `day-chart` flipped because IBKR was strictly more data (real extended-hours volume vs. Yahoo's
  zero-volume gap). Here it's a real tradeoff: Yahoo's `fast_info` is close to real-time; IBKR's
  free tier on this account is delayed ~15-20 minutes. Not a strict improvement, so no default
  change — user call.
- **Module placement**: `IBKRQuote` lives in `shared/providers/ibkr.py` alongside `IBKRIntraDay`
  (same external source, same connect-per-call/`client_factory` DI pattern, same
  `fetchFields=StartupFetch(0)` startup-fetch fix) rather than a new file — matches
  `yahoo_finance.py` previously holding both a quote and an intraday provider for the same source.
- **Connection settings**: reuses the existing `Settings.ibkr`/`IBKRSettings` section as-is (already
  added for `day-chart`) — no new settings needed, same host/port/client_id apply to any IBKR
  connection regardless of which provider uses it.
- **`stock_quote/cli.py`**: gains `--provider {yahoo,ibkr}` (default `yahoo`) and a
  `_build_provider(provider_name, settings) -> YahooFinanceProvider` helper, mirroring
  `day_chart.cli`'s helper of the same name and purpose (constructed only when no `provider` was
  injected). No range/pacing concerns here — `stock-quote` fetches once per invocation, no date
  range concept exists.

## Implementation plan

1. `defs/protocols.py`: add `StockQuote.delayed: bool = False`.
2. `stock_quote/output.py`: add `delayed` to `CSV_HEADERS` and the written row.
3. `shared/providers/ibkr.py`: add `IBKRQuote` implementing `fetch_quote(ticker) -> StockQuote` —
   live-first-then-delayed-fallback via `reqTickers`/`reqMarketDataType(3)`, same
   connect-per-call/`client_factory`/`fetchFields=StartupFetch(0)` shape as `IBKRIntraDay`.
4. `stock_quote/cli.py`: `--provider {yahoo,ibkr}` (default `yahoo`), `_build_provider` helper,
   wired into `main()`.
5. Tests:
   - `tests/unit/test_ibkr_quote.py`: new, mirrors `test_ibkr_provider.py`'s `FakeIB` pattern —
     live succeeds without fallback; live empty triggers delayed fallback; `delayed` reflects real
     `marketDataType`; connect/disconnect lifecycle; error handling.
   - `tests/unit/test_stock_quote_output.py` / `test_stock_quote_cli.py`: update for the new
     `delayed` CSV column; add `_build_provider` coverage matching `day_chart`'s test shape.
6. Docs: `docs/PROTOCOL.md` (`--provider` flag, `delayed` CSV column), `docs/ARCHITECTURE.md`
   (`ibkr.py`'s new `IBKRQuote` note, `stock_quote/cli.py`'s provider-selection logic), `CLAUDE.md`.

## Test results

Implemented as planned. 98/98 tests pass (`ruff format`/`ruff check` clean), 12 new
(`tests/unit/test_ibkr_quote.py` ×9 incl. the `fetchFields` and connection-lifecycle tests,
`tests/unit/test_stock_quote_cli.py` ×3 `_build_provider` tests, plus updated CSV/output tests for
the new `delayed` column).

**Real bug caught by the tests, not assumed**: `ib_async.Ticker.__post_init__` resets
`last`/`volume`/`bid`/`ask`/etc. back to its own NaN sentinel unless `created=True` is also passed
to the constructor — passing `Ticker(last=150.25, ...)` directly silently produces `last=nan`, not
150.25. Not documented anywhere obvious; discovered because the first test run failed with an
`IndexError` (the code's live-then-delayed-fallback logic saw NaN and tried a second `reqTickers`
call the fake only had one entry queued for). Fixed with a `_ticker(...)` test helper that always
passes `created=True`; noted inline since it'll bite anyone constructing a `Ticker` directly again.

**Live verification** against the running paper Gateway:

- `stock-quote SPY` (no flags, still `yahoo`) → near-live quote (`delayed=False`), unchanged
  behavior.
- `stock-quote SPY --provider ibkr` → live attempt hit the same entitlement wall as the earlier
  probe (error 10089, printed directly by `ib_async` to stdout — informative noise, not a bug),
  fell back to delayed automatically, returned `delayed=True` with the same price as the earlier
  probe (market closed on a Sunday, so both reflect Friday's last trade).

Confirms the live-first-then-delayed-fallback design works correctly end-to-end, not just against
fakes.

**Follow-up (same day)**: added `StockQuote.provider: str` (required, no default) alongside
`delayed` — the CSV/output now also records *which* provider supplied a quote, not just whether it
was delayed. Each provider stamps its own `PROVIDER_NAME` constant (`"yahoo"`/`"ibkr"`) onto the
quote it returns; `stock_quote.cli.PROVIDER_YAHOO`/`PROVIDER_IBKR` were changed from independent
string literals to aliases of those same constants (`from shared.providers import ibkr,
yahoo_finance`), so the `--provider` flag and each quote's self-reported identity are structurally
guaranteed to match rather than relying on two literals staying in sync by convention. Required
updating every `StockQuote(...)` construction site (both providers, the Yahoo mock, and CSV/output
tests) since the field has no default — deliberate: a quote's source is core identifying
information, not an edge-case flag like `delayed`. 98/98 tests still pass; verified live (both
`stock-quote SPY` and `stock-quote SPY --provider ibkr` now show the correct `provider` column).
