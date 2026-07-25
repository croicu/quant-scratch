from __future__ import annotations

from datetime import datetime

from defs.protocols import StockQuote
from shared.providers.yahoo_finance import YahooFinance


def test_fetch_quote_returns_live_data_for_known_ticker():
    quote = YahooFinance().fetch_quote("aapl")

    assert isinstance(quote, StockQuote)
    assert quote.ticker == "AAPL"
    assert quote.price > 0
    assert quote.volume >= 0
    datetime.fromisoformat(quote.timestamp)
