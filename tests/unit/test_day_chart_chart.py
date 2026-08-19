from __future__ import annotations

from datetime import date, datetime, timezone

import matplotlib.dates as mdates
import pytest
from matplotlib.backend_bases import CloseEvent, FigureCanvasBase
from matplotlib.colors import to_rgba
from matplotlib.patches import Rectangle

from day_chart import chart
from defs.protocols import BarConflict, DayBar, ProviderBar
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


def _conflict(hour_utc: int, minute_utc: int, candidate_count: int = 1) -> BarConflict:
    whistleblower_bar = DayBar(
        timestamp=datetime(2026, 1, 2, hour_utc, minute_utc, tzinfo=timezone.utc),
        open=470.0,
        high=470.6,
        low=469.5,
        close=470.3,
        volume=500,
        session="regular",
    )
    candidates = []
    for candidate_index in range(candidate_count):
        candidate_bar = DayBar(
            timestamp=datetime(2026, 1, 2, hour_utc, minute_utc, tzinfo=timezone.utc),
            open=471.0,
            high=471.6,
            low=470.5,
            close=471.3,
            volume=600,
            session="regular",
        )
        candidates.append(ProviderBar(provider=f"candidate{candidate_index}", bar=candidate_bar))

    return BarConflict(field_group="ohlc", whistleblower=ProviderBar(provider="yfinance", bar=whistleblower_bar), candidates=candidates)


def _rejected_bar(hour_utc: int, minute_utc: int) -> ProviderBar:
    bar = DayBar(
        timestamp=datetime(2026, 1, 2, hour_utc, minute_utc, tzinfo=timezone.utc),
        open=469.0,
        high=469.6,
        low=468.5,
        close=469.3,
        volume=400,
        session="regular",
    )
    return ProviderBar(provider="yfinance", bar=bar)


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


def _candle_bodies(price_axis) -> list[Rectangle]:
    bodies = []
    for patch in price_axis.patches:
        if isinstance(patch, Rectangle) and patch.get_gid() == chart._CONFLICT_CANDLE_GID:
            bodies.append(patch)
    return bodies


def _rejected_candle_bodies(price_axis) -> list[Rectangle]:
    bodies = []
    for patch in price_axis.patches:
        if isinstance(patch, Rectangle) and patch.get_gid() == chart._REJECTED_CANDLE_GID:
            bodies.append(patch)
    return bodies


def test_render_chart_draws_no_candlesticks_without_conflicts():
    bars = [_bar(14, 30, "regular")]

    figure = chart.render_chart("SPY", [(date(2026, 1, 2), bars)])

    price_axis = figure.axes[0]
    assert _candle_bodies(price_axis) == []
    chart.plt.close(figure)


def test_render_chart_draws_no_candlesticks_when_conflicts_is_empty_list():
    bars = [_bar(14, 30, "regular")]

    figure = chart.render_chart("SPY", [(date(2026, 1, 2), bars)], [])

    price_axis = figure.axes[0]
    assert _candle_bodies(price_axis) == []
    chart.plt.close(figure)


def test_render_chart_draws_whistleblower_red_and_one_candidate_blue():
    bars = [_bar(14, 30, "regular")]
    conflicts = [_conflict(14, 30, candidate_count=1)]

    figure = chart.render_chart("SPY", [(date(2026, 1, 2), bars)], conflicts)

    price_axis = figure.axes[0]
    bodies = _candle_bodies(price_axis)
    assert len(bodies) == 2  # one whistleblower + one candidate

    colors = []
    for body in bodies:
        colors.append(body.get_facecolor())
    assert to_rgba(chart._WHISTLEBLOWER_COLOR) in colors
    assert to_rgba(chart._CANDIDATE_COLOR) in colors
    chart.plt.close(figure)


