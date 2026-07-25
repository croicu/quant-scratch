from __future__ import annotations

from datetime import datetime, timezone

import pytest

from day_chart.chart import render_chart
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


def test_render_chart_writes_png_file(tmp_path):
    bars = [
        _bar(9, 0, "pre-market"),
        _bar(14, 30, "regular"),
        _bar(21, 0, "after-market"),
    ]
    output_path = tmp_path / "SPY_2026-01-02_chart.png"

    render_chart("SPY", datetime(2026, 1, 2).date(), bars, output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_render_chart_raises_on_empty_bars(tmp_path):
    with pytest.raises(AppError):
        render_chart("SPY", datetime(2026, 1, 2).date(), [], tmp_path / "chart.png")
