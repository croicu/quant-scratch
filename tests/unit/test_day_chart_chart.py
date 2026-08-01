from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from matplotlib.backend_bases import CloseEvent

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


def test_render_chart_returns_figure_with_price_and_volume_axes_for_one_day():
    bars = [
        _bar(9, 0, "pre-market"),
        _bar(14, 30, "regular"),
        _bar(21, 0, "after-market"),
    ]

    figure = chart.render_chart("SPY", [(date(2026, 1, 2), bars)])

    assert len(figure.axes) == 2
    chart.plt.close(figure)


def test_render_chart_returns_one_column_pair_per_day():
    bars = [_bar(9, 0, "pre-market"), _bar(14, 30, "regular")]
    days = [
        (date(2026, 1, 2), bars),
        (date(2026, 1, 5), bars),
        (date(2026, 1, 6), bars),
    ]

    figure = chart.render_chart("SPY", days)

    assert len(figure.axes) == 2 * len(days)
    chart.plt.close(figure)


def test_render_chart_raises_on_no_days():
    with pytest.raises(AppError):
        chart.render_chart("SPY", [])


def test_show_chart_switches_backend_shows_and_waits_for_window_close(monkeypatch):
    bars = [_bar(9, 0, "pre-market"), _bar(14, 30, "regular")]
    switched_to = []
    shown = []
    paused_calls = []
    closed_figures = []

    monkeypatch.setattr(chart.plt, "switch_backend", switched_to.append)
    monkeypatch.setattr(chart.plt, "show", lambda block=True: shown.append(block))

    def fake_pause(interval):
        paused_calls.append(interval)
        if not closed_figures:
            # Simulate a real GUI backend firing 'close_event' when its window is closed --
            # plt.close() alone doesn't do this (it only deregisters the figure from pyplot),
            # since real backends dispatch this event from their own window-destroy handler.
            current_figure = chart.plt.gcf()
            closed_figures.append(current_figure)
            close_event = CloseEvent("close_event", current_figure.canvas)
            current_figure.canvas.callbacks.process("close_event", close_event)

    monkeypatch.setattr(chart.plt, "pause", fake_pause)

    chart.show_chart("SPY", [(date(2026, 1, 2), bars)])

    assert switched_to == [chart._INTERACTIVE_BACKEND]
    assert shown == [False]
    assert len(paused_calls) == 1
    assert len(closed_figures) == 1
