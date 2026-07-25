from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from .errors import AppError

EASTERN = ZoneInfo("America/New_York")

PRE_MARKET = "pre-market"
REGULAR = "regular"
AFTER_MARKET = "after-market"

_PRE_MARKET_OPEN = time(4, 0)
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_AFTER_MARKET_CLOSE = time(20, 0)


def infer_session(timestamp_utc: datetime) -> str:
    local_time = timestamp_utc.astimezone(EASTERN).time()

    if _PRE_MARKET_OPEN <= local_time < _REGULAR_OPEN:
        return PRE_MARKET
    if _REGULAR_OPEN <= local_time < _REGULAR_CLOSE:
        return REGULAR
    if _REGULAR_CLOSE <= local_time < _AFTER_MARKET_CLOSE:
        return AFTER_MARKET

    raise AppError(f"Timestamp '{timestamp_utc.isoformat()}' falls outside known market session hours (4:00-20:00 ET).")
