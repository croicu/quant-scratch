from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from defs.protocols import StockQuote
from shared.errors import AppError

DEFAULT_DATA_PATH = Path(__file__).parent.parent / "data" / "yahoo_finance_quotes.json"


class MockYahooFinance:
    def __init__(self, data_path: Path = DEFAULT_DATA_PATH) -> None:
        with data_path.open("r", encoding="utf-8") as f:
            self._quotes: dict = json.load(f)

    def fetch_quote(self, ticker: str) -> StockQuote:
        normalized_ticker = ticker.upper()

        quote_data = self._quotes.get(normalized_ticker)
        if quote_data is None:
            raise AppError(f"No mock quote data for '{normalized_ticker}'.")

        return StockQuote(
            ticker=normalized_ticker,
            price=float(quote_data["price"]),
            timestamp=datetime.now(timezone.utc).isoformat(),
            volume=int(quote_data["volume"]),
        )
