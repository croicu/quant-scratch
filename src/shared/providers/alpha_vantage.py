from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone

import requests

from defs.protocols import DayBar

from ..diagnostics import Logger
from ..errors import AppError
from ..sessions import EASTERN, infer_session

CATEGORY_INTRADAY_FETCH = "intraday_fetch"

BASE_URL = "https://www.alphavantage.co/query"
# Fixed for now (not yet exposed as a constructor/settings option) -- matches the reconciliation
# grain the rest of this repo's providers use. May become configurable later if a coarser interval
# is ever needed again for a bounded aggregation use case.
INTERVAL = "1min"

# Alpha Vantage's documented, long-stable response shape for TIME_SERIES_INTRADAY -- NOT
# live-verified against a real API key (none available while writing this). Field names ("1.
# open", etc.) and the "Time Series ({interval})" key naming are consistent across every
# TIME_SERIES_* endpoint per their public docs; still, treat this as the first thing to check if a
# live run fails to parse.
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class AlphaVantageIntraDay:
    def __init__(
        self,
        api_key: str,
        request_fn: Callable[[dict], dict] | None = None,
    ) -> None:
        self._api_key = api_key
        self._request = _request if request_fn is None else request_fn

    def fetch_bars(self, ticker: str, target_date: date) -> list[DayBar]:
        normalized_ticker = ticker.upper()
        # Alpha Vantage has no single-day fetch -- 'month' (YYYY-MM) is the finest-grained scope
        # it offers, so fetch the whole month and filter down to target_date below.
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": normalized_ticker,
            "interval": INTERVAL,
            "extended_hours": "true",
            "outputsize": "full",
            "adjusted": "false",
            "month": target_date.strftime("%Y-%m"),
            "apikey": self._api_key,
        }

        try:
            payload = self._request(params)
        except Exception as error:
            raise AppError(f"Failed to fetch intraday bars for '{normalized_ticker}' on {target_date.isoformat()} from Alpha Vantage: {error}") from error

        if "Error Message" in payload:
            raise AppError(f"Alpha Vantage error for '{normalized_ticker}': {payload['Error Message']}")
        if "Note" in payload:
            raise AppError(f"Alpha Vantage rate-limit note for '{normalized_ticker}': {payload['Note']}")
        if "Information" in payload:
            raise AppError(f"Alpha Vantage returned no data for '{normalized_ticker}': {payload['Information']}")

        time_series_key = f"Time Series ({INTERVAL})"
        if time_series_key not in payload:
            raise AppError(f"Unexpected Alpha Vantage response shape for '{normalized_ticker}': missing '{time_series_key}' key.")

        bars: list[DayBar] = []
        for timestamp_str, raw_bar in payload[time_series_key].items():
            timestamp_eastern = datetime.strptime(timestamp_str, _TIMESTAMP_FORMAT).replace(tzinfo=EASTERN)
            if timestamp_eastern.date() != target_date:
                continue
            timestamp_utc = timestamp_eastern.astimezone(timezone.utc)
            bar = DayBar(
                timestamp=timestamp_utc,
                open=float(raw_bar["1. open"]),
                high=float(raw_bar["2. high"]),
                low=float(raw_bar["3. low"]),
                close=float(raw_bar["4. close"]),
                volume=int(raw_bar["5. volume"]),
                session=infer_session(timestamp_utc),
            )
            bars.append(bar)

        if not bars:
            raise AppError(f"No data available for '{normalized_ticker}' on {target_date.isoformat()}.")

        bars.sort(key=_bar_timestamp)

        Logger.info(
            f"alpha-vantage: fetched {len(bars)} intraday bars for {normalized_ticker} on {target_date.isoformat()}.",
            category=CATEGORY_INTRADAY_FETCH,
        )
        return bars


def _bar_timestamp(bar: DayBar) -> datetime:
    return bar.timestamp


def _request(params: dict) -> dict:
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()
