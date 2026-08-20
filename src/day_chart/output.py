from __future__ import annotations

import csv
import io

from defs.protocols import DayBar, QuoteBar
from shared.sessions import EASTERN

# Excel doesn't parse ISO 8601's "T" separator + UTC offset as a real datetime (imports as text,
# or mangles it) -- a plain "YYYY-MM-DD HH:MM:SS" in ET (matching the popup chart's timezone,
# shared.sessions.EASTERN) opens as a genuine Excel datetime with no import gymnastics. Safe from
# the usual local-time DST-ambiguity trap since day-chart never fetches bars outside the
# 4:00-20:00 ET session window (see ibkr.py's _AFTER_MARKET_CLOSE), well clear of the 2am ET
# fall-back transition.
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

CSV_HEADERS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "session",
    "incomplete",
    "wap",
    "trade_count",
    "avg_bid",
    "avg_ask",
    "midpoint_open",
    "midpoint_high",
    "midpoint_low",
    "midpoint_close",
]


def _blank_if_none(value: float | int | None) -> float | int | str:
    if value is None:
        return ""
    return value


def bars_to_csv(bars: list[DayBar], quote_bars: list[QuoteBar] | None = None) -> str:
    # Left join on DayBar timestamps -- every OHLCV minute gets a row; wap/trade_count/avg_bid/
    # avg_ask/midpoint_* are blank when quote_bars is omitted (a provider with no enrichment data)
    # or has no bar for that minute (same policy as each provider's own fetch_quote_bars merge).
    quote_bars_by_timestamp = {}
    if quote_bars is not None:
        for quote_bar in quote_bars:
            quote_bars_by_timestamp[quote_bar.timestamp] = quote_bar

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADERS)
    for bar in bars:
        matching_quote_bar = quote_bars_by_timestamp.get(bar.timestamp)
        if matching_quote_bar is None:
            wap = trade_count = avg_bid = avg_ask = ""
            midpoint_open = midpoint_high = midpoint_low = midpoint_close = ""
        else:
            wap = _blank_if_none(matching_quote_bar.wap)
            trade_count = _blank_if_none(matching_quote_bar.trade_count)
            avg_bid = _blank_if_none(matching_quote_bar.avg_bid)
            avg_ask = _blank_if_none(matching_quote_bar.avg_ask)
            midpoint_open = _blank_if_none(matching_quote_bar.midpoint_open)
            midpoint_high = _blank_if_none(matching_quote_bar.midpoint_high)
            midpoint_low = _blank_if_none(matching_quote_bar.midpoint_low)
            midpoint_close = _blank_if_none(matching_quote_bar.midpoint_close)
        writer.writerow(
            [
                bar.timestamp.astimezone(EASTERN).strftime(_TIMESTAMP_FORMAT),
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.session,
                bar.incomplete,
                wap,
                trade_count,
                avg_bid,
                avg_ask,
                midpoint_open,
                midpoint_high,
                midpoint_low,
                midpoint_close,
            ]
        )
    return buffer.getvalue()
