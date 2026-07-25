from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StockQuote:
    ticker: str
    price: float
    timestamp: str
    volume: int
