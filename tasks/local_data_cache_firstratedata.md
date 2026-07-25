# Local Chunked Historical Data Cache (FirstRateData)

## Status: Brainstorm

## Problem statement

Repeatedly hitting a live API (yfinance, or a future paid provider) for intraday research is
wasteful and rate-limit-prone, and yfinance's data has known gaps for this project's purposes
(see [[databento_intraday_volume]] — extended-hours volume for SPY/QQQ is essentially always
zero from Yahoo). A local, incrementally-built cache of historical 1-minute OHLCV data — sourced
from [FirstRateData](https://firstratedata.com) — would let backtests and `day-chart` runs work
offline against previously-downloaded chunks, decoupled from any single live provider's limits or
gaps.

This is a broader, general-purpose data-management concern (useful for any future experiment that
needs repeated intraday history, not just `day-chart`), which is why it's tracked separately from
the narrower Databento provider task — both happen to address the same SPY/QQQ extended-hours
volume gap, but from different angles (buy access to a live feed vs. manually build a local
archive), and only one may end up needed depending on which proves more practical.

## Design decisions

Per the originating brainstorm note (folded into this file):

- **Chunking**: download and store data in monthly CSV chunks per ticker, not one large
  multi-year file — keeps downloads testable/resumable and disk usage predictable (~20MB/ticker/
  month, ~240MB/ticker/year; 27GB available makes this a non-issue at any realistic scale).
- **Folder structure**: `/data/<TICKER>/<TICKER>_<YYYY-MM>.csv`, plus `/data/README.md` tracking
  what's been downloaded (ticker, month, date fetched).
- **Not committed to git**: add `/data/*.csv` and `/data/**/*.csv` to `.gitignore` — keeps the
  repo lightweight; the cache is local working state, not source.
- **New provider**: `LocalCSVIntraDay` (structurally implements `IntraDayProvider`, same pattern as
  `YahooFinanceIntraDay`/a future `DatabentoIntraDay`) reads `/data/{TICKER}/{TICKER}_{YYYY-MM}.csv`
  for the requested ticker/date, parses rows into `DayBar`, and raises `AppError` with a clear
  "download this chunk" message if the file doesn't exist.
- **Future scaling**: if the local folder needs to be shared or archived, upload to a Cloudflare
  R2 bucket (10GB free tier) and repoint `LocalCSVIntraDay` at an R2 URL instead of disk — no
  changes needed to `day-chart` itself, since it only depends on the `IntraDayProvider` protocol.

## Open questions

- **Exact FirstRateData CSV schema** is unverified — column names/timestamp format/timezone need
  confirming against a real downloaded sample before the parser can be written; the note's schema
  table is a guess pending that.
- **Cost**: only a "2-week free sample" is mentioned before presumably-paid downloads — confirm
  what FirstRateData actually costs for the month/ticker range needed before committing to this
  as the long-term source.
- **Provider selection**: same open question as the Databento task — does `day-chart` gain an
  explicit way to choose between providers (CLI flag, settings toggle), does `LocalCSVIntraDay`
  become a transparent cache-first layer in front of `YahooFinanceIntraDay` (fetch live, save
  locally, reuse next time), or is it a fully separate opt-in provider the user wires in
  explicitly? This wasn't resolved in the originating note, which describes "falls back to other
  providers if local file missing" — implying a composite/fallback provider, not a simple swap.
- **Relationship to [[databento_intraday_volume]]**: both tasks solve the same underlying
  SPY/QQQ extended-hours volume problem. Revisit whether both are still needed once either is
  explored further, to avoid maintaining two parallel data sources for the same gap.
- Module location/name for the new provider (`src/shared/local_csv_finance.py` was the note's
  suggestion) — confirm against repo conventions once this reaches Implementation.

## Implementation plan

<!-- Added when advancing to Implementation. -->

## Test results

<!-- Added when advancing to Testing / Ready to Submit. -->
