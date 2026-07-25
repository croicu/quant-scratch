from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from defs.protocols import DayBar  # noqa: E402
from shared.errors import AppError  # noqa: E402
from shared.sessions import AFTER_MARKET, EASTERN, PRE_MARKET, REGULAR  # noqa: E402

_SESSION_COLORS = {
    PRE_MARKET: "#fde68a",
    REGULAR: "#ffffff",
    AFTER_MARKET: "#c7d2fe",
}
_DEFAULT_SESSION_COLOR = "#ffffff"


def render_chart(ticker: str, session_date: date, bars: list[DayBar], output_path: Path) -> None:
    if not bars:
        raise AppError(f"Cannot render chart for '{ticker}': no bars provided.")

    timestamps_et: list[datetime] = []
    closes: list[float] = []
    volumes: list[int] = []
    sessions: list[str] = []
    for bar in bars:
        timestamps_et.append(bar.timestamp.astimezone(EASTERN))
        closes.append(bar.close)
        volumes.append(bar.volume)
        sessions.append(bar.session)

    figure, (price_axis, volume_axis) = plt.subplots(2, 1, sharex=True, figsize=(12, 8))

    price_axis.plot(timestamps_et, closes, color="#1f2937", linewidth=1)
    price_axis.set_ylabel("Price")
    price_axis.set_title(f"{ticker} — {session_date.isoformat()}")

    volume_axis.bar(timestamps_et, volumes, color="#1f2937", width=1 / (24 * 60))
    volume_axis.set_ylabel("Volume")
    volume_axis.set_xlabel("Time (ET)")

    _shade_sessions(price_axis, timestamps_et, sessions)
    _shade_sessions(volume_axis, timestamps_et, sessions)

    volume_axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=EASTERN))
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(output_path)
    plt.close(figure)


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
