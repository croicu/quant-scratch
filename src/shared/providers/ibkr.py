from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date, datetime
from datetime import time as time_of_day

from ib_async import IB, Stock

from defs.protocols import DayBar

from ..diagnostics import Logger
from ..errors import AppError
from ..sessions import EASTERN, infer_session

CATEGORY_INTRADAY_FETCH = "intraday_fetch"

_AFTER_MARKET_CLOSE = time_of_day(20, 0)


class IBKRIntraDay:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
        timeout: float = 10,
        client_factory: Callable[[], IB] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._timeout = timeout
        # A factory, not a shared instance -- fetch_bars() connects and disconnects a fresh
        # client per call (see tasks/ibkr_tws_extended_hours.md's "Connection lifecycle" design
        # decision), so each call needs its own IB() rather than reusing one that's already been
        # disconnected. Overridable for tests to inject a fake client.
        self._client_factory = IB if client_factory is None else client_factory

    def fetch_bars(self, ticker: str, target_date: date) -> list[DayBar]:
        normalized_ticker = ticker.upper()
        contract = Stock(normalized_ticker, "SMART", "USD")
        # "1 D" ending at the after-market close covers the full 4:00-20:00 ET session this
        # repo's session model understands (shared.sessions) -- there's no bar data beyond that
        # boundary we'd do anything with anyway.
        end_date_time = datetime.combine(target_date, _AFTER_MARKET_CLOSE, tzinfo=EASTERN)

        ib = self._client_factory()
        connect_start = time.perf_counter()
        try:
            ib.connect(self._host, self._port, clientId=self._client_id, timeout=self._timeout)
            Logger.perf(f"connected to IBKR at {self._host}:{self._port}", time.perf_counter() - connect_start)

            ib.qualifyContracts(contract)
            raw_bars = ib.reqHistoricalData(
                contract,
                endDateTime=end_date_time,
                durationStr="1 D",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=False,
                formatDate=2,  # timezone-aware UTC datetimes on each bar, not TWS-local
            )
        except Exception as error:
            raise AppError(f"Failed to fetch bars for '{normalized_ticker}' on {target_date.isoformat()} from IBKR: {error}") from error
        finally:
            ib.disconnect()

        if not raw_bars:
            raise AppError(f"No data available for '{normalized_ticker}' on {target_date.isoformat()}.")

        bars: list[DayBar] = []
        for raw_bar in raw_bars:
            if not isinstance(raw_bar.date, datetime):
                raise AppError(f"Unexpected non-intraday bar date '{raw_bar.date}' for '{normalized_ticker}' on {target_date.isoformat()}.")
            timestamp_utc = raw_bar.date
            bar = DayBar(
                timestamp=timestamp_utc,
                open=raw_bar.open,
                high=raw_bar.high,
                low=raw_bar.low,
                close=raw_bar.close,
                volume=int(raw_bar.volume),
                session=infer_session(timestamp_utc),
            )
            bars.append(bar)

        Logger.info(
            f"ibkr: fetched {len(bars)} intraday bars for {normalized_ticker} on {target_date.isoformat()} from IBKR.",
            category=CATEGORY_INTRADAY_FETCH,
        )
        return bars
