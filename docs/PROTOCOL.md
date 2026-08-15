# PROTOCOL.md

CLI signature and file format schemas for `quant-scratch`.

## CLI

<!-- Command name, arguments, flags, exit codes. -->

### `stock-quote`

- Usage: `stock-quote TICKER [--provider {yahoo,ibkr}] [--debug]`
- Fetches the current quote for a single ticker (case-insensitive) and prints it as CSV to stdout.
- `--provider {yahoo,ibkr}`: which data source to fetch from. **Defaults to `yahoo`**
  (`shared.providers.yahoo_finance.YahooFinance`, close to real-time). `ibkr`
  (`shared.providers.ibkr.IBKRQuote`) uses a local IB Gateway/TWS instance instead — tries live
  data first, and only falls back to delayed data (~15-20 minutes, `StockQuote.delayed=True`) if
  live isn't entitled on the connected account (a paid real-time market-data subscription is
  required for that; delayed data has no such requirement). Unlike `day-chart`'s equivalent flag,
  the default is *not* flipped to `ibkr` — IBKR isn't a strict improvement here the way extended-
  hours volume was for `day-chart`, since Yahoo's quote is closer to real-time than IBKR's free
  (delayed) tier.
- Requires an `ibkr` section in `settings.json` only if you want to override its defaults (see
  `day-chart`'s section below — shared by both commands) — `--provider ibkr` works out of the box
  against a local Gateway with no settings at all.
- `--debug` overrides `settings.json`'s `debug` flag; on a fetch failure with debug on, the
  underlying `AppError` is re-raised instead of being caught and printed.
- Exit codes: `0` success, `1` invalid ticker / no quote data available / network or connection
  error, `2` argument parsing error (argparse's default behavior on missing/bad args).

### `day-chart`

- Usage: `day-chart TICKER [--date YYYY-MM-DD | --start-date YYYY-MM-DD --end-date YYYY-MM-DD] [--provider {ibkr,quant-data,yahoo,databento}] [--debug]`
- Fetches full-day (pre-market + regular + after-market) 1-minute OHLCV bars for a single ticker
  (case-insensitive), pops up an interactive matplotlib chart window (one day, or several days'
  charts stacked horizontally — see below), and writes a CSV export to the current working
  directory. The command doesn't exit until you close the popup window; this is driven by polling
  the GUI event loop for the window's own close event, not `plt.show()`'s own blocking (which
  doesn't reliably block under a debugger).
- `--provider {ibkr,quant-data,yahoo,databento}`: which data source to fetch from. **Defaults to
  `ibkr`** (`shared.providers.ibkr.IBKRIntraDay`, a local IB Gateway/TWS instance) — real trade
  volume through pre-/after-market, unlike `quant-data`'s Yahoo-sourced gap (see
  `docs/ARCHITECTURE.md`). `quant-data` (`shared.providers.quant_data.QuantDataIntraDay`) reads the
  [quant-data](https://github.com/croicu/quant-data) warehouse instead — useful as a fallback if
  the local Gateway isn't running, or for dates further back than IBKR's lookback window. `yahoo`
  (`shared.providers.yahoo_finance.YahooFinanceIntraDay`) hits Yahoo directly — has the same
  pre-/after-market zero-volume gap as `quant-data`'s ingest (confirmed: 315/315 pre-market bars
  zero-volume for a live SPY pull), so it isn't useful as an everyday source; exists specifically
  so you can compare a raw-source fetch against what's actually in the warehouse (e.g. checking
  whether a metric's absence is a real gap in the source vs. an ingest gap). `databento`
  (`shared.providers.databento.DatabentoIntraDay`) hits Databento's consolidated equities feed
  (`DBEQ.BASIC` by default, overridable via `Settings.databento.dataset`) — requires a paid API
  key; added as an additional source alongside `ibkr`, not a default change, since IBKR already
  covers the extended-hours-volume need this was originally evaluated for. Whether your
  account/plan actually returns non-zero extended-hours volume for a given dataset is not
  guaranteed by this tool — verify against your own Databento entitlements.
- Requires either an `ibkr` section in `settings.json` (optional — see below, only needed to
  override the defaults) for `--provider ibkr`, a `postgres` section (required) for `--provider
  quant-data` (see `docs/PROTOCOL.md`'s settings notes below and quant-data's own
  `docs/DATABASE.md` for connecting to the box), a `databento` section (required, `apiKey`) for
  `--provider databento`, or nothing at all for `--provider yahoo` — a missing required section is
  an `AppError` (exit `1`), same as any other fetch failure.
- `--date YYYY-MM-DD`: single session date to fetch. Omit (and omit `--start-date`/`--end-date`) to
  default to today, or the last trading day (Friday) if today falls on a weekend. Rejected (exit
  `1`) if the date is malformed, in the future, or falls on a weekend. NYSE holidays are not
  validated explicitly, and the provider may simply not have data for the requested ticker/date yet
  — both surface as the same generic "no data available" error. **Ignored if either `--start-date`
  or `--end-date` is given.**
- `--start-date YYYY-MM-DD` / `--end-date YYYY-MM-DD`: fetch every day in this inclusive range
  instead of a single day — the popup shows one price/volume chart per day, stacked horizontally
  (same 3:1 price:volume split per day, small padding between days). Giving either flag switches
  the command into range mode (overriding `--date`); giving neither keeps today's single-day
  behavior unchanged.
  - Both given: fetches `start`..`end` inclusive. Rejected (exit `1`) if `start` is after `end`.
  - `--start-date` alone: end defaults to today's single-day default (today, or the last trading
    day if today is a weekend).
  - `--end-date` alone: start defaults to the same day as `--end-date` (i.e. behaves like `--date`
    with that value).
  - Each bound is only checked for a valid, non-future date — unlike `--date`, a bound landing on a
    weekend is not rejected outright, since a real range is expected to span weekends.
  - Days within the range that come back with no data (weekends, holidays, not yet ingested) are
    logged as a warning and dropped from the chart rather than failing the whole command. The
    command only fails (exit `1`) if *every* day in the range has no data.
  - **`--provider ibkr` only**: a range longer than 30 days is rejected up front (exit `1`, before
    any requests are made) — a safety margin under IBKR's documented historical-data pacing ceiling
    (60 requests/10 minutes), which a per-day fetch loop could plausibly cross for a large range.
    Not a measured breaking point, just an untested-but-documented one; a live probe of 7 rapid
    same-contract requests found no pacing violation well below this cap. Use `--provider
    quant-data` for longer ranges — no such constraint applies to Postgres reads.
- `--debug` overrides `settings.json`'s `debug` flag; on failure with debug on, the underlying
  `AppError` is re-raised instead of being caught and printed.
- Exit codes: `0` success, `1` invalid ticker / invalid date(s) / oversized `--provider ibkr` range /
  no data available (for any day, in single-day mode; for every day, in range mode) / missing
  required settings / connection error, `2` argument parsing error (argparse's default behavior on
  missing/bad args).
- On success, prints the written CSV path to stdout (after you press Enter to close the popup).
- **`--provider quant-data` only**: always (no separate flag) also fetches quant-reconcile's
  pending-resolution ("stuck") bars for the charted range and draws them on the popup as
  candlesticks — red for the whistleblower provider's own OHLC values, blue for each candidate
  provider's own OHLC values (see the popup section below). A silent no-op for
  `ibkr`/`yahoo`/`databento` — nothing to dispute for a raw single-source fetch. Never written to
  the CSV export.
- **`--provider quant-data` only**: also always fetches quant-data's rejected-whistleblower bars
  (a `yfinance` value flagged implausible by a per-provider quality check that auto-resolved
  without ever becoming a pending-resolution dispute) and draws them as orange candlesticks on the
  popup, using each bar's own real OHLC values (see the popup section below). Same silent no-op for
  `ibkr`/`yahoo`/`databento`, never written to the CSV export. **Not yet exercised against real
  data**: the quality check that sets this designation is still undesigned upstream in quant-data,
  so this always renders nothing today — see
  [issue #16](https://github.com/croicu/quant-scratch/issues/16).

### `open-quant-data`

- Usage: `open-quant-data SPREADSHEET`
- Opens its own SSH tunnel directly in Python (`sshtunnel`/`paramiko`, skipping relaunch if local
  port `5433` already accepts connections — same mechanism `day-chart --provider quant-data`
  already uses internally, no PuTTY/`plink` involved), opens the given `.xlsx` with the
  OS-associated app (Excel), then blocks — keeping the tunnel alive so Excel has something to
  refresh against — until Excel closes (polls for the `EXCEL.EXE` process; exits automatically once
  it's gone), or you press Ctrl+C to close the tunnel and exit early without closing Excel yourself.
- `SPREADSHEET`: path to an `.xlsx` workbook — either a stable checked-in example under
  `public/reports/` (e.g. `public/reports/sample.xlsx`) or an actively-refreshed, gitignored
  dashboard under `local/reports/` (e.g. `local/reports/SPY - Price and Volume.xlsx`; see
  `docs/ARCHITECTURE.md`'s note on why real dashboards live there instead). The workbook must
  already be wired up with a Power Query connection to the `quant-data-tunnel` ODBC DSN (one-time
  manual setup — see [issue #19](https://github.com/croicu/quant-scratch/issues/19)).
- Requires a `postgres` section in `settings.local.json` with `sshUser`/`sshKeyPath` set (the same
  section/fields `day-chart --provider quant-data`'s auto-tunnel reads — see that settings section
  below), plus a one-time manual setup done outside this repo: psqlODBC installed with a
  `quant-data-tunnel` System DSN pointed at `localhost:5433`. Nothing about the real hostname/key
  is stored in this repo or in any workbook — see `docs/ARCHITECTURE.md`'s `open_quant_data` entry.
- Exit codes: `0` success, `1` the tunnel failed to open (missing `sshUser`/`sshKeyPath`, SSH
  auth/connection failure) or the given spreadsheet path doesn't exist, `2` argument parsing error (missing
  `SPREADSHEET`).

### Settings: `ibkr` section (`settings.json` / `settings.local.json`)

Optional. Shared by both `day-chart --provider ibkr` (the default) and `stock-quote --provider
ibkr`, read by `shared.providers.ibkr.IBKRIntraDay` and `IBKRQuote` respectively — one connection
config for any IBKR-backed provider, since `host`/`port`/`client_id` mean the same thing regardless
of which one is using them. Unlike `postgres` below, every field already has a usable default
(matching the providers' own constructor defaults for a local paper-Gateway setup), so this
section — and any individual key within it — may be omitted entirely:

```json
{
  "settings": {
    "ibkr": {
      "host": "127.0.0.1",
      "port": 4002,
      "clientId": 1
    }
  }
}
```

`port` distinguishes IB Gateway/TWS instance and account type: `4002` paper / `4001` live for
Gateway, `7497` paper / `7496` live for TWS. `clientId` only needs to change if running more than
one API client against the same Gateway/TWS instance at once (each needs a distinct ID). None of
these are secrets — safe to commit in `settings.json` if ever overridden, same reasoning as
`postgres`'s non-secret fields below.

### Settings: `postgres` section (`settings.json` / `settings.local.json`)

Required by `day-chart --provider quant-data` (see above). `host`/`port`/`user`/`password`/`dbname`
aren't secret for a client connecting through an already-established local SSH tunnel, so that much
can live in the committed `settings.json`:

```json
{
  "settings": {
    "postgres": {
      "host": "localhost",
      "port": 5433,
      "user": "quant_reader",
      "password": "",
      "dbname": "quant_data"
    }
  }
}
```

`host`/`port` are the local tunnel endpoint, not the real database box — this shape assumes you
already have a manual SSH tunnel running (see quant-data's `docs/DATABASE.md`).

**Optional `sshUser`/`sshKeyPath`** (added [croicu/quant-data#17](https://github.com/croicu/quant-data/issues/17)):
when both are set, quant-data's `create_postgres_provider` opens and manages its own SSH tunnel
instead — no manually-run tunnel needed. Must be set together or not at all (`day-chart` raises an
error otherwise). When used, `host`/`port` switch meaning to the *real database box and its actual
Postgres port* (not a local tunnel endpoint):

```json
{
  "settings": {
    "postgres": {
      "host": "<ubuntu_host>",
      "port": 5432,
      "user": "quant_reader",
      "password": "",
      "dbname": "quant_data",
      "sshUser": "<ssh_user>",
      "sshKeyPath": "/path/to/private/key"
    }
  }
}
```

The real hostname/`sshUser`/`sshKeyPath` are not secret in the sense of needing encryption, but
they identify a specific private machine — keep this block in `settings.local.json` (gitignored),
never the committed `settings.json`.

### Settings: `databento` section (`settings.local.json` only — never commit)

Required by `day-chart --provider databento` (see above). `apiKey` is a real secret (a paid
Databento account credential), unlike `postgres`'s fields above, so this section must live in
`settings.local.json` (gitignored) only — never the committed `settings.json`:

```json
{
  "settings": {
    "databento": {
      "apiKey": "db-...",
      "dataset": "DBEQ.BASIC"
    }
  }
}
```

`dataset` is optional, defaulting to `"DBEQ.BASIC"` (Databento's consolidated multi-venue US
equities feed) if omitted — override it if your account is entitled to a different dataset (e.g. a
single-exchange feed like `"XNAS.ITCH"`).

### Settings: `window` section (`settings.local.json`, auto-managed — don't hand-edit)

Optional. When present, `day-chart` opens its popup at this screen position instead of the OS
default:

```json
{
  "settings": {
    "window": {
      "x": 100,
      "y": 200
    }
  }
}
```

Both `day_chart.chart.show_chart` writes and reads this itself — it saves the popup's position to
`settings.local.json` (never the committed `settings.json`, since it's a per-machine UI preference)
every time the window closes, and applies it on the next open. Purely a hint: if the saved position
would land off the current screen (e.g. a different monitor setup since it was last saved), it's
ignored and the OS default position is used instead. `cli.py` has no flag for this and no role in
it — the read/write happens entirely inside `chart.py`.

## File formats

<!-- Schemas for any files this project reads or writes. -->

### Stock quote CSV (`stock-quote` stdout)

One header row followed by one data row:

| Column | Type | Description |
|---|---|---|
| `ticker` | string | Uppercased ticker symbol |
| `price` | float | Last traded price |
| `timestamp` | string | ISO 8601 UTC timestamp of the fetch |
| `volume` | int | Last traded volume |
| `provider` | string | Which provider supplied this quote — `"yahoo"` or `"ibkr"`, matching `--provider`'s value (each provider self-reports its own name, so this can't drift from the flag). |
| `delayed` | bool | `True` if the provider could only supply delayed (not real-time) data. Always `False` for `--provider yahoo`. For `--provider ibkr`, reflects what `IBKRQuote` actually got back (not which code path ran) — `True` whenever the account isn't entitled to live data for that ticker and it fell back to IBKR's free delayed tier (~15-20 minutes). |

### Mock Yahoo Finance fixture (`tests/data/yahoo_finance_quotes.json`)

Read by `tests.mocks.yahoo_finance.MockYahooFinance` (test-only). A JSON object keyed by uppercased
ticker symbol:

```json
{
  "AAPL": { "price": 150.25, "volume": 1000000 }
}
```

`timestamp` isn't stored in the fixture — the mock generates it at fetch time, same as the real
`YahooFinance` implementation.

### Day-chart CSV (`<TICKER>_<DATE>_data.csv`, or `<TICKER>_<START>_<END>_data.csv` for a range)

One header row followed by one data row per 1-minute bar. For a `--start-date`/`--end-date` range,
every charted day's bars are concatenated into this single file, in chronological order (`timestamp`
disambiguates which day a row belongs to; no separate `date` column is added):

| Column | Type | Description |
|---|---|---|
| `timestamp` | string | ISO 8601 UTC |
| `open` | float | |
| `high` | float | |
| `low` | float | |
| `close` | float | |
| `volume` | int | |
| `session` | string | `"pre-market"`, `"regular"`, or `"after-market"` |
| `incomplete` | bool | `True` if quant-data's provider couldn't supply full data for this bar (e.g. no pre/after-market volume), or if a per-provider quality check flagged the value implausible (`DataQuality.REJECTED`, collapsed into the same `True` here — see the rejected-whistleblower-bar note above for where that distinction is actually surfaced). Always `False` for `--provider ibkr`/`databento` — neither `IBKRIntraDay` nor `DatabentoIntraDay` has an equivalent flag, and a zero-volume bar from either is presumed genuinely no trades that minute, not missing data. |

### Day-chart popup window

No longer written to disk — `day-chart` displays it as an interactive matplotlib window instead
(`day_chart.chart.show_chart`, `TkAgg` backend, non-blocking `plt.show()` gated by polling the GUI
event loop until the window's own close event fires). One day: a figure with two vertically stacked subplots sharing an
x-axis (rendered in US/Eastern time): price (line) on top (3/4 of the figure height), volume (bar)
below (1/4). A `--start-date`/`--end-date` range: the same two-subplot layout repeated once per
charted day, stacked horizontally left-to-right in chronological order with a small gap between
days (each day keeping its own independent midnight-to-midnight x-axis — days are *not* a shared
timeline), a shared ticker title above the whole figure, and each day's own date as that panel's
title. Only the leftmost day's panels are y-axis labeled ("Price"/"Volume"), to avoid repeating
labels across every panel. Each subplot shades its background by session (pre-market / regular /
after-market) using `axvspan`. Doesn't currently render `incomplete` visually — that information is
only in the CSV/`DayBar` data for now. For `--provider quant-data`, each price panel also draws a
candlestick per disputed bar that falls on that panel's day (see the CLI section above): one red
candlestick using the whistleblower provider's own OHLC values, plus one blue candlestick per
candidate provider using that candidate's own OHLC values — each candle plots its provider's real
numbers directly, not a derived/combined value. The whistleblower candle sits at the bar's actual
timestamp; candidate candles are offset slightly to its right so multiple candidates (rare today,
but possible) stay visually distinct rather than fully overlapping. Also one orange candlestick per
rejected-whistleblower bar that falls on that panel's day, offset slightly right of its own real
timestamp the same way a candidate candle is — currently always zero of these in practice, since no
real data sets the underlying quality flag yet (see the CLI section above).

### Mock intraday bars fixture (`tests/data/quant_data_bars.json`)

Read by `tests.mocks.quant_data.MockQuantDataIntraDay` (test-only). A JSON object keyed by
uppercased ticker symbol, then by `YYYY-MM-DD` session date, to a list of raw bars:

```json
{
  "SPY": {
    "2026-01-02": [
      { "timestamp": "2026-01-02T09:00:00+00:00", "open": 470.0, "high": 470.5, "low": 469.8, "close": 470.2, "volume": 0, "incomplete": true }
    ]
  }
}
```

`session` isn't stored in the fixture — the mock infers it from `timestamp` via
`shared.sessions.infer_session`, same as the real `QuantDataIntraDay` implementation.
`incomplete` defaults to `false` if omitted from a fixture entry.
