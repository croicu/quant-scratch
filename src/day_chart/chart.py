from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from time import perf_counter

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from defs.protocols import DayBar  # noqa: E402
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


def show_chart(ticker: str, days: list[DayChartData]) -> None:
    switch_start = perf_counter()
    plt.switch_backend(_INTERACTIVE_BACKEND)
    Logger.perf(f"switched to {_INTERACTIVE_BACKEND} backend", perf_counter() - switch_start)

    figure = render_chart(ticker, days)
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


def render_chart(ticker: str, days: list[DayChartData]) -> Figure:
    if not days:
        raise AppError(f"Cannot render chart for '{ticker}': no days provided.")

    render_start = perf_counter()

    figure, axes = plt.subplots(
        2,
        len(days),
        sharex="col",
        squeeze=False,
        figsize=(max(12, 5 * len(days)), 8),
        dpi=_FIGURE_DPI,
        gridspec_kw={"height_ratios": [3, 1]},
        layout="constrained",
    )
    figure.get_layout_engine().set(w_pad=_DAY_PADDING_PX / _FIGURE_DPI, wspace=0)
    figure.suptitle(ticker)

    for column_index, (session_date, bars) in enumerate(days):
        price_axis = axes[0, column_index]
        volume_axis = axes[1, column_index]

        timestamps_et: list[datetime] = []
        closes: list[float] = []
        volumes: list[int] = []
        sessions: list[str] = []
        for bar in bars:
            timestamps_et.append(bar.timestamp.astimezone(EASTERN))
            closes.append(bar.close)
            volumes.append(bar.volume)
            sessions.append(bar.session)

        price_axis.plot(timestamps_et, closes, color="#1f2937", linewidth=1)
        price_axis.set_title(session_date.isoformat())

        volume_axis.bar(timestamps_et, volumes, color="#1f2937", width=1 / (24 * 60))
        volume_axis.set_xlabel("Time (ET)")

        if column_index == 0:
            price_axis.set_ylabel("Price")
            volume_axis.set_ylabel("Volume")

        _shade_sessions(price_axis, timestamps_et, sessions)
        _shade_sessions(volume_axis, timestamps_et, sessions)

        session_start = datetime.combine(session_date, time.min, tzinfo=EASTERN)
        session_end = session_start + timedelta(days=1)
        volume_axis.set_xlim(session_start, session_end)
        volume_axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=EASTERN))

    figure.autofmt_xdate()
    Logger.perf(f"rendered {len(days)} day(s)", perf_counter() - render_start)
    return figure


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
