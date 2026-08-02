from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import yfinance

from defs.protocols import DayBar, StockQuote

from ..diagnostics import Logger
from ..errors import AppError
from ..sessions import infer_session

CATEGORY_QUOTE_FETCH = "quote_fetch"
CATEGORY_INTRADAY_FETCH = "intraday_fetch"

PROVIDER_NAME = "yahoo"


class YahooFinance:
    def fetch_quote(self, ticker: str) -> StockQuote:
        normalized_ticker = ticker.upper()

        try:
            fast_info = yfinance.Ticker(normalized_ticker).fast_info
            price = fast_info["lastPrice"]
            volume = fast_info["lastVolume"]
        except Exception as error:
            raise AppError(f"Failed to fetch quote for '{normalized_ticker}': {error}") from error

        if price is None or volume is None:
            raise AppError(f"No quote data available for '{normalized_ticker}'.")

        quote = StockQuote(
            ticker=normalized_ticker,
            price=float(price),
            timestamp=datetime.now(timezone.utc).isoformat(),
            volume=int(volume),
            provider=PROVIDER_NAME,
        )
        Logger.info(f"stock-quote: fetched quote for {normalized_ticker}.", category=CATEGORY_QUOTE_FETCH)
        return quote


class YahooFinanceIntraDay:
    def fetch_bars(self, ticker: str, target_date: date) -> list[DayBar]:
        normalized_ticker = ticker.upper()
        start = datetime.combine(target_date, datetime.min.time())
        end = start + timedelta(days=1)

        try:
            history = yfinance.Ticker(normalized_ticker).history(start=start, end=end, interval="1m", prepost=True)
        except Exception as error:
            raise AppError(f"Failed to fetch intraday bars for '{normalized_ticker}' on {target_date.isoformat()}: {error}") from error

        if history.empty:
            raise AppError(f"No data available for '{normalized_ticker}' on {target_date.isoformat()}.")

        bars: list[DayBar] = []
        for row_timestamp, row in history.iterrows():
            timestamp_utc = row_timestamp.tz_convert("UTC").to_pydatetime()
            bar = DayBar(
                timestamp=timestamp_utc,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row["Volume"]),
                session=infer_session(timestamp_utc),
            )
            bars.append(bar)

        Logger.info(
            f"day-chart: fetched {len(bars)} intraday bars for {normalized_ticker} on {target_date.isoformat()} from Yahoo.",
            category=CATEGORY_INTRADAY_FETCH,
        )
        return bars
