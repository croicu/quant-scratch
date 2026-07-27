from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from quant_data import OHLCV

from defs.protocols import DayBar
from shared.errors import AppError
from shared.providers.quant_data import QuantDataIntraDay


class FakeMarketData:
    def __init__(self, bars: list[OHLCV] | None = None, error: Exception | None = None):
        self._bars = bars if bars is not None else []
        self._error = error
        self.requested: tuple[str, date, date] | None = None

    def fetch_bars(self, ticker: str, start_date: date, end_date: date) -> list[OHLCV]:
        self.requested = (ticker, start_date, end_date)
        if self._error is not None:
            raise self._error
        return self._bars


def test_fetch_bars_converts_ohlcv_to_daybar_with_session_and_incomplete():
    fake_client = FakeMarketData(
        bars=[
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
                open=471.5,
                high=472.4,
                low=471.3,
                close=472.1,
                volume=250000,
                incomplete=False,
            ),
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc),
                open=470.0,
                high=470.5,
                low=469.8,
                close=470.2,
                volume=0,
                incomplete=True,
            ),
        ]
    )
    provider = QuantDataIntraDay(client=fake_client)

    bars = provider.fetch_bars("spy", date(2026, 1, 2))

    assert fake_client.requested == ("SPY", date(2026, 1, 2), date(2026, 1, 2))
    assert len(bars) == 2
    assert isinstance(bars[0], DayBar)
    assert bars[0].session == "regular"
    assert bars[0].incomplete is False
    assert bars[1].session == "pre-market"
    assert bars[1].incomplete is True


def test_fetch_bars_treats_naive_timestamp_as_utc():
    # quant-data's MarketData has been observed returning naive datetimes despite OHLCV.timestamp
    # being documented as timezone-aware UTC (see github.com/croicu/quant-data/issues/8) -- a naive
    # value must be treated as UTC (not silently reinterpreted as the system's local timezone by
    # .astimezone()), or session classification breaks depending on which machine this runs on.
    fake_client = FakeMarketData(
        bars=[
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 14, 30),  # naive, no tzinfo
                open=471.5,
                high=472.4,
                low=471.3,
                close=472.1,
                volume=250000,
                incomplete=False,
            ),
        ]
    )
    provider = QuantDataIntraDay(client=fake_client)

    bars = provider.fetch_bars("SPY", date(2026, 1, 2))

    assert bars[0].timestamp.tzinfo is not None
    assert bars[0].timestamp == datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    assert bars[0].session == "regular"


def test_fetch_bars_skips_bars_outside_known_session_hours():
    # quant-data's warehouse can contain bars outside the 4:00-20:00 ET window this repo's session
    # model covers (thin overnight activity, or anomalous ingest rows -- see
    # github.com/croicu/quant-data/issues/9). day-chart's purpose is session-transition analysis,
    # so a handful of unclassifiable bars shouldn't fail the entire fetch.
    fake_client = FakeMarketData(
        bars=[
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 6, 30, tzinfo=timezone.utc),  # 01:30 ET -- no session
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=858048,
                incomplete=False,
            ),
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),  # 09:30 ET -- regular
                open=471.5,
                high=472.4,
                low=471.3,
                close=472.1,
                volume=250000,
                incomplete=False,
            ),
        ]
    )
    provider = QuantDataIntraDay(client=fake_client)

    bars = provider.fetch_bars("SPY", date(2026, 1, 2))

    assert len(bars) == 1
    assert bars[0].session == "regular"


def test_fetch_bars_raises_when_all_bars_outside_known_session_hours():
    fake_client = FakeMarketData(
        bars=[
            OHLCV(
                ticker="SPY",
                timestamp=datetime(2026, 1, 2, 6, 30, tzinfo=timezone.utc),  # 01:30 ET -- no session
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=858048,
                incomplete=False,
            ),
        ]
    )
    provider = QuantDataIntraDay(client=fake_client)

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 1, 2))


def test_fetch_bars_raises_on_empty_result():
    provider = QuantDataIntraDay(client=FakeMarketData(bars=[]))

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 1, 2))


def test_fetch_bars_raises_on_client_error():
    provider = QuantDataIntraDay(client=FakeMarketData(error=RuntimeError("connection reset")))

    with pytest.raises(AppError):
        provider.fetch_bars("SPY", date(2026, 1, 2))


def test_constructor_requires_client_or_connection_details():
    with pytest.raises(AppError):
        QuantDataIntraDay()
