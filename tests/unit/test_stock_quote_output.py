from __future__ import annotations

from defs.protocols import StockQuote
from stock_quote.output import quote_to_csv


def test_quote_to_csv_formats_header_and_row():
    quote = StockQuote(ticker="AAPL", price=150.25, timestamp="2026-01-01T00:00:00+00:00", volume=1_000_000, provider="yahoo")

    csv_text = quote_to_csv(quote)

    lines = csv_text.strip("\n").split("\n")
    assert lines[0] == "ticker,price,timestamp,volume,provider,delayed"
    assert lines[1] == "AAPL,150.25,2026-01-01T00:00:00+00:00,1000000,yahoo,False"


def test_quote_to_csv_includes_provider_and_delayed_flag():
    quote = StockQuote(ticker="SPY", price=744.20, timestamp="2026-01-01T00:00:00+00:00", volume=62_446_343, provider="ibkr", delayed=True)

    csv_text = quote_to_csv(quote)

    lines = csv_text.strip("\n").split("\n")
    assert lines[1] == "SPY,744.2,2026-01-01T00:00:00+00:00,62446343,ibkr,True"
