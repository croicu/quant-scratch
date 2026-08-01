from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from matplotlib.backend_bases import CloseEvent, FigureCanvasBase

from day_chart import chart
from defs.protocols import DayBar
from shared.errors import AppError
from shared.settings import Settings, WindowSettings


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


class _FakeWindow:
    def __init__(self, x: int, y: int, screen_width: int = 1920, screen_height: int = 1080):
        self._x = x
        self._y = y
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.geometry_calls: list[str] = []
        self._configure_callback = None

    def winfo_screenwidth(self) -> int:
        return self.screen_width

    def winfo_screenheight(self) -> int:
        return self.screen_height

    def geometry(self, spec: str) -> None:
        self.geometry_calls.append(spec)

    def winfo_x(self) -> int:
        return self._x

    def winfo_y(self) -> int:
        return self._y

    def move_to(self, x: int, y: int) -> None:
        # Simulates the window being dragged: updates position and fires whatever was bound to
        # <Configure>, same as a real move/resize would.
        self._x = x
        self._y = y
        if self._configure_callback is not None:
            self._configure_callback()

    def bind(self, sequence: str, callback) -> None:
        if sequence == "<Configure>":
            self._configure_callback = callback


def _patch_show_chart_for_window_tests(
    monkeypatch,
    fake_window: _FakeWindow,
    before_close=None,
    virtual_desktop_bounds: tuple[int, int, int, int] = (0, 0, 1920, 1080),
) -> None:
    monkeypatch.setattr(chart.plt, "switch_backend", lambda name: None)
    monkeypatch.setattr(chart.plt, "show", lambda block=True: None)
    # Real GetSystemMetrics() would return this machine's actual desktop bounds -- pin it to a
    # known value so tests are deterministic regardless of what monitors happen to be attached.
    monkeypatch.setattr(chart, "_get_virtual_desktop_bounds", lambda window: virtual_desktop_bounds)

    def fake_start_event_loop(self, timeout=0):
        if before_close is not None:
            before_close()
        close_event = CloseEvent("close_event", self)
        self.callbacks.process("close_event", close_event)

    monkeypatch.setattr(FigureCanvasBase, "start_event_loop", fake_start_event_loop)

    real_render_chart = chart.render_chart

    def render_chart_with_fake_window(ticker, days):
        figure = real_render_chart(ticker, days)
        figure.canvas.manager.window = fake_window
        return figure

    monkeypatch.setattr(chart, "render_chart", render_chart_with_fake_window)


def test_load_saved_window_position_returns_none_when_unset(monkeypatch):
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings(debug=False)))

    assert chart._load_saved_window_position() is None


def test_load_saved_window_position_returns_saved_xy(monkeypatch):
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings(debug=False, window=WindowSettings(x=100, y=200))))

    assert chart._load_saved_window_position() == (100, 200)


def test_load_saved_window_position_returns_none_on_settings_error(monkeypatch):
    def raise_error(cls):
        raise RuntimeError("boom")

    monkeypatch.setattr(Settings, "load", classmethod(raise_error))

    assert chart._load_saved_window_position() is None


def test_save_window_position_swallows_errors(monkeypatch):
    def raise_error(cls, x, y):
        raise RuntimeError("boom")

    monkeypatch.setattr(Settings, "save_window_position", classmethod(raise_error))

    chart._save_window_position(1, 2)  # must not raise


def test_show_chart_applies_saved_position_within_screen_bounds(monkeypatch):
    bars = [_bar(9, 0, "pre-market")]
    fake_window = _FakeWindow(x=0, y=0)
    _patch_show_chart_for_window_tests(monkeypatch, fake_window)
    monkeypatch.setattr(chart, "_load_saved_window_position", lambda: (100, 200))
    monkeypatch.setattr(chart, "_save_window_position", lambda x, y: None)

    chart.show_chart("SPY", [(date(2026, 1, 2), bars)])

    assert fake_window.geometry_calls == ["+100+200"]


def test_show_chart_skips_off_screen_saved_position(monkeypatch):
    bars = [_bar(9, 0, "pre-market")]
    fake_window = _FakeWindow(x=0, y=0)
    _patch_show_chart_for_window_tests(monkeypatch, fake_window, virtual_desktop_bounds=(0, 0, 1920, 1080))
    monkeypatch.setattr(chart, "_load_saved_window_position", lambda: (5000, 5000))
    monkeypatch.setattr(chart, "_save_window_position", lambda x, y: None)

    chart.show_chart("SPY", [(date(2026, 1, 2), bars)])

    assert fake_window.geometry_calls == []


