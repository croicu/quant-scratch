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
]


def bars_to_csv(bars: list[DayBar], quote_bars: list[QuoteBar] | None = None) -> str:
    # Left join on DayBar timestamps -- every OHLCV minute gets a row; wap/trade_count/avg_bid/
    # avg_ask are blank when quote_bars is omitted (non-IBKR providers) or has no bar for that
    # minute (same policy as IBKRIntraDay.fetch_quote_bars's own TRADES/BID_ASK merge).
    quote_bars_by_timestamp = {}
    if quote_bars is not None:
        for quote_bar in quote_bars:
            quote_bars_by_timestamp[quote_bar.timestamp] = quote_bar

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADERS)
    for bar in bars:
        matching_quote_bar = quote_bars_by_timestamp.get(bar.timestamp)
        wap = "" if matching_quote_bar is None or matching_quote_bar.wap is None else matching_quote_bar.wap
        trade_count = "" if matching_quote_bar is None or matching_quote_bar.trade_count is None else matching_quote_bar.trade_count
        avg_bid = "" if matching_quote_bar is None or matching_quote_bar.avg_bid is None else matching_quote_bar.avg_bid
        avg_ask = "" if matching_quote_bar is None or matching_quote_bar.avg_ask is None else matching_quote_bar.avg_ask
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
            ]
        )
    return buffer.getvalue()
