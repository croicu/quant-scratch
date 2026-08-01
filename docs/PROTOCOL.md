# PROTOCOL.md

CLI signature and file format schemas for `quant-scratch`.

## CLI

<!-- Command name, arguments, flags, exit codes. -->

### `stock-quote`

- Usage: `stock-quote TICKER [--debug]`
- Fetches the current quote for a single ticker (case-insensitive) via yfinance and prints it as
  CSV to stdout.
- `--debug` overrides `settings.json`'s `debug` flag; on a fetch failure with debug on, the
  underlying `AppError` is re-raised instead of being caught and printed.
- Exit codes: `0` success, `1` invalid ticker / network error, `2` argument parsing error
  (argparse's default behavior on missing/bad args).

### `day-chart`

- Usage: `day-chart TICKER [--date YYYY-MM-DD | --start-date YYYY-MM-DD --end-date YYYY-MM-DD] [--debug]`
- Fetches full-day (pre-market + regular + after-market) 1-minute OHLCV bars for a single ticker
  (case-insensitive) from the [quant-data](https://github.com/croicu/quant-data) warehouse (not
  live from yfinance — see `docs/ARCHITECTURE.md`), pops up an interactive matplotlib chart window
  (one day, or several days' charts stacked horizontally — see below), and writes a CSV export to
  the current working directory. The command doesn't exit until you close the popup window; this is
  driven by polling the GUI event loop for the window's own close event, not `plt.show()`'s own
  blocking (which doesn't reliably block under a debugger).
- Requires a `postgres` section in `settings.json` (see `docs/PROTOCOL.md`'s settings note below
  and quant-data's own `docs/DATABASE.md` for connecting to the box) — missing it is an `AppError`
  (exit `1`), same as any other fetch failure.
- `--date YYYY-MM-DD`: single session date to fetch. Omit (and omit `--start-date`/`--end-date`) to
  default to today, or the last trading day (Friday) if today falls on a weekend. Rejected (exit
  `1`) if the date is malformed, in the future, or falls on a weekend. NYSE holidays are not
  validated explicitly, and quant-data may simply not have data loaded for the requested
  ticker/date yet — both surface as the same generic "no data available" error. **Ignored if either
  `--start-date` or `--end-date` is given.**
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
- `--debug` overrides `settings.json`'s `debug` flag; on failure with debug on, the underlying
  `AppError` is re-raised instead of being caught and printed.
- Exit codes: `0` success, `1` invalid ticker / invalid date(s) / no data available (for any day, in
  single-day mode; for every day, in range mode) / missing `postgres` settings / connection error,
  `2` argument parsing error (argparse's default behavior on missing/bad args).
- On success, prints the written CSV path to stdout (after you press Enter to close the popup).

### Settings: `postgres` section (`settings.json` / `settings.local.json`)

Required by `day-chart` (see above). `host`/`port`/`user`/`password`/`dbname` aren't secret for a
client connecting through an already-established local SSH tunnel, so that much can live in the
committed `settings.json`:

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
| `incomplete` | bool | `True` if quant-data's provider couldn't supply full data for this bar (e.g. no pre/after-market volume) |

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
only in the CSV/`DayBar` data for now.

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
