from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from ib_async import BarData

from defs.protocols import DayBar
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

    def connect(self, host, port, clientId, timeout):
        self.connect_args = (host, port, clientId, timeout)

    def disconnect(self):
        self.disconnect_called = True

    def qualifyContracts(self, contract):
        self.qualified_contract = contract

    def reqHistoricalData(self, contract, **kwargs):
        if self._error is not None:
            raise self._error
        self.historical_data_kwargs = kwargs
        return self._bars


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
        def connect(self, host, port, clientId, timeout):
            raise ConnectionRefusedError("no gateway running")

    provider = IBKRIntraDay(client_factory=lambda: RaisingConnectIB())

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 7, 31))
