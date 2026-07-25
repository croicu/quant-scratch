from __future__ import annotations

from stock_quote.output import quote_to_csv
from stock_quote.protocols import StockQuote


def test_quote_to_csv_formats_header_and_row():
    quote = StockQuote(ticker="AAPL", price=150.25, timestamp="2026-01-01T00:00:00+00:00", volume=1_000_000)

    csv_text = quote_to_csv(quote)

    lines = csv_text.strip("\n").split("\n")
    assert lines[0] == "ticker,price,timestamp,volume"
    assert lines[1] == "AAPL,150.25,2026-01-01T00:00:00+00:00,1000000"
