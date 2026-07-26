# Databento Intraday Volume Provider

## Status: Postponed

Postponed 2026-07-25 — Databento's usage-based billing model was a concern (free credit today,
but a real risk of being charged automatically once it runs out if usage isn't tracked carefully).
[[local_data_cache_firstratedata]] was briefly considered instead, then also postponed; the chosen
path forward is [[ibkr_tws_extended_hours]] (IBKR TWS API — free with any account, no recurring
per-usage billing). Revisit only if IBKR doesn't pan out (account/data-entitlement issues, etc.).

## Problem statement

`day-chart`'s default `YahooFinanceIntraDay` provider (`shared/yahoo_finance.py`) returns
1-minute OHLCV bars via yfinance, but extended-hours volume is essentially always zero: confirmed
against live SPY data for 2026-07-24, 315/315 pre-market bars and 239/240 after-market bars had
`volume == 0`, while price (open/high/low/close) moved normally throughout. Reproduced identically
via both `yfinance.Ticker(...).history(interval="1m", prepost=True)` and
`yfinance.download(..., prepost=True)` — this is a genuine Yahoo Finance data gap, not a bug in
how we call the API, so Yahoo Finance is excluded as a source for extended-hours volume.

The user's actual instruments of interest are **SPY** and **QQQ** — the two most liquid ETFs —
specifically to study price/volume behavior at session transitions (pre-market → open, close →
after-market), which is the whole point of `day-chart`. Without real extended-hours volume, that
analysis is incomplete for exactly the tickers that matter most.

## Design decisions

Recommendation from a Claude Chat brainstorm session (see original note, since folded into this
file): use [Databento](https://databento.com) for SPY/QQQ extended-hours volume — explicitly
supports US-listed ETFs, offers 1-minute bars with full pre/regular/after-market volume, has a
Python client, $125 free credit for new accounts, and fits the existing `IntraDayProvider`
protocol (`fetch_bars(ticker, target_date) -> list[DayBar]`) as a drop-in alternative
implementation alongside `YahooFinanceIntraDay`.

## Open questions

- **Manual prerequisite**: needs a Databento account + API key before any implementation can
  start — that signup step is the user's to do, not something Claude Code can perform.
- **Credential handling**: where does the API key live? Needs a non-committed location (e.g.
  `settings.local.json` or an environment variable) — `settings.json` is checked in, so it can't
  hold a secret directly.
- **Provider selection**: does `day-chart` gain a way to choose between `YahooFinanceIntraDay` and
  a new `DatabentoIntraDay` (e.g. a CLI flag, a settings toggle), or does `DatabentoIntraDay`
  simply become the new default? `IntraDayProvider` was already designed as a swappable
  interface, so either is architecturally easy — this is a product decision, not a constraint.
- **Scope of ticker coverage**: Databento's free credit is what funds this — is coverage limited
  to SPY/QQQ for now, or should the tool assume any ticker might work (with Yahoo as a fallback
  for symbols Databento doesn't cover well)?
- Confirm whether Databento's `history`-equivalent endpoint actually returns non-zero
  extended-hours volume for SPY/QQQ before committing to the implementation (the addendum's claim
  is unverified against live data, unlike the Yahoo Finance gap above which we did verify
  ourselves).

## Implementation plan

<!-- Added when advancing to Implementation, once the above open questions are resolved and an
     API key is available. -->

## Test results

<!-- Added when advancing to Testing / Ready to Submit. -->
