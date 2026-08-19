from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from time import perf_counter

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from defs.protocols import BarConflict, DayBar, ProviderBar, QuoteBar  # noqa: E402
from shared.diagnostics import CATEGORY_PERF_UI, Logger  # noqa: E402
from shared.errors import AppError  # noqa: E402
from shared.sessions import AFTER_MARKET, EASTERN, PRE_MARKET, REGULAR  # noqa: E402
from shared.settings import Settings  # noqa: E402

_SESSION_COLORS = {
    PRE_MARKET: "#fde68a",
    REGULAR: "#ffffff",
    AFTER_MARKET: "#c7d2fe",
}
_DEFAULT_SESSION_COLOR = "#ffffff"

_INTERACTIVE_BACKEND = "TkAgg"
_FIGURE_DPI = 100
_DAY_PADDING_PX = 5
_EVENT_LOOP_POLL_SECONDS = 0.1
_RESIZE_DEBOUNCE_MS = 200

_MAIN_CANDLE_COLOR = "black"
_MAIN_CANDLE_GID = "main-candle-body"
_WHISTLEBLOWER_COLOR = "#dc2626"
_CANDIDATE_COLOR = "#2563eb"
_REJECTED_COLOR = "#f59e0b"
_CANDLE_WIDTH_DAYS = 0.6 / (24 * 60)  # narrower than a full minute, leaves a visible gap
_CONFLICT_CANDLE_GID = "conflict-candle-body"
_REJECTED_CANDLE_GID = "rejected-candle-body"
_CANDLE_OFFSET_DAYS = 1.2 / (24 * 60)  # spacing between a whistleblower candle and each candidate
# A conflict's whistleblower minute is never resolved into fact_market_data_1min (it's stuck
# pending), so there's no real black candle at that timestamp for a >1-minute-offset candidate to
# collide with. A rejected-whistleblower bar's minute is different: it *did* auto-resolve, so a
# real black candle already sits at that exact timestamp -- reusing _CANDLE_OFFSET_DAYS (1.2min,
# more than a full minute) visually dragged the rejected candle onto the *next* minute's slot
# instead of its own (looked like an off-by-one shift against a real run of consecutive rejected
# bars). Sub-minute so it stays paired with its own minute's candle instead.
_REJECTED_OFFSET_DAYS = _CANDLE_WIDTH_DAYS

# One day's worth of chart input: its session date plus that day's bars.
DayChartData = tuple[date, list[DayBar]]


def _load_saved_window_position() -> tuple[int, int] | None:
    # Best-effort: a saved position is a hint, never something the popup should fail over. Reads
    # directly via Settings rather than accepting it as a show_chart parameter -- day-chart has no
    # CLI flag for this, so there's nothing for cli.py to thread through.
    try:
        settings = Settings.load()
    except Exception as error:
        Logger.warning(f"day-chart: could not load settings for window position, using default: {error}")
        return None

    if settings.window is None:
        return None
    return (settings.window.x, settings.window.y)


def _save_window_position(x: int, y: int) -> None:
    try:
        Settings.save_window_position(x, y)
    except Exception as error:
        Logger.warning(f"day-chart: could not save window position {x},{y}: {error}")


def _get_virtual_desktop_bounds(window) -> tuple[int, int, int, int]:
    # tkinter's winfo_screenwidth()/winfo_screenheight() only report the *primary* monitor's
    # resolution on Windows, not the full virtual desktop spanning every monitor -- which can also
    # have a negative origin, for a monitor positioned left of or above the primary. A saved
    # position on a secondary monitor would otherwise look "off-screen" and get discarded even
    # though it's perfectly valid. GetSystemMetrics is the only way to get the real bounds.
    if sys.platform == "win32":
        try:
            import ctypes

            sm_xvirtualscreen = 76
            sm_yvirtualscreen = 77
            sm_cxvirtualscreen = 78
            sm_cyvirtualscreen = 79
            user32 = ctypes.windll.user32
            min_x = user32.GetSystemMetrics(sm_xvirtualscreen)
            min_y = user32.GetSystemMetrics(sm_yvirtualscreen)
            width = user32.GetSystemMetrics(sm_cxvirtualscreen)
            height = user32.GetSystemMetrics(sm_cyvirtualscreen)
            return (min_x, min_y, min_x + width, min_y + height)
        except Exception:
            pass

    return (0, 0, window.winfo_screenwidth(), window.winfo_screenheight())


