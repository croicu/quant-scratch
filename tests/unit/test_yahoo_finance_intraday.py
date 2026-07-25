from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from defs.protocols import DayBar
from shared import yahoo_finance
from shared.errors import AppError


class FakeTickerWithHistory:
    def __init__(self, history_df: pd.DataFrame):
        self._history_df = history_df

    def history(self, **kwargs) -> pd.DataFrame:
        return self._history_df


def _fake_history_df() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        ["2026-01-02 09:30:00-05:00", "2026-01-02 13:00:00-05:00"],
        name="Datetime",
    )
    return pd.DataFrame(
        {
            "Open": [471.5, 473.0],
            "High": [472.4, 473.6],
            "Low": [471.3, 472.7],
            "Close": [472.1, 473.2],
            "Volume": [250000, 180000],
        },
        index=index,
    )


def test_fetch_bars_returns_day_bars(monkeypatch):
    fake_df = _fake_history_df()

    def fake_ticker(ticker: str) -> FakeTickerWithHistory:
        return FakeTickerWithHistory(fake_df)

    monkeypatch.setattr(yahoo_finance.yfinance, "Ticker", fake_ticker)

    bars = yahoo_finance.YahooFinanceIntraDay().fetch_bars("spy", date(2026, 1, 2))

    assert len(bars) == 2
    assert isinstance(bars[0], DayBar)
    assert bars[0].session == "regular"
    assert bars[0].close == 472.1
    assert bars[1].close == 473.2


def test_fetch_bars_raises_on_empty_history(monkeypatch):
    empty_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    def fake_ticker(ticker: str) -> FakeTickerWithHistory:
        return FakeTickerWithHistory(empty_df)

    monkeypatch.setattr(yahoo_finance.yfinance, "Ticker", fake_ticker)

    with pytest.raises(AppError):
        yahoo_finance.YahooFinanceIntraDay().fetch_bars("SPY", date(2026, 1, 2))


def test_fetch_bars_raises_on_network_error(monkeypatch):
    def fake_ticker(ticker: str) -> FakeTickerWithHistory:
        raise RuntimeError("network down")

    monkeypatch.setattr(yahoo_finance.yfinance, "Ticker", fake_ticker)

    with pytest.raises(AppError):
        yahoo_finance.YahooFinanceIntraDay().fetch_bars("SPY", date(2026, 1, 2))
