from __future__ import annotations

from datetime import datetime, timezone

from day_chart.output import bars_to_csv
from defs.protocols import DayBar


def test_bars_to_csv_formats_header_and_rows():
    bars = [
        DayBar(
            timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
            open=471.5,
            high=472.4,
            low=471.3,
            close=472.1,
            volume=250000,
            session="regular",
        ),
        DayBar(
            timestamp=datetime(2026, 1, 2, 21, 0, tzinfo=timezone.utc),
            open=473.2,
            high=473.5,
            low=472.9,
            close=473.0,
            volume=9000,
            session="after-market",
        ),
    ]

    csv_text = bars_to_csv(bars)

    lines = csv_text.strip("\n").split("\n")
    assert lines[0] == "timestamp,open,high,low,close,volume,session"
    assert lines[1] == "2026-01-02T14:30:00+00:00,471.5,472.4,471.3,472.1,250000,regular"
    assert lines[2] == "2026-01-02T21:00:00+00:00,473.2,473.5,472.9,473.0,9000,after-market"


def test_bars_to_csv_header_only_for_empty_bars():
    csv_text = bars_to_csv([])

    assert csv_text.strip("\n") == "timestamp,open,high,low,close,volume,session"
