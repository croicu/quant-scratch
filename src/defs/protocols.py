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
    provider: str  # which provider supplied this quote, e.g. "yahoo" or "ibkr"
    delayed: bool = False  # True if the provider could only supply delayed (not real-time) data


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


@dataclass
class ProviderBar:
    provider: str
    bar: DayBar


@dataclass
class BarConflict:
    # quant-data's reconciliation "stuck" queue: providers disagree on this field group for this
    # minute beyond tolerance, awaiting --finalize or manual correction. Not a DayBar itself, and
    # not part of IntraDayProvider's shared interface -- only quant-data has a reconciliation
    # concept to report a conflict from in the first place.
    field_group: str
    whistleblower: ProviderBar
    candidates: list[ProviderBar]  # usually one today, but plurality is possible -- never assume exactly one