def show_chart(
    ticker: str,
    days: list[DayChartData],
    conflicts: list[BarConflict] | None = None,
    rejected_bars: list[ProviderBar] | None = None,
    quote_bars: list[QuoteBar] | None = None,
) -> None:
    switch_start = perf_counter()
    plt.switch_backend(_INTERACTIVE_BACKEND)
    Logger.perf(f"switched to {_INTERACTIVE_BACKEND} backend", perf_counter() - switch_start)

    figure = render_chart(ticker, days, conflicts, rejected_bars, quote_bars)
    # None for any backend without a real GUI window (e.g. Agg, used in tests) -- window
    # positioning is a TkAgg-specific nicety, not something every backend needs to support.
    window = getattr(figure.canvas.manager, "window", None)
    last_known_position: tuple[int, int] | None = None

    if window is not None:
        saved_position = _load_saved_window_position()
        if saved_position is not None:
            saved_x, saved_y = saved_position
            min_x, min_y, max_x, max_y = _get_virtual_desktop_bounds(window)
            if min_x <= saved_x < max_x and min_y <= saved_y < max_y:
                window.geometry(f"+{saved_x}+{saved_y}")
            else:
                Logger.warning(
                    f"day-chart: saved window position {saved_x},{saved_y} is outside the virtual desktop ({min_x},{min_y})-({max_x},{max_y}), using default"
                )

        def _track_position(_event=None) -> None:
            # close_event fires in response to the widget's own <Destroy> event -- by then the
            # window is already mid-teardown and winfo_x()/winfo_y() raise. Track the position
            # live on every move/resize instead of querying it once the window is already gone.
            nonlocal last_known_position
            try:
                last_known_position = (window.winfo_x(), window.winfo_y())
            except Exception:
                pass

        window.bind("<Configure>", _track_position)
        _track_position()

    closed = False

    def _on_close(_event) -> None:
        nonlocal closed
        closed = True

    def _on_resize(event) -> None:
        Logger.info(f"resize_event: canvas now {event.width}x{event.height}px", category=CATEGORY_PERF_UI)

    original_draw = figure.canvas.draw

    def _timed_draw(*args, **kwargs):
        draw_start = perf_counter()
        result = original_draw(*args, **kwargs)
        Logger.perf("canvas.draw()", perf_counter() - draw_start, category=CATEGORY_PERF_UI)
        return result

    figure.canvas.mpl_connect("close_event", _on_close)
    figure.canvas.mpl_connect("resize_event", _on_resize)
    # Wrapping draw() (rather than only relying on the draw_event callback) times the actual
    # rendering work itself, whatever triggers it -- a resize, a poll-forced redraw, anything --
    # instead of just marking that a draw happened at some point.
    figure.canvas.draw = _timed_draw

    tk_canvas = getattr(figure.canvas, "_tkcanvas", None)
    if tk_canvas is not None:
        # Debounce redraws: a live resize drag fires several intermediate resize_events in quick
        # succession (Windows streams WM_SIZE messages throughout the drag), and matplotlib's own
        # draw_idle() dedup (skip if a draw is already scheduled) doesn't help when each draw takes
        # several seconds -- by the time one draw finishes, the *next* queued resize event triggers
        # another one from scratch, instead of the dedup ever getting a chance to collapse them.
        # Measured 2-3 full redraws (~5-8s each) per single drag gesture before this. Cancelling and
        # rescheduling on every draw_idle() call means the real (slow) draw only fires once resizing
        # has actually settled, cutting that down to exactly one.
        original_draw_idle = figure.canvas.draw_idle
        pending_draw_id: list[str | None] = [None]

        def _debounced_draw_idle(*args, **kwargs):
            if pending_draw_id[0] is not None:
                tk_canvas.after_cancel(pending_draw_id[0])

            def _fire_draw_idle():
                pending_draw_id[0] = None
                original_draw_idle()

            pending_draw_id[0] = tk_canvas.after(_RESIZE_DEBOUNCE_MS, _fire_draw_idle)

        figure.canvas.draw_idle = _debounced_draw_idle

    # plt.show()'s own blocking mainloop doesn't reliably block when launched under the VS Code
    # debugger (debugpy) -- the popup closed instantly. Polling the event loop ourselves via a
    # close_event callback works the same way regardless of that environment.
    #
    # Deliberately calling figure.canvas.start_event_loop() directly instead of plt.pause(): pyplot's
    # own pause() calls show(block=False) on every single invocation, and for TkAgg,
    # FigureManagerTk.show() unconditionally calls canvas.draw_idle() once the window has been shown
    # once -- not gated by figure.stale at all. That forces a full redraw of the whole figure on
    # every poll tick regardless of whether anything changed, measured at ~1-1.5s/poll for a 6-day
    # chart (vs the ~0.1s requested) -- 10-27x slower, and the actual cause of the popup feeling
    # "painfully sluggish". Calling start_event_loop() directly still pumps Tk's event loop (so
    # close_event/resize/etc. still fire) without plt.pause()'s forced redraw.
    plt.show(block=False)
    wait_start = perf_counter()
    poll_count = 0
    while not closed:
        poll_start = perf_counter()
        figure.canvas.start_event_loop(_EVENT_LOOP_POLL_SECONDS)
        poll_count += 1
        Logger.perf(f"event-loop poll {poll_count}", perf_counter() - poll_start, category=CATEGORY_PERF_UI)
    wait_elapsed = perf_counter() - wait_start
    poll_seconds = wait_elapsed / poll_count if poll_count else 0.0
    Logger.perf(
        f"popup open ({poll_count} event-loop polls, {poll_seconds:.4f}s/poll avg vs {_EVENT_LOOP_POLL_SECONDS}s requested)",
        wait_elapsed,
    )

    if last_known_position is not None:
        last_x, last_y = last_known_position
        _save_window_position(last_x, last_y)

    plt.close(figure)


