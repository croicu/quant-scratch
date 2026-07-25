"""Runtime behavioral interfaces.

`typing.Protocol` classes describing behavior (e.g. workers, executors) — not data. Persisted
or shared data contracts belong in protocols.py instead.
"""

from __future__ import annotations

from typing import Protocol

from .protocols import StockQuote


class YahooFinanceProvider(Protocol):
    def fetch_quote(self, ticker: str) -> StockQuote: ...
