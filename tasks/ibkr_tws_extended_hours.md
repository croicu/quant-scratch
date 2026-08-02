# IBKR TWS API Extended-Hours Intraday Provider

## Status: Brainstorm

Chosen path forward for SPY/QQQ extended-hours volume (superseding the postponed
[[databento_intraday_volume]] and [[local_data_cache_firstratedata]] tasks — see those files).
Account opened 2026-07-25; approval expected within 1-3 business days. This file's Brainstorm
status won't advance to Implementation until the account is approved and TWS/IBGateway access is
confirmed working — that's a manual prerequisite, not something Claude Code can do.

**Target shifted 2026-07-26**: `day-chart` no longer fetches intraday data live at all — it reads
from the [quant-data](https://github.com/croicu/quant-data) warehouse via `QuantDataIntraDay`
(quant-scratch#7). quant-data's own `quant-ingest` still pulls from Yahoo Finance and inherits its
extended-hours volume gap (flagged via `OHLCV.incomplete`, not fixed). So whenever this task is
picked back up, an IBKR-based provider would need to be implemented as a new *ingest*-side source
inside `quant-data` (alongside/replacing its `shared/providers/yf.py`), not as a `quant-scratch`
CLI provider as originally scoped below — the design below (session inference reuse, connect-per-
call lifecycle, etc.) still broadly applies, just in a different repo.

**Both halves of this brainstorm are now superseded by real work, 2026-08-02**: the `quant-scratch`
CLI-provider path this file originally scoped went ahead anyway (as a from-source pipeline-
validation/comparison tool, not a `day-chart` production dependency) — see
[quant-scratch#11](https://github.com/croicu/quant-scratch/issues/11) (closed; its task file was
deleted per this repo's own workflow once the issue closed — the issue body/comments are now the
record). The ingest-side path this note called out above is now tracked directly in quant-data:
[croicu/quant-data#21](https://github.com/croicu/quant-data/issues/21). This file stays only as
historical design context (other task files still link here for the session-inference-reuse/
connect-per-call reasoning) — no longer an active brainstorm.

## Problem statement

Same underlying problem as the postponed tasks: `YahooFinanceIntraDay` returns essentially zero
volume for SPY/QQQ outside regular trading hours (confirmed against live data — see
[[databento_intraday_volume]]'s problem statement). Interactive Brokers' TWS API is the chosen
replacement data source: free with any account (including IBKR Lite, no minimum deposit), serves
1-minute historical bars with extended-hours coverage via `reqHistoricalData(..., useRTH=False)`,
and — unlike Databento/FirstRateData — has no recurring-billing or per-download-cost model to
worry about, which was the deciding concern in both postponed tasks.

## Design decisions

Per the originating brainstorm note (folded into this file), with corrections against this repo's
actual conventions (the note's code sketch was written without seeing this codebase, so several
details don't match and shouldn't be carried forward as-is):

- **New provider**: `IBKRIntraDay`, implementing `defs.contracts.IntraDayProvider`
  (`fetch_bars(ticker, target_date) -> list[DayBar]`), wraps `ib_insync`'s
  `IB.reqHistoricalData(contract, durationStr="1 D", barSizeSetting="1 min", whatToShow="TRADES",
  useRTH=False)`.
- **Module location — corrected**: `src/shared/providers/ibkr.py`, not `src/shared/ibkr_finance.py`
  as the note suggested — this repo's providers now live under `shared/providers/` (see
  `shared/providers/yahoo_finance.py`), a convention established after that note was written.
- **Session inference — corrected**: reuse `shared.sessions.infer_session`, the same function
  `YahooFinanceIntraDay` already uses, instead of the note's own inline `_infer_session` static
  method. That inline version is redundant with existing code, doesn't handle timezone conversion
  (its own docstring admits "assumes UTC or ET; adjust if needed"), and its boundary logic
  disagrees with the existing after-market cutoff (it treats an exact 16:00 bar as `"regular"`;
  `shared.sessions.infer_session` treats `REGULAR_CLOSE` as the exclusive upper bound, so 16:00:00
  is `"after-market"` — the existing function is the one all providers should agree with).
- **Connection lifecycle — resolved**: `IBKRIntraDay.fetch_bars()` connects to TWS/IBGateway and
  disconnects within the same call, rather than exposing separate `connect()`/`disconnect()`
  methods the CLI has to call around it. The note's own `cli.py` sketch special-cases this with an
  `isinstance(provider, IBKRIntraDay)` check, which would tie `day_chart.cli.main()` to one
  concrete provider type — day-chart only calls `fetch_bars` once per run anyway, so there's no
  performance case for keeping a connection open across calls, and connect-per-call keeps
  `IBKRIntraDay` a drop-in `IntraDayProvider` with zero changes to `contracts.py` or `cli.py`.
- **No credential-handling problem** (unlike Databento): TWS authentication happens through the
  desktop app login, not an API key embedded in our code/settings. The provider only needs
  host/port/`client_id`, none of which are secrets — safe to default in code or (if made
  configurable later) in the committed `settings.json`.

## Open questions

- **Blocking prerequisite**: IBKR account approval (1-3 business days from 2026-07-25) and
  confirming TWS or IBGateway actually runs and accepts API connections locally. No implementation
  work can be verified end-to-end until then.
- **Market data entitlement risk**: IBKR is well known for requiring paid real-time market data
  subscriptions for live US equities quotes on some account tiers. The note claims "zero cost" but
  doesn't address whether `reqHistoricalData` for SPY/QQQ 1-minute bars needs such a subscription,
  or whether delayed/frozen historical data (which is usually free) is sufficient for this
  research use case. Needs verifying against the real account once approved, not assumed.
- **Paper vs. live port** (7497 vs. 7496): unclear which is appropriate for a data-only, no-trading
  use case, or whether it affects data entitlements/quality. Another item to verify hands-on.
- **`ib_insync` package/maintenance status**: the note links `github.com/ibis-trading/ib_insync`,
  which doesn't match the package's actual well-known home (`erdewit/ib_insync`) — that URL wasn't
  verified before being written into the original note and shouldn't be trusted without checking.
  `ib_insync` itself is also known to be lightly maintained upstream; worth a quick check at
  Implementation time for whether the community fork `ib_async` is the better-maintained choice of
  the two before pinning a dependency.
- **Provider selection**: with a third candidate provider now in play (Yahoo default, and
  previously-considered Databento/FirstRateData), `day_chart.cli.main()`'s current hardcoded
  `YahooFinanceIntraDay()` default can't just be silently swapped — worth deciding whether
  `day-chart` gains an explicit `--provider` flag (e.g. `yahoo`/`ibkr`) before `IBKRIntraDay`
  becomes usable, rather than only reachable via the `provider=` parameter in tests/scripts.
- **120-day lookback limit**: same shape of constraint as yfinance's ~30-day 1-minute limit, just
  wider. Following the same precedent set for `YahooFinanceIntraDay` (see `PROTOCOL.md`), an
  out-of-range date should surface as the same generic "no data available" `AppError` rather than
  a separate hardcoded pre-check.
- **`ib-insync` dependency**: only add it to `pyproject.toml` once the above is settled — no point
  pinning a dependency for a provider that can't be tested yet.

## Implementation plan

<!-- Added when advancing to Implementation, once the IBKR account is approved and TWS/IBGateway
     access is confirmed working. -->

## Test results

<!-- Added when advancing to Testing / Ready to Submit. -->
