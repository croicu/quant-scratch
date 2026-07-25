from __future__ import annotations

import csv
import io

from defs.protocols import StockQuote

CSV_HEADERS = ["ticker", "price", "timestamp", "volume"]


def quote_to_csv(quote: StockQuote) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADERS)
    writer.writerow([quote.ticker, quote.price, quote.timestamp, quote.volume])
    return buffer.getvalue()