def render_chart(
    ticker: str,
    days: list[DayChartData],
    conflicts: list[BarConflict] | None = None,
    rejected_bars: list[ProviderBar] | None = None,
    quote_bars: list[QuoteBar] | None = None,
) -> Figure:
    if not days:
        raise AppError(f"Cannot render chart for '{ticker}': no days provided.")

    active_conflicts = [] if conflicts is None else conflicts
    active_rejected_bars = [] if rejected_bars is None else rejected_bars
    # A third row (bid/ask) only appears when quote_bars is actually supplied -- None means "this
    # provider has no such data" (every non-IBKR path), so the grid stays 2 rows exactly as before.
    show_bid_ask_row = quote_bars is not None
    active_quote_bars = [] if quote_bars is None else quote_bars
    render_start = perf_counter()

    row_count = 3 if show_bid_ask_row else 2
    height_ratios = [3, 1, 1] if show_bid_ask_row else [3, 1]

    figure, axes = plt.subplots(
        row_count,
        len(days),
        sharex="col",
        squeeze=False,
        figsize=(max(12, 5 * len(days)), 8),
        dpi=_FIGURE_DPI,
        gridspec_kw={"height_ratios": height_ratios},
        layout="constrained",
    )
    figure.get_layout_engine().set(w_pad=_DAY_PADDING_PX / _FIGURE_DPI, wspace=0)
    figure.suptitle(ticker)

    for column_index, (session_date, bars) in enumerate(days):
        price_axis = axes[0, column_index]
        volume_axis = axes[1, column_index]
        bid_ask_axis = axes[2, column_index] if show_bid_ask_row else None

        timestamps_et: list[datetime] = []
        volumes: list[int] = []
        sessions: list[str] = []
        for bar in bars:
            timestamp_et = bar.timestamp.astimezone(EASTERN)
            timestamps_et.append(timestamp_et)
            volumes.append(bar.volume)
            sessions.append(bar.session)
            _draw_candlestick(price_axis, timestamp_et, bar, _MAIN_CANDLE_COLOR, _MAIN_CANDLE_GID)

        price_axis.set_title(session_date.isoformat())

        volume_axis.bar(timestamps_et, volumes, color="#1f2937", width=1 / (24 * 60))
        volume_axis.set_xlabel("Time (ET)")

        if column_index == 0:
            price_axis.set_ylabel("Price")
            volume_axis.set_ylabel("Volume")

        _shade_sessions(price_axis, timestamps_et, sessions)
        _shade_sessions(volume_axis, timestamps_et, sessions)

        for conflict in active_conflicts:
            conflict_timestamp_et = conflict.whistleblower.bar.timestamp.astimezone(EASTERN)
            if conflict_timestamp_et.date() == session_date:
                _draw_conflict(price_axis, conflict, conflict_timestamp_et)

        for rejected_bar in active_rejected_bars:
            rejected_timestamp_et = rejected_bar.bar.timestamp.astimezone(EASTERN)
            if rejected_timestamp_et.date() == session_date:
                _draw_rejected_bar(price_axis, rejected_bar, rejected_timestamp_et)

        session_start = datetime.combine(session_date, time.min, tzinfo=EASTERN)
        session_end = session_start + timedelta(days=1)
        volume_axis.set_xlim(session_start, session_end)
        volume_axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=EASTERN))

        if bid_ask_axis is not None:
            _draw_bid_ask(bid_ask_axis, active_quote_bars, session_date)
            bid_ask_axis.set_xlabel("Time (ET)")
            if column_index == 0:
                bid_ask_axis.set_ylabel("Bid/Ask")

    figure.autofmt_xdate()
    Logger.perf(f"rendered {len(days)} day(s)", perf_counter() - render_start)
    return figure