def test_render_chart_draws_one_candlestick_per_candidate():
    bars = [_bar(14, 30, "regular")]
    conflicts = [_conflict(14, 30, candidate_count=3)]

    figure = chart.render_chart("SPY", [(date(2026, 1, 2), bars)], conflicts)

    price_axis = figure.axes[0]
    bodies = _candle_bodies(price_axis)
    assert len(bodies) == 4  # one whistleblower + three candidates
    chart.plt.close(figure)


def test_render_chart_draws_no_rejected_candlesticks_without_rejected_bars():
    bars = [_bar(14, 30, "regular")]

    figure = chart.render_chart("SPY", [(date(2026, 1, 2), bars)])

    price_axis = figure.axes[0]
    assert _rejected_candle_bodies(price_axis) == []
    chart.plt.close(figure)


def test_render_chart_draws_no_rejected_candlesticks_when_rejected_bars_is_empty_list():
    bars = [_bar(14, 30, "regular")]

    figure = chart.render_chart("SPY", [(date(2026, 1, 2), bars)], None, [])

    price_axis = figure.axes[0]
    assert _rejected_candle_bodies(price_axis) == []
    chart.plt.close(figure)


def test_render_chart_draws_one_orange_candlestick_per_rejected_bar():
    bars = [_bar(14, 30, "regular")]
    rejected_bars = [_rejected_bar(14, 30), _rejected_bar(15, 0)]

    figure = chart.render_chart("SPY", [(date(2026, 1, 2), bars)], None, rejected_bars)

    price_axis = figure.axes[0]
    bodies = _rejected_candle_bodies(price_axis)
    assert len(bodies) == 2

    colors = []
    for body in bodies:
        colors.append(body.get_facecolor())
    assert colors == [to_rgba(chart._REJECTED_COLOR), to_rgba(chart._REJECTED_COLOR)]
    chart.plt.close(figure)


def test_render_chart_positions_rejected_candlestick_within_its_own_minute():
    # Regression: a rejected bar's minute already has a real resolved black candle (unlike a
    # conflict's pending whistleblower minute, which has none), so the offset must stay under a
    # full minute -- otherwise the rejected candle visually drifts onto the *next* minute's slot,
    # looking like the wrong bar was flagged.
    bars = [_bar(14, 30, "regular")]
    rejected_bars = [_rejected_bar(14, 30)]

    figure = chart.render_chart("SPY", [(date(2026, 1, 2), bars)], None, rejected_bars)

    price_axis = figure.axes[0]
    bodies = _rejected_candle_bodies(price_axis)
    assert len(bodies) == 1

    own_timestamp_et = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc).astimezone(chart.EASTERN)
    own_x = mdates.date2num(own_timestamp_et)
    body_center_x = bodies[0].get_x() + bodies[0].get_width() / 2
    one_minute_in_days = 1 / (24 * 60)
    assert body_center_x - own_x < one_minute_in_days
    chart.plt.close(figure)


def test_render_chart_only_draws_rejected_bars_on_their_own_day():
    bars_day_1 = [_bar(14, 30, "regular")]
    bars_day_2 = [
        DayBar(
            timestamp=datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc),
            open=470.0,
            high=470.5,
            low=469.8,
            close=470.2,
            volume=1000,
            session="regular",
        )
    ]
    days = [(date(2026, 1, 2), bars_day_1), (date(2026, 1, 5), bars_day_2)]
    rejected_bars = [_rejected_bar(14, 30)]  # timestamped 2026-01-02

    figure = chart.render_chart("SPY", days, None, rejected_bars)

    day_1_price_axis = figure.axes[0]
    day_2_price_axis = figure.axes[2]  # axes ordering: [day1 price, day1 volume, day2 price, day2 volume]
    assert len(_rejected_candle_bodies(day_1_price_axis)) == 1
    assert len(_rejected_candle_bodies(day_2_price_axis)) == 0
    chart.plt.close(figure)


