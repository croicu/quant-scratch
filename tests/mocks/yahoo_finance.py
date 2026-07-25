from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from defs.protocols import DayBar, StockQuote
from shared.errors import AppError
from shared.sessions import infer_session

DEFAULT_DATA_PATH = Path(__file__).parent.parent / "data" / "yahoo_finance_quotes.json"
DEFAULT_DAY_BARS_PATH = Path(__file__).parent.parent / "data" / "day_bars.json"


class MockYahooFinance:
    def __init__(self, data_path: Path = DEFAULT_DATA_PATH) -> None:
        with data_path.open("r", encoding="utf-8") as f:
            self._quotes: dict = json.load(f)

    def fetch_quote(self, ticker: str) -> StockQuote:
        normalized_ticker = ticker.upper()

        quote_data = self._quotes.get(normalized_ticker)
        if quote_data is None:
            raise AppError(f"No mock quote data for '{normalized_ticker}'.")

        return StockQuote(
            ticker=normalized_ticker,
            price=float(quote_data["price"]),
            timestamp=datetime.now(timezone.utc).isoformat(),
            volume=int(quote_data["volume"]),
        )


class MockYahooFinanceIntraDay:
    def __init__(self, data_path: Path = DEFAULT_DAY_BARS_PATH) -> None:
        with data_path.open("r", encoding="utf-8") as f:
            self._bars_by_ticker: dict = json.load(f)

    def fetch_bars(self, ticker: str, target_date: date) -> list[DayBar]:
        normalized_ticker = ticker.upper()

        ticker_data = self._bars_by_ticker.get(normalized_ticker)
        if ticker_data is None:
            raise AppError(f"No mock intraday data for '{normalized_ticker}'.")

        day_data = ticker_data.get(target_date.isoformat())
        if day_data is None:
            raise AppError(f"No data available for '{normalized_ticker}' on {target_date.isoformat()}.")

        bars: list[DayBar] = []
        for bar_data in day_data:
            timestamp_utc = datetime.fromisoformat(bar_data["timestamp"])
            bar = DayBar(
                timestamp=timestamp_utc,
                open=float(bar_data["open"]),
                high=float(bar_data["high"]),
                low=float(bar_data["low"]),
                close=float(bar_data["close"]),
                volume=int(bar_data["volume"]),
                session=infer_session(timestamp_utc),
            )
            bars.append(bar)

        return bars