def _draw_bid_ask(axis, quote_bars: list[QuoteBar], session_date: date) -> None:
    # Only plots minutes where the BID_ASK call actually returned a bar (avg_bid/avg_ask
    # non-None) -- unlike the CSV's left join against DayBar timestamps, the chart doesn't need a
    # point for every OHLCV minute, just the ones with real bid/ask data.
    timestamps_et: list[datetime] = []
    avg_bids: list[float] = []
    avg_asks: list[float] = []
    for quote_bar in quote_bars:
        if quote_bar.avg_bid is None or quote_bar.avg_ask is None:
            continue
        timestamp_et = quote_bar.timestamp.astimezone(EASTERN)
        if timestamp_et.date() != session_date:
            continue
        timestamps_et.append(timestamp_et)
        avg_bids.append(quote_bar.avg_bid)
        avg_asks.append(quote_bar.avg_ask)

    axis.plot(timestamps_et, avg_bids, color=_CANDIDATE_COLOR, linewidth=1, label="avg bid")
    axis.plot(timestamps_et, avg_asks, color=_WHISTLEBLOWER_COLOR, linewidth=1, label="avg ask")
    if timestamps_et:
        axis.legend(loc="upper left", fontsize="x-small")


def _draw_conflict(axis, conflict: BarConflict, timestamp_et: datetime) -> None:
    # Whistleblower candle sits at the conflict's real timestamp (lines it up with the existing
    # price line); candidate candles fan out to its right, offset per candidate so multiple
    # candidates (possible, even if today's data is always exactly one) stay visually distinct
    # rather than fully overlapping.
    _draw_candlestick(axis, timestamp_et, conflict.whistleblower.bar, _WHISTLEBLOWER_COLOR, _CONFLICT_CANDLE_GID)
    for candidate_index, candidate in enumerate(conflict.candidates):
        offset = timedelta(days=_CANDLE_OFFSET_DAYS * (candidate_index + 1))
        _draw_candlestick(axis, timestamp_et + offset, candidate.bar, _CANDIDATE_COLOR, _CONFLICT_CANDLE_GID)


def _draw_rejected_bar(axis, rejected_bar: ProviderBar, timestamp_et: datetime) -> None:
    # A rejected-whistleblower bar (quant-data#32) isn't part of a whistleblower/candidate dispute
    # -- it already auto-resolved via Tier 1 and never became pending, so there's no "other side"
    # to fan out here the way _draw_conflict does. One offset candle is enough to keep it visually
    # distinct from the main (black) candle at the same timestamp. Uses _REJECTED_OFFSET_DAYS, not
    # _CANDLE_OFFSET_DAYS -- see that constant's own comment for why conflicts and rejected bars
    # need different-sized offsets.
    offset = timedelta(days=_REJECTED_OFFSET_DAYS)
    _draw_candlestick(axis, timestamp_et + offset, rejected_bar.bar, _REJECTED_COLOR, _REJECTED_CANDLE_GID)


def _draw_candlestick(axis, timestamp_et: datetime, bar: DayBar, color: str, gid: str) -> None:
    axis.plot([timestamp_et, timestamp_et], [bar.low, bar.high], color=color, linewidth=1, zorder=3)

    body_bottom = min(bar.open, bar.close)
    body_height = abs(bar.close - bar.open)
    if body_height == 0:
        # A doji-like bar (open == close) would otherwise draw an invisible zero-height body --
        # give it a thin sliver so the candle stays visible.
        body_height = max((bar.high - bar.low) * 0.01, 0.01)

    body = Rectangle(
        (mdates.date2num(timestamp_et) - _CANDLE_WIDTH_DAYS / 2, body_bottom),
        _CANDLE_WIDTH_DAYS,
        body_height,
        color=color,
        zorder=3,
        # axvspan (session shading) is itself implemented with Rectangle patches, so a plain
        # isinstance(patch, Rectangle) check can't tell them apart -- gid tags this one as ours,
        # and distinguishes a main-chart candle from a conflict candle for the same reason.
        gid=gid,
    )
    axis.add_patch(body)


def _shade_sessions(axis, timestamps_et: list[datetime], sessions: list[str]) -> None:
    region_start_index = 0
    for index in range(1, len(sessions)):
        if sessions[index] != sessions[region_start_index]:
            axis.axvspan(
                timestamps_et[region_start_index],
                timestamps_et[index],
                color=_SESSION_COLORS.get(sessions[region_start_index], _DEFAULT_SESSION_COLOR),
                alpha=0.2,
            )
            region_start_index = index

    axis.axvspan(
        timestamps_et[region_start_index],
        timestamps_et[-1],
        color=_SESSION_COLORS.get(sessions[region_start_index], _DEFAULT_SESSION_COLOR),
        alpha=0.2,
    )