def test_render_chart_draws_conflicts_and_rejected_bars_independently():
    # Conflict and rejected-bar candlesticks use distinct gids -- both can be present on the same
    # chart without one query picking up the other's patches.
    bars = [_bar(14, 30, "regular")]
    conflicts = [_conflict(14, 30, candidate_count=1)]
    rejected_bars = [_rejected_bar(15, 0)]

    figure = chart.render_chart("SPY", [(date(2026, 1, 2), bars)], conflicts, rejected_bars)

    price_axis = figure.axes[0]
    assert len(_candle_bodies(price_axis)) == 2
    assert len(_rejected_candle_bodies(price_axis)) == 1
    chart.plt.close(figure)


def test_render_chart_only_draws_conflicts_on_their_own_day():
    bars_day_1 = [_bar(14, 30, "regular")]
    bars_day_2 = [
        DayBar(
            timestamp=datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc),
            open=470.0,
            high=470.5,
            low=469.8,
            close=470.2,
            volume=1000,
            session="regular",
        )
    ]
    days = [(date(2026, 1, 2), bars_day_1), (date(2026, 1, 5), bars_day_2)]
    conflicts = [_conflict(14, 30, candidate_count=1)]  # timestamped 2026-01-02

    figure = chart.render_chart("SPY", days, conflicts)

    day_1_price_axis = figure.axes[0]
    day_2_price_axis = figure.axes[2]  # axes ordering: [day1 price, day1 volume, day2 price, day2 volume]
    assert len(_candle_bodies(day_1_price_axis)) == 2
    assert len(_candle_bodies(day_2_price_axis)) == 0
    chart.plt.close(figure)


def test_show_chart_forwards_conflicts_to_render_chart(monkeypatch):
    bars = [_bar(14, 30, "regular")]
    conflicts = [_conflict(14, 30)]
    received = []

    def fake_render_chart(ticker, days, passed_conflicts=None, passed_rejected_bars=None, passed_quote_bars=None):
        received.append(passed_conflicts)
        real_figure = chart.plt.figure()
        return real_figure

    monkeypatch.setattr(chart, "render_chart", fake_render_chart)
    monkeypatch.setattr(chart.plt, "switch_backend", lambda name: None)
    monkeypatch.setattr(chart.plt, "show", lambda block=True: None)

    def fake_start_event_loop(self, timeout=0):
        close_event = CloseEvent("close_event", self)
        self.callbacks.process("close_event", close_event)

    monkeypatch.setattr(FigureCanvasBase, "start_event_loop", fake_start_event_loop)

    chart.show_chart("SPY", [(date(2026, 1, 2), bars)], conflicts)

    assert received == [conflicts]


def test_show_chart_forwards_rejected_bars_to_render_chart(monkeypatch):
    bars = [_bar(14, 30, "regular")]
    rejected_bars = [_rejected_bar(14, 30)]
    received = []

    def fake_render_chart(ticker, days, passed_conflicts=None, passed_rejected_bars=None, passed_quote_bars=None):
        received.append(passed_rejected_bars)
        real_figure = chart.plt.figure()
        return real_figure

    monkeypatch.setattr(chart, "render_chart", fake_render_chart)
    monkeypatch.setattr(chart.plt, "switch_backend", lambda name: None)
    monkeypatch.setattr(chart.plt, "show", lambda block=True: None)

    def fake_start_event_loop(self, timeout=0):
        close_event = CloseEvent("close_event", self)
        self.callbacks.process("close_event", close_event)

    monkeypatch.setattr(FigureCanvasBase, "start_event_loop", fake_start_event_loop)

    chart.show_chart("SPY", [(date(2026, 1, 2), bars)], None, rejected_bars)

    assert received == [rejected_bars]


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

    def render_chart_with_fake_window(ticker, days, conflicts=None, rejected_bars=None, quote_bars=None):
        figure = real_render_chart(ticker, days, conflicts, rejected_bars, quote_bars)
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
