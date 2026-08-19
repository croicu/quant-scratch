from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from ib_async import BarData
from ib_async.ib import StartupFetch

from defs.protocols import DayBar, QuoteBar
from shared.errors import AppError
from shared.providers.ibkr import IBKRIntraDay


class FakeIB:
    def __init__(self, bars: list[BarData] | None = None, error: Exception | None = None):
        self._bars = bars if bars is not None else []
        self._error = error
        self.connect_args: tuple | None = None
        self.disconnect_called = False
        self.qualified_contract = None
        self.historical_data_kwargs: dict | None = None

    def connect(self, host, port, clientId, timeout, fetchFields=None):
        self.connect_args = (host, port, clientId, timeout)
        self.connect_fetch_fields = fetchFields

    def disconnect(self):
        self.disconnect_called = True

    def qualifyContracts(self, contract):
        self.qualified_contract = contract

    def reqHistoricalData(self, contract, **kwargs):
        if self._error is not None:
            raise self._error
        self.historical_data_kwargs = kwargs
        return self._bars


class FakeIBByMethod:
    # fetch_quote_bars issues two separate reqHistoricalData calls (TRADES, then BID_ASK) over
    # the same connection -- this fake returns a different canned response per whatToShow value,
    # and records every call's kwargs so tests can assert both were made.
    def __init__(self, bars_by_method: dict[str, list[BarData]]):
        self._bars_by_method = bars_by_method
        self.disconnect_called = False
        self.historical_data_calls: list[dict] = []

    def connect(self, host, port, clientId, timeout, fetchFields=None):
        pass

    def disconnect(self):
        self.disconnect_called = True

    def qualifyContracts(self, contract):
        pass

    def reqHistoricalData(self, contract, **kwargs):
        self.historical_data_calls.append(kwargs)
        return self._bars_by_method.get(kwargs["whatToShow"], [])


def test_fetch_bars_converts_bardata_to_daybar_with_session():
    fake_ib = FakeIB(
        bars=[
            BarData(
                date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc),  # 10:30 ET -- regular
                open=471.5,
                high=472.4,
                low=471.3,
                close=472.1,
                volume=250000,
            ),
            BarData(
                date=datetime(2026, 7, 31, 9, 0, tzinfo=timezone.utc),  # 05:00 ET -- pre-market
                open=470.0,
                high=470.5,
                low=469.8,
                close=470.2,
                volume=0,
            ),
        ]
    )
    provider = IBKRIntraDay(client_factory=lambda: fake_ib)

    bars = provider.fetch_bars("spy", date(2026, 7, 31))

    assert len(bars) == 2
    assert isinstance(bars[0], DayBar)
    assert bars[0].session == "regular"
    assert bars[0].volume == 250000
    assert bars[1].session == "pre-market"
    assert fake_ib.qualified_contract.symbol == "SPY"
    assert fake_ib.qualified_contract.exchange == "SMART"
    assert fake_ib.qualified_contract.currency == "USD"


def test_fetch_bars_requests_extended_hours_one_minute_trades_bars():
    fake_ib = FakeIB(bars=[BarData(date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1)])
    provider = IBKRIntraDay(client_factory=lambda: fake_ib)

    provider.fetch_bars("SPY", date(2026, 7, 31))

    assert fake_ib.historical_data_kwargs["barSizeSetting"] == "1 min"
    assert fake_ib.historical_data_kwargs["whatToShow"] == "TRADES"
    assert fake_ib.historical_data_kwargs["useRTH"] is False
    assert fake_ib.historical_data_kwargs["durationStr"] == "1 D"
    assert fake_ib.historical_data_kwargs["formatDate"] == 2


def test_fetch_bars_connects_and_disconnects_with_given_connection_details():
    fake_ib = FakeIB(bars=[BarData(date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1)])
    provider = IBKRIntraDay(host="127.0.0.1", port=4002, client_id=7, timeout=5, client_factory=lambda: fake_ib)

    provider.fetch_bars("SPY", date(2026, 7, 31))

    assert fake_ib.connect_args == ("127.0.0.1", 4002, 7, 5)
    assert fake_ib.disconnect_called is True


def test_fetch_bars_skips_startup_account_fetch_to_avoid_read_only_api_rejection():
    # connect()'s default startup fetch (positions/orders/account updates) needs write-level API
    # access, which a Read-Only API Gateway rejects -- this provider never uses any of that, only
    # reqHistoricalData, so it should request an empty StartupFetch rather than the library default.
    fake_ib = FakeIB(bars=[BarData(date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1)])
    provider = IBKRIntraDay(client_factory=lambda: fake_ib)

    provider.fetch_bars("SPY", date(2026, 7, 31))

    assert fake_ib.connect_fetch_fields == StartupFetch(0)


def test_fetch_bars_disconnects_even_when_request_fails():
    fake_ib = FakeIB(error=RuntimeError("connection reset"))
    provider = IBKRIntraDay(client_factory=lambda: fake_ib)

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 7, 31))

    assert fake_ib.disconnect_called is True


