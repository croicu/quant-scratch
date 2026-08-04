# day-chart-pending-resolution-display

## Status: Testing

## Problem statement

quant-data's `quant-reconcile` now exposes its "stuck" queue — bars where candidate/whistleblower
providers disagree beyond tolerance and are awaiting `--finalize` or manual correction — through a
new public method on the same `MarketData` client `QuantDataIntraDay` already uses:

```python
MarketData.fetch_pending_resolution_bars(ticker, start_date, end_date) -> list[PendingResolutionBar]
# PendingResolutionBar: field_group: str, provider: str, bar: OHLCV
```

([croicu/quant-scratch#15](https://github.com/croicu/quant-scratch/issues/15), announcing
[croicu/quant-data#26](https://github.com/croicu/quant-data/issues/26)/commit `9bed431`, additive
— `fetch_bars` unchanged.) One entry per (bar, field group, provider) that reported a value, so a
disputed bar shows up as *multiple* entries (e.g. `ibkr`'s close and `yfinance`'s close for the
same disputed minute) — the actual disagreement, not just "this bar is stuck."

User wants this **visualized on `day-chart`** — surfacing which minutes in a chart are still
unresolved (and what the disagreement actually is), not just silently showing whatever
`fetch_bars` already promoted to `fact_market_data_1min`.

## Design decisions

- **Gating**: `--provider ibkr`/`yahoo` → silent no-op (no rejection). Nothing to dispute for a
  raw single-source fetch, so the feature simply doesn't activate rather than erroring.
- **Always on for `--provider quant-data`** — no separate opt-in flag. Every `quant-data` run
  fetches pending-resolution data alongside the regular bars.
- **Unblocked by an upstream API shape change**: `PendingResolutionBar` gained a `role:
  ProviderRole` field (`Enum`: `CANDIDATE`/`WHISTLEBLOWER`, mirroring `dim_provider.role`) —
  [croicu/quant-data#27](https://github.com/croicu/quant-data/issues/27), commit `7b4423b`. Today's
  data is exactly one whistleblower (`yfinance`) + one candidate (`ibkr`), but `dim_provider` isn't
  hardcoded to two rows — **do not assume exactly one candidate**, quant-data's own issue explicitly
  warns against this.
- **New data model, not a `DayBar` field** (`defs/protocols.py`): `ProviderBar` (`provider: str`,
  `bar: DayBar`) and `BarConflict` (`field_group: str`, `whistleblower: ProviderBar`, `candidates:
  list[ProviderBar]` — one item in the common case today, but a list since plurality is explicitly
  possible). Neither is part of `IntraDayProvider`'s shared interface — `IBKRIntraDay`/
  `YahooFinanceIntraDay` have no equivalent concept.
- **No CSV export** — purely a chart visualization, `bars_to_csv`/`CSV_HEADERS` untouched.
- **Range mode**: one `fetch_pending_resolution_bars` call for the whole resolved range
  (`session_dates[0]` .. `session_dates[-1]`), not per-day — the API already accepts a
  `start_date`/`end_date` range natively, so no reason to loop.
- **Visual: candlesticks colored by role** — one red candlestick using the *whistleblower's own*
  OHLC values, and one blue candlestick per *candidate's own* OHLC values (multiple candidates ⇒
  multiple blue candles, offset slightly so they don't fully overlap). Resolves the earlier
  envelope-vs-single-bar ambiguity entirely: each candle just renders its own provider's real
  values, no derived/guessed data. First candlestick rendering in `day_chart/chart.py` — today's
  chart is a close-price line only.

## Implementation plan

1. `defs/protocols.py`: add `ProviderBar`, `BarConflict` (see Design decisions).
2. `shared/providers/quant_data.py`: factor the existing `OHLCV` → `DayBar` conversion in
   `fetch_bars` into a small helper, reuse it in a new `fetch_conflicts(ticker, start_date,
   end_date) -> list[BarConflict]`: calls `MarketData.fetch_pending_resolution_bars`, groups
   entries by `(bar.timestamp, field_group)`, partitions each group by `role`, raises `AppError` if
   a group doesn't have exactly one `WHISTLEBLOWER` or has zero `CANDIDATE`s (unexpected shape, not
   silently guessed). Empty overall result is *not* an error (no disputes is the normal case,
   unlike `fetch_bars`'s empty-is-error semantics).
3. `day_chart/cli.py`: when `arguments.provider == PROVIDER_QUANT_DATA`, call
   `active_provider.fetch_conflicts(normalized_ticker, session_dates[0], session_dates[-1])`
   (works for both single-day and range mode, since `session_dates` is always a list) and pass the
   result through to `show_chart`.
4. `day_chart/chart.py`: `render_chart`/`show_chart` gain a new trailing optional `conflicts:
   list[BarConflict] | None = None` parameter — `DayChartData`'s existing tuple shape stays
   untouched (many existing tests construct `(date, bars)` directly). For each day/column, filter
   conflicts to that session date and draw a candlestick (wick + body `Rectangle`) per bar, red for
   `whistleblower`, blue for each `candidates` entry.
5. Tests: `fetch_conflicts` grouping/validation/multi-candidate cases in
   `test_quant_data_provider.py`; gating + always-on wiring in `test_day_chart_cli.py`; candlestick
   rendering (element counts, colors) in `test_day_chart_chart.py`.
6. Docs: `docs/ARCHITECTURE.md`, `docs/PROTOCOL.md`, `CLAUDE.md`.

## Test results

Implemented as planned (all 6 steps), against the corrected API shape (`PendingResolutionBar.role`
— see quant-data#27, not the earlier `9bed431` shape this file originally documented; required
re-syncing the `quant-data` pin twice more mid-task, `e86c902` → `cd22e858` → `81e1d4e2`, each time
via `pip install --force-reinstall --no-deps` since plain `pip install -e .` silently keeps a stale
VCS-cached copy when only the pin's commit hash changes).

**Discovered while writing tests**: `matplotlib.Axes.axvspan` (already used for session shading)
is itself implemented internally with `Rectangle` patches — a plain `isinstance(patch, Rectangle)`
check in a test couldn't distinguish candlestick bodies from session-shading rectangles. Fixed by
tagging candlestick bodies with `gid=_CONFLICT_CANDLE_GID` at creation time and filtering on that
in tests, rather than relying on type alone.

123/123 tests pass (`ruff format`/`ruff check` clean) — 20 new (9 `fetch_conflicts` grouping/
validation/multi-candidate/range tests, 5 `day_chart.cli` gating/wiring tests, 6 candlestick
rendering tests), plus a `MockQuantDataIntraDay.fetch_conflicts` stub and a test-helper fix for the
`show_chart`/`render_chart` signature's new trailing parameter.

**Live-verified against real disputed data**, not just fakes: found 3 real conflicts for SPY
(2026-07-28/29/30, all at the 16:00 ET regular/after-market boundary — one whistleblower `yfinance`
+ one candidate `ibkr` each). Ran `day-chart SPY --date 2026-07-28 --provider quant-data`
end-to-end: `fetch_conflicts` correctly grouped the real rows into one `BarConflict`
(whistleblower close=740.9, candidate `ibkr` close=740.84), `render_chart` drew exactly 2 candle
bodies with the correct colors/positions, CSV write and full command succeeded. Confirms both the
grouping logic and the render path work against production data, not just synthetic fixtures.
