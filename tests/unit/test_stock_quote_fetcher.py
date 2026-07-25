from __future__ import annotations

import pytest

from shared.errors import AppError
from stock_quote import fetcher
from stock_quote.protocols import StockQuote


class FakeTicker:
    def __init__(self, fast_info: dict):
        self.fast_info = fast_info


def test_fetch_quote_returns_stock_quote(monkeypatch):
    fake_info = {"lastPrice": 150.25, "lastVolume": 1_000_000}

    def fake_ticker(ticker: str) -> FakeTicker:
        return FakeTicker(fake_info)

    monkeypatch.setattr(fetcher.yfinance, "Ticker", fake_ticker)

    quote = fetcher.fetch_quote("aapl")

    assert isinstance(quote, StockQuote)
    assert quote.ticker == "AAPL"
    assert quote.price == 150.25
    assert quote.volume == 1_000_000
    assert quote.timestamp


def test_fetch_quote_raises_on_missing_data(monkeypatch):
    fake_info = {"lastPrice": None, "lastVolume": None}

    def fake_ticker(ticker: str) -> FakeTicker:
        return FakeTicker(fake_info)

    monkeypatch.setattr(fetcher.yfinance, "Ticker", fake_ticker)

    with pytest.raises(AppError):
        fetcher.fetch_quote("BADTICKER")


def test_fetch_quote_raises_on_network_error(monkeypatch):
    def fake_ticker(ticker: str) -> FakeTicker:
        raise RuntimeError("network down")

    monkeypatch.setattr(fetcher.yfinance, "Ticker", fake_ticker)

    with pytest.raises(AppError):
        fetcher.fetch_quote("AAPL")
