"""Persisted/shared data contracts.

Dataclasses only — no methods, no logic. Behavior that operates on these types belongs in a
dedicated entity/service layer, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class StockQuote:
    ticker: str
    price: float
    timestamp: str
    volume: int


@dataclass
class DayBar:
    timestamp: datetime  # timezone-aware, UTC
    open: float
    high: float
    low: float
    close: float
    volume: int
    session: str  # "pre-market", "regular", or "after-market"
    incomplete: bool = False  # provider couldn't supply full data for this bar (e.g. missing volume)
