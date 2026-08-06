from __future__ import annotations

import time as time_module
from collections.abc import Callable
from datetime import date, datetime
from datetime import time as time_of_day

import databento as db

from defs.protocols import DayBar

from ..diagnostics import Logger
from ..errors import AppError
from ..sessions import EASTERN, infer_session

CATEGORY_INTRADAY_FETCH = "intraday_fetch"

PROVIDER_NAME = "databento"

# Matches the same 4:00-20:00 ET window IBKRIntraDay requests -- the full session range
# shared.sessions.infer_session understands, nothing beyond it.
_SESSION_OPEN = time_of_day(4, 0)
_SESSION_CLOSE = time_of_day(20, 0)

# DBEQ.BASIC: Databento's consolidated US equities feed (multiple lit venues), not a single
# exchange's own tape -- picked so a single-venue dataset doesn't silently under-report volume
# for a security that trades across venues.
DEFAULT_DATASET = "DBEQ.BASIC"

# Databento's hist.databento.com gateway has been observed returning intermittent, seemingly
# random 504s even on trivial requests (a single day's SPY bars succeeding on one call and
# failing on the next, no pattern by ticker/date/dataset) -- retrying a couple of times with a
# short delay clears most of them. 3 attempts / 2s chosen empirically as "enough to ride out the
# flakiness observed live" rather than a documented SLA from Databento.
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_RETRY_DELAY_SECONDS = 2.0


class DatabentoIntraDay:
    def __init__(
        self,
        api_key: str,
        dataset: str = DEFAULT_DATASET,
        client_factory: Callable[[str], db.Historical] | None = None,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._dataset = dataset
        self._client_factory = db.Historical if client_factory is None else client_factory
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._sleep = time_module.sleep if sleep_fn is None else sleep_fn

    def fetch_bars(self, ticker: str, target_date: date) -> list[DayBar]:
        normalized_ticker = ticker.upper()
        start = datetime.combine(target_date, _SESSION_OPEN, tzinfo=EASTERN)
        end = datetime.combine(target_date, _SESSION_CLOSE, tzinfo=EASTERN)

        client = self._client_factory(self._api_key)
        fetch_start = time_module.perf_counter()

        data = None
        last_server_error: db.BentoServerError | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                data = client.timeseries.get_range(
                    dataset=self._dataset,
                    start=start,
                    end=end,
                    symbols=[normalized_ticker],
                    schema=db.Schema.OHLCV_1M,
                )
                last_server_error = None
                break
            except db.BentoServerError as error:
                # 500-series -- Databento's own gateway/infrastructure, not our request being
                # malformed or unauthorized. Worth retrying. BentoClientError (400-series, e.g. bad
                # API key or invalid symbol) falls through to the generic handler below instead --
                # retrying an error that will never succeed just wastes time.
                last_server_error = error
                if attempt < self._max_attempts:
                    Logger.warning(
                        f"databento: request for '{normalized_ticker}' on {target_date.isoformat()} failed "
                        f"(attempt {attempt}/{self._max_attempts}): {error}. Retrying in {self._retry_delay_seconds}s.",
                        category=CATEGORY_INTRADAY_FETCH,
                    )
                    self._sleep(self._retry_delay_seconds)
            except Exception as error:
                raise AppError(f"Failed to fetch bars for '{normalized_ticker}' on {target_date.isoformat()} from Databento: {error}") from error

        if last_server_error is not None:
            raise AppError(
                f"Failed to fetch bars for '{normalized_ticker}' on {target_date.isoformat()} from Databento "
                f"after {self._max_attempts} attempts: {last_server_error}"
            ) from last_server_error

        Logger.perf(f"fetched from Databento ({self._dataset})", time_module.perf_counter() - fetch_start)

        frame = data.to_df(price_type="float", tz="UTC")
        if frame.empty:
            raise AppError(f"No data available for '{normalized_ticker}' on {target_date.isoformat()}.")

        bars: list[DayBar] = []
        for row_timestamp, row in frame.iterrows():
            timestamp_utc = row_timestamp.to_pydatetime()
            bar = DayBar(
                timestamp=timestamp_utc,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                session=infer_session(timestamp_utc),
            )
            bars.append(bar)

        Logger.info(
            f"day-chart: fetched {len(bars)} intraday bars for {normalized_ticker} on {target_date.isoformat()} from Databento.",
            category=CATEGORY_INTRADAY_FETCH,
        )
        return bars
