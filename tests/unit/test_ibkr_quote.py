from __future__ import annotations

import pytest
from ib_async import Ticker
from ib_async.ib import StartupFetch

from defs.protocols import StockQuote
from shared.errors import AppError
from shared.providers.ibkr import IBKRQuote


def _ticker(*, last: float = float("nan"), volume: float = float("nan"), marketDataType: int = 1) -> Ticker:
    # Ticker.__post_init__ resets last/volume/bid/ask/etc. back to its own "unset" (NaN) sentinel
    # unless created=True is passed -- a real ib_async quirk, not obvious from the constructor
    # signature alone (discovered the hard way: passing last=150.25 silently became NaN).
    return Ticker(last=last, volume=volume, marketDataType=marketDataType, created=True)


class FakeIB:
    def __init__(self, ticker_sequence: list[Ticker] | None = None, error: Exception | None = None):
        self._ticker_sequence = ticker_sequence if ticker_sequence is not None else []
        self._call_index = 0
        self._error = error
        self.connect_args: tuple | None = None
        self.connect_fetch_fields = None
        self.disconnect_called = False
        self.qualified_contract = None
        self.market_data_type_requests: list[int] = []

    def connect(self, host, port, clientId, timeout, fetchFields=None):
        self.connect_args = (host, port, clientId, timeout)
        self.connect_fetch_fields = fetchFields

    def disconnect(self):
        self.disconnect_called = True

    def qualifyContracts(self, contract):
        self.qualified_contract = contract

    def reqMarketDataType(self, market_data_type):
        self.market_data_type_requests.append(market_data_type)

    def reqTickers(self, *contracts):
        if self._error is not None:
            raise self._error
        ticker_data = self._ticker_sequence[self._call_index]
        self._call_index += 1
        return [ticker_data]


def test_fetch_quote_returns_live_quote_without_delayed_fallback():
    fake_ib = FakeIB(ticker_sequence=[_ticker(last=150.25, volume=1_000_000, marketDataType=1)])
    provider = IBKRQuote(client_factory=lambda: fake_ib)

    quote = provider.fetch_quote("aapl")

    assert isinstance(quote, StockQuote)
    assert quote.ticker == "AAPL"
    assert quote.price == 150.25
    assert quote.volume == 1_000_000
    assert quote.provider == "ibkr"
    assert quote.delayed is False
    assert fake_ib.market_data_type_requests == []  # never needed the delayed fallback


def test_fetch_quote_falls_back_to_delayed_when_live_is_unentitled():
    # First reqTickers call comes back all-NaN (no live entitlement, confirmed empirically against
    # the real Gateway -- see tasks/stock_quote_ibkr_integration.md); second call (after
    # reqMarketDataType(3)) returns real delayed data.
    fake_ib = FakeIB(
        ticker_sequence=[
            _ticker(marketDataType=1),  # last/volume stay NaN -- unentitled live response
            _ticker(last=744.20, volume=62_446_343, marketDataType=3),
        ]
    )
    provider = IBKRQuote(client_factory=lambda: fake_ib)

    quote = provider.fetch_quote("SPY")

    assert quote.price == 744.20
    assert quote.volume == 62_446_343
    assert quote.delayed is True
    assert fake_ib.market_data_type_requests == [3]


def test_fetch_quote_raises_when_both_live_and_delayed_come_back_empty():
    fake_ib = FakeIB(ticker_sequence=[_ticker(marketDataType=1), _ticker(marketDataType=3)])
    provider = IBKRQuote(client_factory=lambda: fake_ib)

    with pytest.raises(AppError):
        provider.fetch_quote("BADTICKER")


def test_fetch_quote_defaults_volume_to_zero_when_unset():
    fake_ib = FakeIB(ticker_sequence=[_ticker(last=100.0, marketDataType=1)])  # volume left NaN
    provider = IBKRQuote(client_factory=lambda: fake_ib)

    quote = provider.fetch_quote("SPY")

    assert quote.volume == 0


def test_fetch_quote_connects_and_disconnects_with_given_connection_details():
    fake_ib = FakeIB(ticker_sequence=[_ticker(last=1.0, volume=1, marketDataType=1)])
    provider = IBKRQuote(host="127.0.0.1", port=4002, client_id=7, timeout=5, client_factory=lambda: fake_ib)

    provider.fetch_quote("SPY")

    assert fake_ib.connect_args == ("127.0.0.1", 4002, 7, 5)
    assert fake_ib.disconnect_called is True


def test_fetch_quote_skips_startup_account_fetch_to_avoid_read_only_api_rejection():
    fake_ib = FakeIB(ticker_sequence=[_ticker(last=1.0, volume=1, marketDataType=1)])
    provider = IBKRQuote(client_factory=lambda: fake_ib)

    provider.fetch_quote("SPY")

    assert fake_ib.connect_fetch_fields == StartupFetch(0)


def test_fetch_quote_disconnects_even_when_request_fails():
    fake_ib = FakeIB(error=RuntimeError("connection reset"))
    provider = IBKRQuote(client_factory=lambda: fake_ib)

    with pytest.raises(AppError):
        provider.fetch_quote("SPY")

    assert fake_ib.disconnect_called is True
