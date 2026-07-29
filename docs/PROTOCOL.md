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

- Usage: `day-chart TICKER [--date YYYY-MM-DD] [--debug]`
- Fetches full-day (pre-market + regular + after-market) 1-minute OHLCV bars for a single ticker
  (case-insensitive) from the [quant-data](https://github.com/croicu/quant-data) warehouse (not
  live from yfinance — see `docs/ARCHITECTURE.md`), pops up an interactive matplotlib chart window,
  and writes a CSV export to the current working directory. The popup stays open until you press
  Enter in the terminal — that's a deliberate keypress gate, not `plt.show()`'s own blocking (which
  doesn't reliably block under a debugger).
- Requires a `postgres` section in `settings.json` (see `docs/PROTOCOL.md`'s settings note below
  and quant-data's own `docs/DATABASE.md` for connecting to the box) — missing it is an `AppError`
  (exit `1`), same as any other fetch failure.
- `--date YYYY-MM-DD`: session date to fetch. Omit to default to today, or the last trading day
  (Friday) if today falls on a weekend. Rejected (exit `1`) if the date is malformed, in the
  future, or falls on a weekend. NYSE holidays are not validated explicitly, and quant-data may
  simply not have data loaded for the requested ticker/date yet — both surface as the same generic
  "no data available" error.
- `--debug` overrides `settings.json`'s `debug` flag; on failure with debug on, the underlying
  `AppError` is re-raised instead of being caught and printed.
- Exit codes: `0` success, `1` invalid ticker / invalid date / no data available / missing
  `postgres` settings / connection error, `2` argument parsing error (argparse's default behavior
  on missing/bad args).
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

### Day-chart CSV (`<TICKER>_<DATE>_data.csv`)

One header row followed by one data row per 1-minute bar:

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
(`day_chart.chart.show_chart`, `TkAgg` backend, non-blocking `plt.show()` gated by an `input()`
keypress prompt in the terminal). A figure with two vertically
stacked subplots sharing an x-axis (rendered in US/Eastern time): price (line) on top, volume (bar)
below. Each subplot shades its background by session (pre-market / regular / after-market) using
`axvspan`. Doesn't currently render `incomplete` visually — that information is only in the
CSV/`DayBar` data for now.

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
