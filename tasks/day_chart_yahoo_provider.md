# day-chart-yahoo-provider

## Status: Testing

## Problem statement

`day-chart --provider {ibkr,quant-data}` currently has no way to hit Yahoo Finance directly —
`YahooFinanceIntraDay` was removed entirely when `day-chart` switched to quant-data
([issue #7](https://github.com/croicu/quant-scratch/issues/7), since quant-data's own ingest
already pulls from Yahoo and re-fetching it directly was pure duplication at the time).

User request: bring it back as a third selectable provider. Not for its data quality (Yahoo has
the documented pre-/after-market zero-volume gap) — the actual use case is *comparison*: once
quant-data becomes the default (planned once the warehouse is fully populated — a separate future
change, not part of this task), being able to fetch straight from Yahoo (or IBKR) lets you check
whether a given metric is a real gap in what's been ingested vs. a gap in the underlying source
itself.

## Design decisions

- **Restore, not rebuild**: `YahooFinanceIntraDay` (`fetch_bars(ticker, target_date) -> list[DayBar]`)
  is recovered from git history (commit `2150132^`, right before its removal) and adapted to
  today's `shared/providers/yahoo_finance.py` (now also home to `YahooFinance`'s
  `PROVIDER_NAME = "yahoo"` constant, added since for `stock-quote`'s `StockQuote.provider` — reused
  as-is here as `day_chart.cli`'s third `--provider` choice, same alias pattern as `ibkr`/`yahoo`
  already use for `stock_quote.cli`).
- **Default stays `ibkr`** — this is purely additive. The user's own stated long-term plan (default
  flips to `quant-data` once the warehouse is fully populated) is explicitly a separate future
  change, not something to act on now.
- **No settings needed**: like the original, `yfinance.Ticker(...).history(...)` takes no
  connection config — `_build_provider`'s `yahoo` branch is a plain `YahooFinanceIntraDay()`, no
  `Settings` fields read.
- **Known limitation carried forward unchanged**: Yahoo's intraday feed doesn't populate
  extended-hours volume (the original reason quant-data's ingest was preferred, and the reason
  `IBKRIntraDay` was built at all). Not a regression — this provider is for comparison, not
  everyday use.

## Implementation plan

1. `shared/providers/yahoo_finance.py`: restore `YahooFinanceIntraDay` from git history, importing
   `DayBar`/`infer_session` (already used elsewhere in this module's neighbors) alongside the
   existing `StockQuote`/`YahooFinance` code already there.
2. `day_chart/cli.py`: add `PROVIDER_YAHOO = yahoo_finance.PROVIDER_NAME` alias, add to `--provider`
   choices, wire into `_build_provider`.
3. Tests: restore `tests/unit/test_yahoo_finance_intraday.py` (adapted from git history) plus a
   `_build_provider` test for the `yahoo` choice in `test_day_chart_cli.py`, matching the existing
   `ibkr`/`quant-data` coverage shape.
4. Docs: `docs/PROTOCOL.md` (`--provider` choices), `docs/ARCHITECTURE.md` (`yahoo_finance.py`
   module note, `day_chart.cli`'s provider list), `CLAUDE.md`.

## Test results

Implemented as planned. Restored `YahooFinanceIntraDay` and both its test files verbatim from git
history (commit `2150132^`) — no adaptation needed beyond re-adding the `date`/`timedelta`/
`DayBar`/`infer_session` imports `yahoo_finance.py` had dropped when the class was removed. 103/103
tests pass (`ruff format`/`ruff check` clean): 3 new unit tests
(`tests/unit/test_yahoo_finance_intraday.py`, restored), 1 new integration test
(`tests/integration/test_yahoo_finance_intraday.py`, restored, hits real Yahoo), 1 new
`_build_provider` test for the `yahoo` choice.

**Live verification**: `day-chart SPY --date 2026-07-31 --provider yahoo` → 945 bars (946 lines
incl. header), and — the whole point of this provider — **315/315 pre-market bars showed zero
volume**, an exact match for the gap documented back when `IBKRIntraDay` was first built (see
`quant_scratch_intraday_data_status` history / `tasks/ibkr_fetch_historical_spy.md`). Confirms the
provider now gives a direct, live comparison point against `--provider ibkr` (20/330 zero) and
`--provider quant-data` (same gap, inherited from this same source) for exactly the kind of
source-vs-warehouse check this task exists for.
