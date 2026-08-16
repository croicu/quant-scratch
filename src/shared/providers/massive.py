from __future__ import annotations

import time as time_module
from collections.abc import Callable
from datetime import date, datetime, timezone

import requests
from requests.exceptions import HTTPError

from defs.protocols import DayBar

from ..diagnostics import Logger
from ..errors import AppError
from ..sessions import infer_session

CATEGORY_INTRADAY_FETCH = "intraday_fetch"

PROVIDER_NAME = "massive"

# Massive (formerly Polygon.io -- polygon.io now 301-redirects here, same /v2/aggs/... API shape)
BASE_URL = "https://api.massive.com"

# Live-verified on the free Basic tier (2026-08-15): 1-minute bars, full 4:00-20:00 ET extended
# hours included by default (no separate flag needed, unlike Alpha Vantage's extended_hours=true),
# no premium gate. Confirmed via a real SPY 2026-07-31 call: 920 bars, 04:00-19:59 ET.

# Massive's free Basic tier documents 5 API calls/minute. A 429 mid-range (see day_chart.cli's
# MAX_MASSIVE_RANGE_DAYS note) is a transient condition, not "no data for this day" -- retrying
# gives the per-minute window a chance to clear rather than permanently dropping a real trading
# day from the chart the way a genuine no-data day (weekend/holiday) should be. 15s is a guess at
# a safe-enough spacing (60s/5 calls = 12s minimum, padded slightly), not a measured value -- the
# exact windowing (sliding vs. fixed-bucket) isn't known.
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_RETRY_DELAY_SECONDS = 15.0
_RATE_LIMIT_STATUS = 429


class MassiveIntraDay:
    def __init__(
        self,
        api_key: str,
        request_fn: Callable[[str, dict], dict] | None = None,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._request = _request if request_fn is None else request_fn
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._sleep = time_module.sleep if sleep_fn is None else sleep_fn

    def fetch_bars(self, ticker: str, target_date: date) -> list[DayBar]:
        normalized_ticker = ticker.upper()
        date_str = target_date.isoformat()
        url = f"{BASE_URL}/v2/aggs/ticker/{normalized_ticker}/range/1/minute/{date_str}/{date_str}"
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000,
            "apiKey": self._api_key,
        }

        payload = None
        last_rate_limit_error: HTTPError | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                payload = self._request(url, params)
                last_rate_limit_error = None
                break
            except HTTPError as error:
                status_code = error.response.status_code if error.response is not None else None
                if status_code != _RATE_LIMIT_STATUS:
                    raise AppError(f"Failed to fetch intraday bars for '{normalized_ticker}' on {target_date.isoformat()} from Massive: {error}") from error
                last_rate_limit_error = error
                if attempt < self._max_attempts:
                    Logger.warning(
                        f"massive: rate-limited fetching '{normalized_ticker}' on {target_date.isoformat()} "
                        f"(attempt {attempt}/{self._max_attempts}). Retrying in {self._retry_delay_seconds}s.",
                        category=CATEGORY_INTRADAY_FETCH,
                    )
                    self._sleep(self._retry_delay_seconds)
            except Exception as error:
                raise AppError(f"Failed to fetch intraday bars for '{normalized_ticker}' on {target_date.isoformat()} from Massive: {error}") from error

        if last_rate_limit_error is not None:
            raise AppError(
                f"Failed to fetch intraday bars for '{normalized_ticker}' on {target_date.isoformat()} from Massive "
                f"after {self._max_attempts} attempts (still rate-limited): {last_rate_limit_error}"
            ) from last_rate_limit_error

        if payload.get("status") == "ERROR":
            raise AppError(f"Massive error for '{normalized_ticker}': {payload.get('error', 'unknown error')}")

        raw_bars = payload.get("results")
        if not raw_bars:
            raise AppError(f"No data available for '{normalized_ticker}' on {target_date.isoformat()}.")

        bars: list[DayBar] = []
        for raw_bar in raw_bars:
            timestamp_utc = datetime.fromtimestamp(raw_bar["t"] / 1000, tz=timezone.utc)
            bar = DayBar(
                timestamp=timestamp_utc,
                open=float(raw_bar["o"]),
                high=float(raw_bar["h"]),
                low=float(raw_bar["l"]),
                close=float(raw_bar["c"]),
                # 'v' comes back as a float from the API (observed fractional values in practice,
                # e.g. odd-lot/computed volume) -- DayBar.volume is int, so this truncates, same as
                # every other provider's int(...) cast on its own raw volume field.
                volume=int(raw_bar["v"]),
                session=infer_session(timestamp_utc),
            )
            bars.append(bar)

        bars.sort(key=_bar_timestamp)

        Logger.info(
            f"massive: fetched {len(bars)} intraday bars for {normalized_ticker} on {target_date.isoformat()}.",
            category=CATEGORY_INTRADAY_FETCH,
        )
        return bars


def _bar_timestamp(bar: DayBar) -> datetime:
    return bar.timestamp


def _request(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()