def test_show_chart_accepts_position_on_a_secondary_monitor(monkeypatch):
    # Regression test: winfo_screenwidth()/winfo_screenheight() only report the *primary*
    # monitor's resolution on Windows, not the full virtual desktop. A position on a monitor to
    # the left of the primary (negative x, valid within the virtual desktop bounds below) must not
    # be treated as "off-screen" just because it's outside a single 1920x1080 primary monitor.
    bars = [_bar(9, 0, "pre-market")]
    fake_window = _FakeWindow(x=0, y=0)
    _patch_show_chart_for_window_tests(monkeypatch, fake_window, virtual_desktop_bounds=(-1920, 0, 3840, 1080))
    monkeypatch.setattr(chart, "_load_saved_window_position", lambda: (-1500, 200))
    monkeypatch.setattr(chart, "_save_window_position", lambda x, y: None)

    chart.show_chart("SPY", [(date(2026, 1, 2), bars)])

    assert fake_window.geometry_calls == ["+-1500+200"]


def test_show_chart_saves_window_position_on_close(monkeypatch):
    bars = [_bar(9, 0, "pre-market")]
    fake_window = _FakeWindow(x=300, y=400)
    _patch_show_chart_for_window_tests(monkeypatch, fake_window)
    monkeypatch.setattr(chart, "_load_saved_window_position", lambda: None)
    saved_calls = []
    monkeypatch.setattr(chart, "_save_window_position", lambda x, y: saved_calls.append((x, y)))

    chart.show_chart("SPY", [(date(2026, 1, 2), bars)])

    assert saved_calls == [(300, 400)]


def test_show_chart_saves_latest_position_after_a_move(monkeypatch):
    # Regression test: close_event fires in response to the widget's own <Destroy> event, so by
    # the time show_chart's post-loop code runs, querying the window directly for its position
    # would already fail (window mid-teardown) -- the position must come from live <Configure>
    # tracking instead. Simulates the user dragging the window right before closing it, within the
    # same event-loop tick, and asserts the *moved-to* position is what gets saved, not the
    # position the window had when it was first created.
    bars = [_bar(9, 0, "pre-market")]
    fake_window = _FakeWindow(x=300, y=400)
    _patch_show_chart_for_window_tests(monkeypatch, fake_window, before_close=lambda: fake_window.move_to(555, 666))
    monkeypatch.setattr(chart, "_load_saved_window_position", lambda: None)
    saved_calls = []
    monkeypatch.setattr(chart, "_save_window_position", lambda x, y: saved_calls.append((x, y)))

    chart.show_chart("SPY", [(date(2026, 1, 2), bars)])

    assert saved_calls == [(555, 666)]


def test_show_chart_switches_backend_shows_and_waits_for_window_close(monkeypatch):
    bars = [_bar(9, 0, "pre-market"), _bar(14, 30, "regular")]
    switched_to = []
    shown = []
    poll_calls = []
    closed_figures = []

    monkeypatch.setattr(chart.plt, "switch_backend", switched_to.append)
    monkeypatch.setattr(chart.plt, "show", lambda block=True: shown.append(block))

    def fake_start_event_loop(self, timeout=0):
        poll_calls.append(timeout)
        if not closed_figures:
            # Simulate a real GUI backend firing 'close_event' when its window is closed --
            # plt.close() alone doesn't do this (it only deregisters the figure from pyplot),
            # since real backends dispatch this event from their own window-destroy handler.
            closed_figures.append(self.figure)
            close_event = CloseEvent("close_event", self)
            self.callbacks.process("close_event", close_event)

    # Patched on the base canvas class (not a specific instance) since show_chart's figure is
    # only created inside render_chart, after this monkeypatch has to already be in place.
    monkeypatch.setattr(FigureCanvasBase, "start_event_loop", fake_start_event_loop)

    chart.show_chart("SPY", [(date(2026, 1, 2), bars)])

    assert switched_to == [chart._INTERACTIVE_BACKEND]
    assert shown == [False]
    assert poll_calls == [chart._EVENT_LOOP_POLL_SECONDS]
    assert len(closed_figures) == 1
