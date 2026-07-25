from __future__ import annotations

import pytest

from defs.protocols import StockQuote
from shared.errors import AppError
from tests.mocks.yahoo_finance import MockYahooFinance


def test_fetch_quote_returns_fixture_data():
    quote = MockYahooFinance().fetch_quote("aapl")

    assert isinstance(quote, StockQuote)
    assert quote.ticker == "AAPL"
    assert quote.price == 150.25
    assert quote.volume == 1_000_000
    assert quote.timestamp


def test_fetch_quote_raises_on_unknown_ticker():
    with pytest.raises(AppError):
        MockYahooFinance().fetch_quote("NOTINFIXTURE")
