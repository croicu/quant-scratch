# ibkr-fetch-historical-spy

## Status: Testing

## Problem statement

Need to validate IBKR Gateway API pipeline for fetching intraday + extended-hours historical data (SPY on 7/31/2026). This is the foundation for the premarket signal backtest. Must confirm:
1. ib_insync can pull 1-min bars for regular + extended hours
2. Data includes both price (OHLC) and volume
3. Data quality is usable for signal testing (no gaps, correct timestamps)

Without this working, can't proceed to signal validation.

## Design decisions

- **Library:** ib_insync (Python wrapper around TWS API) — cleaner than raw socket API, handles reconnection
- **Data source:** IB Gateway (lightweight, already running) vs TWS (full bloat)
- **Bar resolution:** 1-minute bars (captures premarket/extended hours movement, fine-grained enough for signal detection)
- **Extended hours:** Request both RTH (regular trading hours: 9:30-16:00 ET) and EXTENDED (4:00-20:00 ET for premarket 4:00-9:30 and afterhours 16:00-20:00)
- **Data structure:** Store as pandas DataFrame (timestamp, open, high, low, close, volume) for easy analysis + backtest compatibility
- **Scope (first pass):** SPY 7/31/2026 only (validate pipeline before expanding to multiple dates or QQQ)

## Open questions

- Does premarket data (4:00-9:30 ET) include volume from Cboe One / IEX? Or only RTH volume?
- Exact time range for 7/31 — request 4:00 ET to 20:00 ET to capture full day?
- Do we need separate contracts for extended vs regular, or one request with whatToShow=TRADES covers both?

## Implementation plan

1. **ib_insync setup** (setup.py / requirements.txt)
   - Install ib_insync
   - Verify connection to IB Gateway (localhost:7497 for paper)

2. **Fetch SPY 7/31 historical** (ibkr_fetch.py)
   - Create Contract for SPY
   - Request 1-min bars, whatToShow=TRADES, useRTH=False (extended hours)
   - Handle pagination if needed (IBKR limits bar requests)
   - Parse response into DataFrame

3. **Validation / export** (ibkr_fetch.py continued or separate validate.py)
   - Check data shape (expect ~500+ 1-min bars for full day)
   - Spot-check timestamps (4:00 ET through 20:00 ET)
   - Spot-check volume (non-zero during premarket, regular, afterhours)
   - Export to CSV for manual inspection

4. **Integration** (working.md)
   - Document exact request format for future signal backtest
   - Record any quirks (gaps, missing hours, volume anomalies)

## Test results

**Implementation** (2026-08-01): built as a real, reusable provider rather than a throwaway
script, per user direction — `IBKRIntraDay` in `src/shared/providers/ibkr.py`, implementing
`defs.contracts.IntraDayProvider` (same interface `QuantDataIntraDay` implements), plus a minimal
manual validation harness at `src/ibkr_fetch/validate.py` (no argparse/CLI registration — run via
`python -m ibkr_fetch.validate [TICKER] [YYYY-MM-DD]`). Unit-tested offline with a fake IB client
(`tests/unit/test_ibkr_provider.py`, 6 tests, DI'd via a `client_factory` constructor param —
mirrors `QuantDataIntraDay`'s test pattern). Library: `ib_async` (not `ib_insync` — the community
fork is actively maintained where the original is archived; open question from
`ibkr_tws_extended_hours.md` now resolved).

**Live run** (`python -m ibkr_fetch.validate SPY 2026-07-31`, against the local paper-trading IB
Gateway on port 4002):

```
total bars: 960
first timestamp: 2026-07-31T08:00:00+00:00
last timestamp: 2026-07-31T23:59:00+00:00
pre-market: 330 bars, 20 with zero volume
regular: 390 bars, 0 with zero volume
after-market: 240 bars, 20 with zero volume
```

- **960 bars = 330 + 390 + 240**, exactly matching the 4:00–20:00 ET window's minute count for
  each session (pre-market 4:00–9:30, regular 9:30–16:00, after-market 16:00–20:00) — no gaps,
  confirmed by spot-checking the CSV directly (consecutive minutes through the pre-market→regular
  boundary at 13:30 UTC / 9:30 ET, and through to the after-market close at 23:59 UTC / 19:59 ET).
- **Answers the original open question**: pre-/after-market volume is real, not a Yahoo-style
  zero-volume gap — only 20/330 pre-market and 20/240 after-market bars had zero volume (plausible
  genuine no-trade minutes), vs. Yahoo Finance's confirmed 315/315 pre-market / 239/240
  after-market zero-volume bars for the same kind of data (see
  `quant_scratch_intraday_data_status` history). This is the reason the IBKR path was chosen over
  Yahoo/quant-data in the first place, now confirmed against real data.
- **One request covers both regular and extended hours**: a single `reqHistoricalData(...,
  useRTH=False, durationStr="1 D")` call returns the full session — no separate
  regular/extended-hours requests needed (an open question in the original brainstorm).
- Connection took ~10s (`ib.connect()` including `ib_async`'s default startup account-state
  fetch); `reqHistoricalData` itself was fast once connected.
- **Quirk**: `ib_async` prints `"open orders request timed out"` / `"completed orders request
  timed out"` directly to stdout (not through this repo's `Logger`) during `connect()`. Confirmed
  against the Gateway's own log (screenshot captured mid-run, not retained): the real cause is
  `"Error validating request... The API interface is currently in Read-Only mode"` — the Gateway's
  API is configured read-only (reasonable for a data-only paper account, prevents accidental order
  placement), which rejects `ib_async`'s default startup order/position-state fetch; `ib_async`
  reports the rejection as a timeout rather than surfacing the rejection reason directly. Unrelated
  to and harmless for historical-bar fetching (that request isn't order/position-related and still
  succeeds); could be silenced later by passing a narrower `fetchFields` to `connect()` if the
  noise becomes annoying.
- Historical Data Farm showed "Inactive" in the Gateway's own status panel before this run, and
  "ON: ushmds" during/after it — confirms that was just a lazy-connect state, not a real blocker.
- Confirmed empirically (not from IBKR docs): the Gateway was listening on port **4002**
  (paper-trading), not TWS's 7497/7496 — resolves that open question from
  `ibkr_tws_extended_hours.md` for at least this account/setup.

**Not done yet**: `day-chart` still hardcodes `QuantDataIntraDay` as its only provider —
`IBKRIntraDay` is validated standalone but not wired in. Per `ibkr_tws_extended_hours.md`'s own
open question, that would need a `--provider` flag (or similar) added to `day_chart.cli` first,
since swapping the hardcoded default outright would silently change what every existing `day-chart`
invocation does. Next step, per user request, once this is picked back up.

Tracked as [issue #11](https://github.com/croicu/quant-scratch/issues/11), labeled `status:testing`.