def test_fetch_bars_raises_on_empty_result():
    provider = IBKRIntraDay(client_factory=lambda: FakeIB(bars=[]))

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 7, 31))


def test_fetch_bars_raises_on_connect_error():
    class RaisingConnectIB(FakeIB):
        def connect(self, host, port, clientId, timeout, fetchFields=None):
            raise ConnectionRefusedError("no gateway running")

    provider = IBKRIntraDay(client_factory=lambda: RaisingConnectIB())

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 7, 31))


def test_fetch_quote_bars_makes_one_trades_call_and_one_bid_ask_call():
    fake_ib = FakeIBByMethod(
        bars_by_method={
            "TRADES": [BarData(date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1, average=471.9, barCount=42)],
            "BID_ASK": [
                BarData(date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc), open=471.4, high=471.7, low=471.2, close=471.6, average=-1, barCount=-1)
            ],
        }
    )
    provider = IBKRIntraDay(client_factory=lambda: fake_ib)

    provider.fetch_quote_bars("SPY", date(2026, 7, 31))

    methods_requested = [call["whatToShow"] for call in fake_ib.historical_data_calls]
    assert methods_requested == ["TRADES", "BID_ASK"]


def test_fetch_quote_bars_converts_wap_and_trade_count_from_trades_bar():
    fake_ib = FakeIBByMethod(
        bars_by_method={
            "TRADES": [BarData(date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1, average=471.9, barCount=42)],
            "BID_ASK": [],
        }
    )
    provider = IBKRIntraDay(client_factory=lambda: fake_ib)

    quote_bars = provider.fetch_quote_bars("SPY", date(2026, 7, 31))

    assert len(quote_bars) == 1
    assert isinstance(quote_bars[0], QuoteBar)
    assert quote_bars[0].wap == 471.9
    assert quote_bars[0].trade_count == 42


def test_fetch_quote_bars_converts_avg_bid_and_avg_ask_from_bid_ask_bar_open_close():
    # IBKR's own semantics for a BID_ASK bar: open is the time-averaged bid, close is the
    # time-averaged ask (this repo's tasks/ingestion_variable_inventory.md documents this).
    fake_ib = FakeIBByMethod(
        bars_by_method={
            "TRADES": [BarData(date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1, average=471.9, barCount=42)],
            "BID_ASK": [
                BarData(date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc), open=471.4, high=471.7, low=471.2, close=471.6, average=-1, barCount=-1)
            ],
        }
    )
    provider = IBKRIntraDay(client_factory=lambda: fake_ib)

    quote_bars = provider.fetch_quote_bars("SPY", date(2026, 7, 31))

    assert quote_bars[0].avg_bid == 471.4
    assert quote_bars[0].avg_ask == 471.6


def test_fetch_quote_bars_left_joins_on_trades_timestamps_when_bid_ask_is_missing_a_minute():
    # Mirrors the real mismatch confirmed live: TRADES and BID_ASK can return different bar
    # counts for the same window. Every TRADES minute gets a row; a minute BID_ASK didn't return
    # comes back with avg_bid/avg_ask left None rather than being dropped.
    fake_ib = FakeIBByMethod(
        bars_by_method={
            "TRADES": [
                BarData(date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1, average=471.9, barCount=42),
                BarData(date=datetime(2026, 7, 31, 14, 31, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1, average=472.0, barCount=10),
            ],
            "BID_ASK": [
                BarData(date=datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc), open=471.4, high=471.7, low=471.2, close=471.6, average=-1, barCount=-1),
            ],
        }
    )
    provider = IBKRIntraDay(client_factory=lambda: fake_ib)

    quote_bars = provider.fetch_quote_bars("SPY", date(2026, 7, 31))

    assert len(quote_bars) == 2
    assert quote_bars[0].avg_bid == 471.4
    assert quote_bars[0].avg_ask == 471.6
    assert quote_bars[1].wap == 472.0
    assert quote_bars[1].trade_count == 10
    assert quote_bars[1].avg_bid is None
    assert quote_bars[1].avg_ask is None


def test_fetch_quote_bars_returns_empty_list_when_no_trades_bars():
    fake_ib = FakeIBByMethod(bars_by_method={"TRADES": [], "BID_ASK": []})
    provider = IBKRIntraDay(client_factory=lambda: fake_ib)

    quote_bars = provider.fetch_quote_bars("SPY", date(2026, 7, 31))

    assert quote_bars == []


def test_fetch_quote_bars_disconnects_even_when_request_fails():
    fake_ib = FakeIB(error=RuntimeError("connection reset"))
    provider = IBKRIntraDay(client_factory=lambda: fake_ib)

    with pytest.raises(AppError):
        provider.fetch_quote_bars("SPY", date(2026, 7, 31))

    assert fake_ib.disconnect_called is True
