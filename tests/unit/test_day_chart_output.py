from __future__ import annotations

from datetime import datetime, timezone

from day_chart.output import bars_to_csv
from defs.protocols import DayBar, QuoteBar

_HEADER = "timestamp,open,high,low,close,volume,session,incomplete,wap,trade_count,avg_bid,avg_ask,midpoint_open,midpoint_high,midpoint_low,midpoint_close"


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
            incomplete=False,
        ),
        DayBar(
            timestamp=datetime(2026, 1, 2, 21, 0, tzinfo=timezone.utc),
            open=473.2,
            high=473.5,
            low=472.9,
            close=473.0,
            volume=0,
            session="after-market",
            incomplete=True,
        ),
    ]

    csv_text = bars_to_csv(bars)

    lines = csv_text.strip("\n").split("\n")
    assert lines[0] == _HEADER
    # 2026-01-02 is winter (EST, UTC-5): 14:30 UTC -> 09:30 ET, 21:00 UTC -> 16:00 ET.
    assert lines[1] == "2026-01-02 09:30:00,471.5,472.4,471.3,472.1,250000,regular,False,,,,,,,,"
    assert lines[2] == "2026-01-02 16:00:00,473.2,473.5,472.9,473.0,0,after-market,True,,,,,,,,"


def test_bars_to_csv_header_only_for_empty_bars():
    csv_text = bars_to_csv([])

    assert csv_text.strip("\n") == _HEADER


def test_bars_to_csv_left_joins_quote_bars_onto_matching_timestamps():
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
            timestamp=datetime(2026, 1, 2, 14, 31, tzinfo=timezone.utc),
            open=472.1,
            high=472.6,
            low=471.9,
            close=472.3,
            volume=180000,
            session="regular",
        ),
    ]
    # Only one matching quote bar -- mirrors the real TRADES-vs-BID_ASK bar-count mismatch (16
    # vs 15) confirmed live: the 14:31 minute has no bid/ask match and should come back blank.
    quote_bars = [
        QuoteBar(
            timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
            wap=471.9,
            trade_count=42,
            avg_bid=471.4,
            avg_ask=471.6,
            midpoint_open=471.45,
            midpoint_high=471.75,
            midpoint_low=471.35,
            midpoint_close=471.55,
        )
    ]

    csv_text = bars_to_csv(bars, quote_bars)

    lines = csv_text.strip("\n").split("\n")
    # 2026-01-02 is winter (EST, UTC-5): 14:30/14:31 UTC -> 09:30/09:31 ET.
    assert lines[1] == "2026-01-02 09:30:00,471.5,472.4,471.3,472.1,250000,regular,False,471.9,42,471.4,471.6,471.45,471.75,471.35,471.55"
    assert lines[2] == "2026-01-02 09:31:00,472.1,472.6,471.9,472.3,180000,regular,False,,,,,,,,"
