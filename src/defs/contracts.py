"""Runtime behavioral interfaces.

`typing.Protocol` classes describing behavior (e.g. workers, executors) — not data. Persisted
or shared data contracts belong in protocols.py instead.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from .protocols import DayBar, StockQuote


class YahooFinanceProvider(Protocol):
    def fetch_quote(self, ticker: str) -> StockQuote: ...


class IntraDayProvider(Protocol):
    def fetch_bars(self, ticker: str, target_date: date) -> list[DayBar]:
        """Fetch 1-minute OHLCV bars for a single session day. Raises AppError if the ticker is
        invalid, the network call fails, or no bars are available for that date."""
        ...
