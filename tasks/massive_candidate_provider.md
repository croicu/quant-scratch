# Massive as a Second Candidate Provider in quant-data

<!--
Cross-repo note: this document describes work for quant-data's ingest/reconciliation pipeline,
not quant-scratch itself -- created here only because this session had quant-scratch open, not
quant-data. Tracking issue already open: croicu/quant-data#44. Move/copy this file into
quant-data's own tasks/ folder once that repo's Claude Chat/Code session picks this up, per that
repo's own task workflow (assumed to mirror this one -- see quant-data's own CLAUDE.md).
-->

## Status: Brainstorm

## Problem statement

quant-scratch validated Massive (formerly Polygon.io — `polygon.io` now 301-redirects to
`massive.com`, confirmed as a genuine rebrand, not a hijack) as a viable extended-hours intraday
data source in [croicu/quant-scratch#23](https://github.com/croicu/quant-scratch/issues/23) /
[PR #24](https://github.com/croicu/quant-scratch/pull/24) — free Basic tier genuinely covers
1-minute bars with full 4:00–20:00 ET extended-hours coverage, no premium gate (unlike Alpha
Vantage, tried first, which turned out not to cover intraday/daily time series on its free tier at
all).

A real comparison (SPY, 5 trading days, IBKR vs. Massive) found:

- Bar-count differences are fully explained by representation, not real disagreement: IBKR pads
  every minute with a zero-volume bar when nothing traded; Massive omits those minutes entirely.
  Every "missing" Massive timestamp was an exact match for an IBKR zero-volume bar, no exceptions.
- Close prices agree closely (18 of 4,277 shared bars differ by more than $0.01).
- Volume disagrees systematically, growing with session thinness: pre-market 1.08x, regular 1.24x,
  after-market **2.46x** (Massive consistently higher than IBKR).
- The 16:00 ET boundary bar (regular-close/after-market-open) stands out specifically: IBKR
  reports 2.6x–16x *more* volume than Massive at that one minute, consistently across all 5 days
  tested — likely a closing-auction-print attribution difference. This is the same boundary that's
  already recurred in quant-data's own reconciliation history (rejected-whistleblower and
  pending-resolution disputed-bar work both clustered there too).

The request: add Massive as a second `dim_provider` entry with `role = candidate`, alongside the
existing `ibkr` candidate. The schema already anticipates this — `BarConflict.candidates` on the
quant-scratch side is a list specifically because `dim_provider` isn't hardcoded to exactly one
candidate — but today's real data has only ever exercised one.

**No quant-scratch API changes are needed for this** — nothing about how quant-scratch reads from
quant-data (`create_postgres_provider`, `MarketData`, `fetch_bars`/`fetch_conflicts`/
`fetch_rejected_bars`) needs to change based on this integration.

## Design decisions

<!-- Fill in as the Claude Chat discussion converges. -->

## Open questions

1. **How does reconciliation resolve a disagreement between two candidates plus the
   whistleblower?** Today's logic has presumably only ever had to arbitrate whistleblower-vs-one
   candidate. Options include majority vote among all three, whistleblower keeping final say
   regardless of candidate count, pairwise tolerance comparison, or something else — needs a real
   design decision, not just "the schema supports it."
2. **Massive's ingest/backfill cadence.** Needs to respect its free-tier rate limit (documented
   5 calls/minute — though live testing in quant-scratch's `day_chart.cli --provider massive`
   found it isn't strictly enforced in practice, see PR #24's retry-on-429 logic). How does this
   interact with quant-data's existing ingest scheduling?
3. **Backfill bound.** Massive's free tier caps at 2 years of historical lookback (confirmed live
   — a request past that returns a plain HTTP 403). Does quant-data's backfill need explicit
   bounding logic for this, matching whatever pattern (if any) already exists for other
   bounded-history providers?
4. **`dim_provider` role re-confirmation.** Assumed `role = candidate` (matching `ibkr`), not
   `whistleblower` or `advisor` — worth re-confirming once the multi-candidate reconciliation logic
   is actually designed, in case the answer to question 1 changes this.
5. **Known consequence, not a blocker:** once live, `fact_market_data_1min` will contain a genuine
   mixture of `ibkr`- and `massive`-sourced bars per minute — reconciliation picks a winner per
   bar/field-group, and with two real candidates it can go either way. Worth deciding up front
   whether the canonical table should explicitly track which provider "won" each bar/field-group,
   for future inspectability, rather than retrofitting that later.
6. **Deferred, not blocking this integration:** eventually being able to inspect "what did
   provider X alone report" for the reconciled series. The raw per-provider data already exists
   (`market_data_archive`, `staging_market_data_1min`, both carry `provider_id`), so nothing is
   lost — there's just no first-class query/API surface for "the reconciled series, filtered to
   one provider's contributions" yet.

## Implementation plan

<!-- Added when advancing to Implementation. -->

## Test results

<!-- Added when advancing to Testing. -->
