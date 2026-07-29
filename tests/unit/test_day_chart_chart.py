from __future__ import annotations

from datetime import datetime, timezone

import pytest

from day_chart import chart
from defs.protocols import DayBar
from shared.errors import AppError


def _bar(hour_utc: int, minute_utc: int, session: str) -> DayBar:
    return DayBar(
        timestamp=datetime(2026, 1, 2, hour_utc, minute_utc, tzinfo=timezone.utc),
        open=470.0,
        high=470.5,
        low=469.8,
        close=470.2,
        volume=1000,
        session=session,
    )


def test_render_chart_returns_figure_with_price_and_volume_axes():
    bars = [
        _bar(9, 0, "pre-market"),
        _bar(14, 30, "regular"),
        _bar(21, 0, "after-market"),
    ]

    figure = chart.render_chart("SPY", datetime(2026, 1, 2).date(), bars)

    assert len(figure.axes) == 2
    chart.plt.close(figure)


def test_render_chart_raises_on_empty_bars():
    with pytest.raises(AppError):
        chart.render_chart("SPY", datetime(2026, 1, 2).date(), [])


def test_show_chart_switches_backend_shows_and_waits_for_keypress(monkeypatch):
    bars = [_bar(9, 0, "pre-market"), _bar(14, 30, "regular")]
    switched_to = []
    shown = []
    prompted = []
    monkeypatch.setattr(chart.plt, "switch_backend", switched_to.append)
    monkeypatch.setattr(chart.plt, "show", lambda block=True: shown.append(block))
    monkeypatch.setattr("builtins.input", lambda prompt="": prompted.append(prompt))

    chart.show_chart("SPY", datetime(2026, 1, 2).date(), bars)

    assert switched_to == [chart._INTERACTIVE_BACKEND]
    assert shown == [False]
    assert len(prompted) == 1
