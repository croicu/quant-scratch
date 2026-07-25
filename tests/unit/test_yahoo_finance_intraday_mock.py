from __future__ import annotations

from datetime import date

import pytest

from defs.protocols import DayBar
from shared.errors import AppError
from tests.mocks.yahoo_finance import MockYahooFinanceIntraDay


def test_fetch_bars_returns_fixture_data():
    bars = MockYahooFinanceIntraDay().fetch_bars("spy", date(2026, 1, 2))

    assert len(bars) == 6
    assert isinstance(bars[0], DayBar)
    assert bars[0].session == "pre-market"
    assert bars[2].session == "regular"
    assert bars[4].session == "after-market"


def test_fetch_bars_raises_on_unknown_ticker():
    with pytest.raises(AppError):
        MockYahooFinanceIntraDay().fetch_bars("NOTINFIXTURE", date(2026, 1, 2))


def test_fetch_bars_raises_on_unknown_date():
    with pytest.raises(AppError):
        MockYahooFinanceIntraDay().fetch_bars("SPY", date(2020, 1, 1))
