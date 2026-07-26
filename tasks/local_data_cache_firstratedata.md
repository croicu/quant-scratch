# Local Chunked Historical Data Cache (FirstRateData)

## Status: Postponed

Postponed 2026-07-25 — FirstRateData specifically isn't being pursued further; the chosen path
forward is [[ibkr_tws_extended_hours]] (IBKR TWS API). Kept rather than deleted since the
underlying local-cache design (chunking, folder layout, `IntraDayProvider`-shaped
`LocalCSVIntraDay`) is source-agnostic and may still apply later, e.g. as a local cache in front of
whatever provider ends up in use.

Two structural decisions from a 2026-07-25 brainstorm, to carry forward whenever this (or a
similar) local-cache task is picked back up, regardless of which source ends up feeding it:
- **Folder structure — namespace by source**: `/data/<source>/<TICKER>/<TICKER>_<YYYY-MM>.csv`
  (e.g. `/data/firstratedata/SPY/SPY_2024-01.csv`), not a flat `/data/<TICKER>/...` — so a second
  source added later (Databento or otherwise) can't collide with or be confused for this one.
- **Download tracking stays uncommitted**: since `/data/` is now fully gitignored (not just
  `*.csv`, per the same 2026-07-25 change), a `README.md`/manifest tracking what's been downloaded
  lives inside `/data/` too, uncommitted — it's local bookkeeping, not something that needs git
  history or cross-machine sharing.

---

*Everything below is the original brainstorm content, kept as historical record.*

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
- **Provider selection — resolved**: a fully separate, explicitly-selected provider, not a
  cache-first fallback in front of `YahooFinanceIntraDay`. A missing chunk raises a clear
  `AppError` telling the user which file to download, rather than silently falling back to a live
  fetch. Keeps the two providers' behavior predictable and easy to reason about independently.
- **Future scaling**: if the local folder needs to be shared or archived, upload to a Cloudflare
  R2 bucket (10GB free tier) and repoint `LocalCSVIntraDay` at an R2 URL instead of disk — no
  changes needed to `day-chart` itself, since it only depends on the `IntraDayProvider` protocol.

## Open questions

- **Blocking prerequisite**: exact FirstRateData CSV schema is unverified — column names,
  timestamp format, and timezone all need confirming against a real downloaded sample before the
  parser can be written; the note's schema table is a guess pending that. Next step is on the
  user: download the free 1-2 week SPY sample from firstratedata.com and drop it somewhere
  readable (this file's Brainstorm status won't advance to Implementation until that happens).
- **Cost**: only a "2-week free sample" is mentioned before presumably-paid downloads — confirm
  what FirstRateData actually costs for the month/ticker range needed before committing to this
  as the long-term source.
- **Relationship to [[databento_intraday_volume]]**: both tasks solve the same underlying
  SPY/QQQ extended-hours volume problem. Databento is being kept as a deprioritized backup (its
  usage-based billing model was a concern — risk of being charged once the free credit runs out,
  vs. FirstRateData's one-time-purchase-per-chunk model with no recurring billing surprise).
  Revisit only if FirstRateData's data or cost doesn't pan out.
- Module location/name for the new provider (`src/shared/local_csv_finance.py` was the note's
  suggestion) — confirm against repo conventions once this reaches Implementation.

## Implementation plan

<!-- Added when advancing to Implementation. -->

## Test results

<!-- Added when advancing to Testing / Ready to Submit. -->
