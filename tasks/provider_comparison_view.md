# provider-comparison-view

## Status: Brainstorm

## Problem statement

`day-chart` and `stock-quote` both now support multiple providers (`ibkr`/`quant-data`/`yahoo` and
`ibkr`/`yahoo` respectively — see issues #12/#13/#14), but each CLI invocation only ever fetches
from one provider at a time. Comparing providers today means re-running the command once per
provider and eyeballing separate CSVs/charts/outputs.

Surfaced from trying to do exactly this via `launch.json`: passing `--provider` more than once in
one config's `args` doesn't fan out to multiple providers — argparse's default `store` action just
keeps the *last* occurrence and silently drops the earlier ones (verified empirically: `--provider
quant-data --provider ibkr --provider yahoo` resolves to `yahoo`, not an error and not all three).

User's actual use case (per the day-chart/Yahoo-provider task, [issue #14](https://github.com/croicu/quant-scratch/issues/14)):
checking whether a given metric's absence is a real gap in a source vs. a gap in what's been
ingested into quant-data. That's inherently a *comparison* operation, and the user's stated
preference is to see it side-by-side, not as N separate outputs to cross-reference manually.

## Design decisions

<!-- None converged yet -- open questions below are exactly the things to resolve first. -->

## Open questions

- **Scope**: `day-chart` only (a chart naturally supports side-by-side panels — it already does
  this for multiple *days*, see `chart.py`'s `render_chart`/`DayChartData` grid), `stock-quote` only
  (simpler — one row per provider for the same ticker at roughly the same moment), or both?
- **Mechanism for `day-chart`**: a few candidate directions, no clear winner yet:
  - A `--providers` (plural) flag accepting multiple values, reusing/extending the existing
    N-columns grid layout (`render_chart` already stacks multiple *days* horizontally — the same
    approach could stack *providers* horizontally instead of, or combined with, days).
  - A CSV-shape change: one row per timestamp with a volume/price column *per provider*
    (`volume_ibkr`, `volume_yahoo`, ...) instead of one row per (day, provider) pair — easier to
    diff at a glance, but a bigger change to `output.bars_to_csv`'s existing shape.
  - A separate, dedicated comparison tool instead of extending `day-chart`/`stock-quote` at all —
    fits this repo's "each experiment gets its own small CLI" convention (per `CLAUDE.md`'s
    Mission), and keeps the existing single-provider commands simple rather than growing a
    "compare mode" bolted onto their existing single/range-mode toggle.
- **Mechanism for `stock-quote`**: simpler surface (no chart) — likely just fetching all requested
  providers and printing/writing one row per provider, but worth confirming that's actually useful
  compared to just running the command twice (a live quote's comparison value is lower than a full
  day's bar-by-bar volume comparison, which is the case that actually motivated this).
- **Partial failure handling**: `day-chart`'s existing range mode already has a precedent (a
  per-day fetch failure is logged as a warning and dropped, not fatal, unless *every* day fails) —
  does a per-*provider* failure in comparison mode follow the same pattern (e.g. IBKR Gateway not
  running shouldn't block a Yahoo-vs-quant-data comparison)?
- **IBKR pacing**: comparison mode fetching from `ibkr` alongside other providers for the same
  ticker/date doesn't change IBKR's own pacing limits (`day_chart.cli.MAX_IBKR_RANGE_DAYS`'s
  reasoning) — worth confirming this only interacts with single-day comparisons cleanly, not
  range-mode-times-N-providers multiplying request counts unexpectedly.

## Implementation plan

<!-- Added when advancing to Implementation. -->

## Test results

<!-- Added when advancing to Testing / Ready to Submit. -->
