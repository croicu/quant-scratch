# ARCHITECTURE.md

Modules, data flow, and contracts for `quant-scratch`.

## Modules

<!-- One entry per module under src/<package>/: what it owns, what it depends on. -->

### `defs` — repo-wide specification, no implementation

Pure interfaces and data contracts, owned by no single implementation package. `shared` provides
one (default) implementation of what's declared here; a CLI tool could in principle bring its own
alternative implementation instead, depending only on `defs`. Also the intended home for other
future cross-cutting non-implementation declarations (constants, etc.) — hence the general name
rather than something provider-specific.

- `protocols.py` — pure data: `StockQuote` (`ticker`, `price`, `timestamp`, `volume`);
  `DayBar` (`timestamp: datetime` UTC-aware, `open`, `high`, `low`, `close`, `volume`, `session: str`,
  `incomplete: bool` defaulting `False`). `DayBar.timestamp` is a `datetime` rather than a `str`
  like `StockQuote.timestamp` — an intentional divergence, since bar data needs real datetime
  arithmetic (session inference, sorting, ET conversion for the chart x-axis) that a string would
  just force back into a parsed datetime anyway. `incomplete` mirrors
  [quant-data](https://github.com/croicu/quant-data)'s `OHLCV.incomplete` field one-for-one — set
  when the warehouse's provider couldn't supply full data for that bar (in practice, almost every
  pre/after-market bar, since quant-data's own ingest still pulls from Yahoo Finance and inherits
  its zero-volume gap outside regular hours).
- `contracts.py` — behavioral interfaces: `YahooFinanceProvider(Protocol)` — `fetch_quote(ticker) -> StockQuote`;
  `IntraDayProvider(Protocol)` — `fetch_bars(ticker, target_date) -> list[DayBar]`

### `shared` — shared framework + default implementations

Every experiment package depends on this one for bootstrap; it owns no experiment-specific logic
and has no CLI/console script of its own.

- `diagnostics.py` — `Logger`, log sinks (`ConsoleLogSink`), telemetry levels/records. Defines
  `CATEGORY_GENERAL` (the default), `CATEGORY_PERF` ("perf"), and `CATEGORY_PERF_UI` ("perf_ui") —
  the latter two centralized here (rather than as a per-file constant like `quant_data.py`'s
  `CATEGORY_INTRADAY_FETCH` or `day_chart/cli.py`'s `CATEGORY_DATE_RANGE`) specifically so timing
  markers scattered across multiple packages can be toggled together with one `settings.json`
  `logCategories` entry (plus a `logLevel` of `"info"` or lower, since `Logger.info` is filtered by
  level too) rather than one category per module. `CATEGORY_PERF_UI` is split out from
  `CATEGORY_PERF` specifically because it's much higher-volume (one line per ~100ms event-loop poll
  while a popup is open) and only useful when actively diagnosing UI responsiveness (resize
  lag, redraw cost) — a flat sibling category for now, not a true hierarchical `perf/ui`
  subcategory, since `logCategories` has no hierarchy today. `Logger.perf(description,
  elapsed_seconds, category=CATEGORY_PERF)` is the call site for these — a thin wrapper over
  `Logger.info(f"duration: {elapsed_seconds:.3f}s - {description}", category)`, duration-first so
  markers are scannable without reading past the message (`day_chart.chart`'s `perf_counter()`-timed
  markers use it for backend-switch/render/popup-wait duration under `perf`, plus per-poll timing,
  actual `canvas.draw()` duration, and `resize_event` markers under `perf_ui`;
  `shared.providers.quant_data` for connection/query duration under `perf`; `day_chart.cli` for the
  cli-entry-to-settings-loaded/fetch-phase/CSV-write markers under `perf`). `day_chart.cli.main()`
  installs the
  `ConsoleLogSink` immediately after `Settings.load()` succeeds and before constructing
  `QuantDataIntraDay` specifically so that provider's own connection-time marker isn't silently
  swallowed by the default no-op sink that's active before `Logger.set_logger()` runs (which is
  exactly what happened before this ordering fix — the SSH tunnel/DB connection cost was being
  measured but never printed). `Logger` (the class itself, passed uninstantiated — all its public
  methods are `@staticmethod`s) is also injected into quant-data as `logger=Logger` wherever it
  accepts one (`create_postgres_provider`, `MarketData`) — it structurally satisfies quant-data's
  public `quant_data.protocols.LoggingSink` `Protocol` with no adapter code needed, since that
  Protocol was deliberately shaped to mirror this `Logger`'s own method surface
  ([quant-data#20](https://github.com/croicu/quant-data/issues/20)). This is what makes
  `shared.providers.quant_data`'s own perf markers and quant-data's *internal* ones (tunnel
  setup, `psycopg.connect()`, each query) show up interleaved in the same stream — see that
  module's own note below for what this replaced.
- `settings.py` — `Settings.load(path, local_path)` / `Settings.current()`, reads `settings.json` +
  `settings.local.json` by default; `path` is a DI'd parameter (default `./settings.json`) so
  callers/tests can point at a fixture instead. `local_path` defaults to a `settings.local.json`
  *sibling of `path`*, not a fixed repo-root path — resolved that way specifically so a caller/test
  passing a custom `path` (e.g. a fixture settings file) can't accidentally pick up whatever real
  `settings.local.json` happens to sit at the real cwd's repo root; passing `local_path` explicitly
  still overrides this. Also `PostgresSettings` (`host`, `port`, `user`, `password`, `dbname`, plus
  optional `ssh_user`/`ssh_key_path` — both-or-neither, `TaskError` if only one is set) and a
  `Settings.postgres` field, parsed from a `postgres` object under `settings.json`/
  `settings.local.json`'s `settings` key (JSON keys `sshUser`/`sshKeyPath`) — mirrors quant-data's
  own `PostgresSettings` shape exactly, including the optional SSH fields
  ([croicu/quant-data#17](https://github.com/croicu/quant-data/issues/17)). `host`/`port`/`user`/
  `password`/`dbname` aren't secret for a client connecting through an already-authenticated local
  SSH tunnel (`host`/`port` are just the local tunnel endpoint, e.g. `localhost`/`5433`; the
  `quant_reader` role has no password), so that much can live in the committed `settings.json`. The
  real box hostname and `ssh_user`/`ssh_key_path` needed for quant-data's new auto-tunnel path are
  a different matter — those go in `settings.local.json` (gitignored) only, never a committed file
  — see quant-data's `docs/DATABASE.md`'s `<ubuntu_host>`/`<ssh_user>` placeholders. Also
  `WindowSettings` (`x`, `y`) and a `Settings.window` field, parsed the same way from an optional
  `window` object — unlike `postgres`, nothing reads this from the committed `settings.json`;
  `day_chart.chart.show_chart` treats it as a `settings.local.json`-only, auto-managed value (see
  its own note below), not something a user hand-edits. `Settings.save_window_position(x, y,
  local_path=...)` is the write side — reads whatever's currently in `local_path` (if anything),
  replaces just the `window` key, and writes the whole file back, so it never clobbers unrelated
  local overrides living in the same file (e.g. `postgres.sshKeyPath`).
- `errors.py` — `AppError`, `TaskError`, `telemetry_session()`
- `sessions.py` — `infer_session(timestamp_utc) -> str`, classifying a UTC timestamp into
  `"pre-market"` (4:00–9:30 ET), `"regular"` (9:30–16:00 ET), or `"after-market"` (16:00–20:00 ET);
  raises `AppError` for a timestamp outside that range. Lives directly in `shared` (not in
  `day_chart`, despite being introduced for that experiment, and not in `shared/providers/` since
  it isn't itself a provider) because it's needed to construct `DayBar` instances inside
  `shared.providers.quant_data.QuantDataIntraDay` and inside the test mock — putting it in
  `day_chart` would have made `shared` depend on an experiment package, inverting the intended
  dependency direction.
- `providers/` — one module per external data source, each providing a default implementation of
  a `defs.contracts` interface. Separated from the rest of `shared` so multiple providers can sit
  side by side without crowding a single flat file list.
  - `yahoo_finance.py` — `YahooFinance`, the default implementation of
    `defs.contracts.YahooFinanceProvider`; wraps `yfinance`, raises `AppError` on an invalid
    ticker or network failure. Used only by `stock_quote` (a live single-quote lookup) — quant-data
    has no equivalent concept, only historical bars, so this one wasn't replaced.
  - `quant_data.py` — `QuantDataIntraDay`, the default implementation of
    `defs.contracts.IntraDayProvider`. Thin wrapper around
    [quant-data](https://github.com/croicu/quant-data)'s public `MarketData` read client — imports
    only from the `quant_data` top level (`from quant_data import MarketData,
    create_postgres_provider`), per quant-data's own stable-surface contract
    ([quant-data#10](https://github.com/croicu/quant-data/issues/10)/
    [quant-scratch#8](https://github.com/croicu/quant-scratch/issues/8)): builds a provider via
    `create_postgres_provider(host=..., port=..., dbname=..., user=..., password=..., ssh_user=...,
    ssh_key_path=...)` and passes it to `MarketData(provider)` — `MarketData` itself no longer
    takes connection details directly, so it stays agnostic of Postgres specifically (a future
    non-Postgres backend wouldn't need another breaking change here). `ssh_user`/`ssh_key_path`
    default to `None` (today's direct-connect behavior, unchanged); when both are set, quant-data
    opens and manages its own SSH tunnel instead of assuming one's already running externally
    ([croicu/quant-data#17](https://github.com/croicu/quant-data/issues/17)/
    [croicu/quant-scratch#10](https://github.com/croicu/quant-scratch/issues/10)). Also passes
    `logger=Logger` to both calls ([quant-data#20](https://github.com/croicu/quant-data/issues/20))
    so quant-data's own internal timing/connection log lines land in this repo's own `Logger`
    stream. Doesn't wrap `fetch_bars` in its own perf marker — quant-data's `PostgresDatabase`
    already emits one for that identical call via the injected logger, so a second one here would
    just duplicate it. (The connection setup itself briefly regressed to a ~130s stall after
    adopting the auto-tunnel, traced to `psycopg.connect()` being handed the ambiguous hostname
    `"localhost"` instead of a concrete `"127.0.0.1"` — fixed upstream in
    [quant-data#19](https://github.com/croicu/quant-data/issues/19), confirmed back down to ~1.4s.)
    Calls `fetch_bars(ticker, target_date, target_date)` (a
    single-day range) and converts each returned `quant_data.OHLCV` into this repo's own `DayBar`,
    computing `session` via `sessions.infer_session` and carrying `incomplete` straight through.
    Normalizes `OHLCV.timestamp` to UTC-aware before use — it's been observed coming back naive
    despite being documented UTC-aware, which `.astimezone()` (used by both `infer_session` and
    the chart's ET conversion) would otherwise silently misinterpret using the local machine's
    system timezone ([quant-data#8](https://github.com/croicu/quant-data/issues/8), still open —
    keep this normalization until it's fixed upstream). A bar `infer_session` can't classify
    (outside the 4:00-20:00 ET window) fails the whole fetch with an `AppError` — quant-data#9 (a
    write-side bug silently shifting stored timestamps by the ingest session's local timezone) was
    the actual cause of bars showing up outside that window; now that it's fixed and historical
    data backfilled, an out-of-window bar again indicates a real problem worth surfacing loudly,
    not something to skip. Connects using `Settings.postgres`
    (host/port/user/password/dbname/ssh_user/ssh_key_path); raises `AppError` if that section is
    missing, if the connection fails, or if no bars are
    returned at all. Replaced
    `shared.providers.yahoo_finance.YahooFinanceIntraDay` (removed — see
    [croicu/quant-scratch#7](https://github.com/croicu/quant-scratch/issues/7)): quant-data's own
    ingest already pulls from Yahoo Finance and stores the result, so `day-chart` fetching Yahoo
    directly was pure duplication once the warehouse existed. Constructor accepts an injected
    `client` for tests, matching this repo's DI-over-monkeypatching convention for testing
    dependencies on third-party/cross-repo code.

### `stock_quote` — first experiment CLI

Fetches and prints the current quote for a single stock ticker. Depends on `defs` for the
`YahooFinanceProvider` interface and `StockQuote` data type, and on `shared` for the default
`YahooFinance` implementation plus `Settings`/`Logger`/`AppError`. No dependency on `yfinance`
directly — that's confined to `shared/providers/yahoo_finance.py`.

- `output.py` — `quote_to_csv(quote) -> str`
- `cli.py` — `stock-quote` entry point; `main()` takes optional `provider: YahooFinanceProvider` and
  `settings_path: Path` parameters (defaulting to `shared.providers.yahoo_finance.YahooFinance()` and
  `Settings.load()`'s own default path respectively) — simple parameter-based DI, no framework,
  letting tests inject `tests.mocks.yahoo_finance.MockYahooFinance` and a fixture settings file
  instead of monkeypatching or relying on `chdir` for isolation

### `day_chart` — second experiment CLI

Fetches full-day intraday bars for one or more days for a single stock ticker and generates a
price/volume chart plus a CSV export. Depends on `defs` for the `IntraDayProvider` interface and
`DayBar` data type, and on `shared` for the default `QuantDataIntraDay` implementation plus
`Settings`/`Logger`/`AppError`. No dependency on `quant_data` or `matplotlib.pyplot` outside its own
`chart.py`/`shared/providers/` — bar fetching is confined to `shared/providers/quant_data.py`.

- `output.py` — `bars_to_csv(bars) -> str`; columns include `incomplete`
- `chart.py` — `DayChartData = tuple[date, list[DayBar]]` (one day's session date + its bars).
  `render_chart(ticker, days: list[DayChartData]) -> Figure`; pure figure construction, a 2×N grid
  (N = `len(days)`) built via a single `plt.subplots(2, N, sharex="col", squeeze=False,
  dpi=100, gridspec_kw={"height_ratios": [3, 1]}, layout="constrained")` — `sharex="col"` links each
  day's own price/volume pair without linking across days (each day gets its own
  midnight-to-midnight x-axis, since the calendar dates differ), `height_ratios` keeps every day's
  own price:volume split at 3:1, and `layout="constrained"` (rather than `tight_layout()`) avoids a
  `tight_layout`/shared-axes incompatibility warning while still leaving room for
  `figure.suptitle(ticker)` above the whole grid. The small horizontal padding between day panels is
  set explicitly in pixels rather than gridspec's relative `wspace`: `dpi` is pinned to `100` so
  pixels convert predictably to inches, then `figure.get_layout_engine().set(w_pad=5/100, wspace=0)`
  fixes the day-to-day gap at 5px regardless of figure width/day count (leaving `h_pad`/`hspace` —
  the price-to-volume gap within a day — at their constrained-layout defaults, untouched). Each day
  panel gets its own date as a subplot title; only the leftmost column labels its
  y-axes ("Price"/"Volume"), to avoid repeating them across every panel. Each subplot still shades
  by session via `axvspan`. Raises `AppError` for an empty `days` list. Runs under the `Agg` backend
  (module default) so it's headless-safe in tests/CI. Doesn't currently do anything visually
  distinct for `incomplete` bars — carried through the data only for now. `show_chart(ticker, days)`
  is the interactive entry point: switches to the `TkAgg` backend, calls `render_chart`, shows the
  figure non-blocking (`plt.show(block=False)`), registers a `close_event` callback on
  `figure.canvas` that flips a flag, then polls the GUI event loop itself
  (`while not closed: figure.canvas.start_event_loop(0.1)`) until that flag flips — i.e. until the
  user actually closes the popup window — before returning. Doesn't rely on `plt.show()`'s own
  blocking mainloop — that didn't reliably block when launched under the VS Code debugger
  (debugpy), closing the popup instantly; polling the event loop directly works the same way
  regardless of that environment. Deliberately calls `figure.canvas.start_event_loop()` directly
  rather than `plt.pause()`: `pyplot.pause()` calls `show(block=False)` on every single invocation,
  and for TkAgg, `FigureManagerTk.show()` unconditionally calls `canvas.draw_idle()` once the
  window's been shown once — not gated by `figure.stale` — forcing a full redraw of the whole
  figure on every poll tick regardless of whether anything actually changed. For a 6-day chart that
  measured ~1-1.5s per poll (vs the ~0.1s requested) — the real cause of the popup feeling
  "painfully sluggish," isolated with throwaway probe scripts that ruled out the SSH tunnel, Tcl/Tk
  itself (a pure-Tkinter `after()`+`mainloop()` probe stayed within a few ms of the requested
  interval), and `figure.raise_window`'s topmost-attribute toggling before landing on this.
  Bypassing `plt.pause()` still pumps Tk's event loop (so `close_event`/resize/etc. still fire),
  just without the forced redraw — confirmed back down to ~0.1s/poll. Also wraps `figure.canvas.draw`
  itself with a timing marker (`canvas.draw()`, `perf_ui`) — capturing the actual rendering cost
  regardless of what triggered it (a resize, a poll-forced redraw, anything) — logs each individual
  poll's duration (`event-loop poll N`, `perf_ui`) rather than only a final aggregate, and logs a
  `resize_event` marker with the new canvas size (`perf_ui`, no duration — the resize's own cost
  shows up as the `canvas.draw()` marker it triggers). Debounces resize-triggered redraws: wraps
  `figure.canvas.draw_idle` so every call cancels any pending scheduled draw and reschedules one
  `_RESIZE_DEBOUNCE_MS` (200ms) later via `tk_canvas.after`/`after_cancel`, rather than letting
  every intermediate `<Configure>` event during a drag trigger its own full redraw immediately.
  Needed because matplotlib's own `draw_idle()` dedup (skip if a draw's already scheduled) doesn't
  help once each draw takes several seconds — by the time one finishes, the *next* queued resize
  event (Windows streams `WM_SIZE` throughout a drag) triggers another one from scratch instead of
  ever getting collapsed; measured 2-3 full ~5-8s redraws per single drag gesture before this,
  down to exactly one after. Also remembers the popup's screen position across runs: reads
  `Settings.window` (via its own `Settings.load()` call — `show_chart` has no `Settings` parameter,
  since `cli.py` has no CLI flag for this and nothing to thread through) and applies it to the Tk
  window with `.geometry(f"+{x}+{y}")` if it's within `_get_virtual_desktop_bounds()` — silently
  falls back to the OS default position otherwise (a different monitor setup since it was last
  saved, say). `_get_virtual_desktop_bounds()` exists specifically because `winfo_screenwidth`/
  `winfo_screenheight` only report the *primary* monitor's resolution on Windows, not the full
  virtual desktop spanning every monitor (which can have a negative origin, for one positioned
  left of or above the primary) — a saved position on a secondary monitor would otherwise always
  look "off-screen" and get silently discarded. Queries `GetSystemMetrics`
  (`SM_XVIRTUALSCREEN`/`SM_YVIRTUALSCREEN`/`SM_CXVIRTUALSCREEN`/`SM_CYVIRTUALSCREEN`) via `ctypes`
  on `win32`, falling back to `winfo_screenwidth`/`winfo_screenheight` (single-monitor bounds) on
  any other platform or if that query fails for any reason. Tracks the window's position
  live via a `<Configure>` binding on the toplevel window (updated on every move/resize) rather
  than querying it once at close time: `close_event` fires in response to the widget's own
  `<Destroy>` event, so by the time a post-close handler runs the window is already mid-teardown
  and `winfo_x()`/`winfo_y()` raise — the fix isn't "catch that exception," it's "never query a
  dying widget in the first place." Saves the last-tracked position via
  `Settings.save_window_position()` right before closing. Both the read and the write are
  best-effort (broad `except Exception`, logged as a warning, never fatal) and a no-op on any
  backend without a real GUI window (`getattr(figure.canvas.manager, "window", None)` is `None`
  for Agg, used in tests) — this is a nicety, never something the popup should fail over. Kept
  separate from `render_chart` specifically so unit tests can exercise figure construction without
  ever touching a GUI backend.
- `cli.py` — `day-chart` entry point; `main()` takes optional `provider: IntraDayProvider`,
  `settings_path: Path`, `output_dir: Path`, and `show_chart: ShowChartFn` (`Callable[[str,
  list[DayChartData]], None]`) parameters — same parameter-based DI pattern as `stock_quote.cli`
  (tests inject a non-GUI stand-in for `show_chart`, same reason `provider` is injected instead of
  hitting a real database). Unlike `stock_quote`, the default provider can't be constructed before
  settings are loaded (it needs `Settings.postgres` for connection details), so provider
  construction happens *after* `Settings.load()` succeeds: `QuantDataIntraDay(host=settings.postgres.host,
  ...)` if no `provider` was injected, raising `AppError` if `settings.postgres` is absent.
  `output_dir` has no CLI flag (`--output-dir` was deliberately deferred); it exists purely as a
  test seam, the same role `settings_path` plays — it now only affects where the CSV lands, since
  the chart itself is shown in a popup rather than saved. Owns `resolve_session_date(date_argument,
  today)` — resolves the `--date` argument to a concrete session date, defaulting to today or
  rolling back to the prior Friday if today is a weekend, and raising `AppError` for a malformed,
  future, or weekend date — used when neither `--start-date` nor `--end-date` is given. Also owns
  `resolve_date_range(start_date_argument, end_date_argument, today)` — used instead of
  `resolve_session_date` whenever either range flag is given (`--date` is ignored in that case):
  `--end-date` alone defaults its start to the same day (so `--end-date X` alone behaves like
  `--date X`); `--start-date` alone defaults its end to today's `resolve_session_date`-style default;
  both given must satisfy `start <= end` (`AppError` otherwise). Individual range bounds are only
  format/future-validated, *not* weekend-rejected like `resolve_session_date` — a range legitimately
  spans weekends, which `main()` then skips. For each resolved day, `main()` calls
  `provider.fetch_bars` individually; in range mode (2+ days), a per-day `AppError` (weekend,
  holiday, not-yet-ingested) is caught, logged via `Logger.warning` (category `date_range`), and
  that day is dropped from the chart rather than failing the whole command — only if *every* day in
  the range comes back empty does the command fail. In single-day mode, a fetch failure still
  propagates directly as before (unchanged). The CSV export flattens all charted days' bars into one
  file — `<TICKER>_<DATE>_data.csv` for a single day, `<TICKER>_<START>_<END>_data.csv` (the
  requested range's bounds, not just the days that actually had data) for a range.

### Test doubles (`tests/`)

- `tests/mocks/yahoo_finance.py` — `MockYahooFinance`, structurally implements the same
  `fetch_quote(ticker) -> StockQuote` shape as the real provider (no explicit inheritance from the
  `Protocol` — that's the point of structural typing). Reads fixture quotes from
  `tests/data/yahoo_finance_quotes.json`; raises `AppError` for a ticker not in the fixture, same
  contract as the real implementation.
- `tests/mocks/quant_data.py` — `MockQuantDataIntraDay`, the same structural-typing approach for
  `fetch_bars(ticker, target_date) -> list[DayBar]`; reads fixture bars from
  `tests/data/quant_data_bars.json` (each entry carries its own `incomplete` value; defaults
  `False` if omitted) and infers each bar's `session` via `shared.sessions.infer_session`, same as
  the real `QuantDataIntraDay`. Note this mocks quant-scratch's own `IntraDayProvider` shape
  end-to-end (for `day_chart` CLI-level tests) — it's a different, lower-level thing from
  `tests/unit/test_quant_data_provider.py`'s `FakeMarketData`, which mocks quant-data's
  `MarketData` client specifically to unit-test `QuantDataIntraDay`'s own conversion logic.
- `tests/data/settings.json` — fixture settings file, DI'd into `Settings.load(path=...)` via
  `stock_quote.cli.main`'s (and `day_chart.cli.main`'s) `settings_path` parameter, so CLI tests
  don't depend on cwd isolation. Deliberately has no `postgres` section — exercises the "missing
  config" error path; day-chart's happy-path CLI tests inject a `provider` directly instead of
  relying on settings-driven construction (which would require a real database connection, and
  unit tests must run offline).

## Data flow

`stock-quote TICKER` → injected `YahooFinanceProvider.fetch_quote` (real: `shared.providers.yahoo_finance.YahooFinance`,
a `yfinance` network call; test: `tests.mocks.yahoo_finance.MockYahooFinance`, a fixture lookup) →
`StockQuote` → `output.quote_to_csv` → stdout.

`day-chart TICKER [--date ... | --start-date ... --end-date ...]` → `cli.resolve_session_date`
(single day) or `cli.resolve_date_range` (either range flag given) → one `list[date]` → per-date
injected `IntraDayProvider.fetch_bars` (real: `shared.providers.quant_data.QuantDataIntraDay`,
wrapping a `quant_data.MarketData` read against the Postgres warehouse, tagging each bar via
`shared.sessions.infer_session`; test: `tests.mocks.quant_data.MockQuantDataIntraDay`, a fixture
lookup) — in range mode, a per-day `AppError` is logged as a warning and that day dropped rather
than failing the whole command — → `list[DayChartData]` (`(date, list[DayBar])` per charted day) →
both injected `show_chart` (real: `chart.show_chart`, a blocking popup window; test: a non-GUI
stand-in) and, after flattening every charted day's bars into one list, `output.bars_to_csv` (→
`<TICKER>_<DATE>_data.csv` for a single day, `<TICKER>_<START>_<END>_data.csv` for a range; written
to `output_dir`, CWD by default).

## Contracts

<!-- protocols.py: persisted/shared data contracts (pure data).
     contracts.py: runtime behavioral interfaces (Protocol classes). -->

`protocols.py`/`contracts.py` live in the repo-wide `defs` package (see Modules above), not inside
any single implementation package — they're the specification every provider (real or mock)
conforms to, independent of which one is wired in.

- `defs.protocols.StockQuote` — pure data, no behavior; the CSV formatting in `stock_quote/output.py`
  operates on it rather than living on the dataclass itself.
- `defs.contracts.YahooFinanceProvider` — behavioral interface implemented by both
  `shared.providers.yahoo_finance.YahooFinance` (production) and `tests.mocks.yahoo_finance.MockYahooFinance` (tests).
- `defs.protocols.DayBar` — pure data, no behavior; the CSV formatting in `day_chart/output.py` and
  the chart rendering in `day_chart/chart.py` both operate on it rather than living on the
  dataclass itself.
- `defs.contracts.IntraDayProvider` — behavioral interface implemented by both
  `shared.providers.quant_data.QuantDataIntraDay` (production) and
  `tests.mocks.quant_data.MockQuantDataIntraDay` (tests).
