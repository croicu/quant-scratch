from __future__ import annotations

from datetime import datetime, timezone

import yfinance

from shared.diagnostics import Logger
from shared.errors import AppError

from .protocols import StockQuote

CATEGORY_QUOTE_FETCH = "quote_fetch"


def fetch_quote(ticker: str) -> StockQuote:
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
    )
    Logger.info(f"stock-quote: fetched quote for {normalized_ticker}.", category=CATEGORY_QUOTE_FETCH)
    return quote
