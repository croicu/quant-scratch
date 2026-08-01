from __future__ import annotations

from datetime import date, datetime, time, timedelta

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from defs.protocols import DayBar  # noqa: E402
from shared.errors import AppError  # noqa: E402
from shared.sessions import AFTER_MARKET, EASTERN, PRE_MARKET, REGULAR  # noqa: E402

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

# One day's worth of chart input: its session date plus that day's bars.
DayChartData = tuple[date, list[DayBar]]


def show_chart(ticker: str, days: list[DayChartData]) -> None:
    plt.switch_backend(_INTERACTIVE_BACKEND)
    figure = render_chart(ticker, days)

    closed = False

    def _on_close(_event) -> None:
        nonlocal closed
        closed = True

    figure.canvas.mpl_connect("close_event", _on_close)

    # plt.show()'s own blocking mainloop doesn't reliably block when launched under the VS Code
    # debugger (debugpy) -- the popup closed instantly. Polling the event loop ourselves via
    # plt.pause() and a close_event callback works the same way regardless of that environment.
    plt.show(block=False)
    while not closed:
        plt.pause(_EVENT_LOOP_POLL_SECONDS)
    plt.close(figure)


def render_chart(ticker: str, days: list[DayChartData]) -> Figure:
    if not days:
        raise AppError(f"Cannot render chart for '{ticker}': no days provided.")

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
