from __future__ import annotations

import math
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from datetime import time as time_of_day

from ib_async import IB, BarData, Stock
from ib_async.ib import StartupFetch

from defs.protocols import DayBar, QuoteBar, StockQuote

from ..diagnostics import Logger
from ..errors import AppError
from ..sessions import EASTERN, infer_session

CATEGORY_INTRADAY_FETCH = "intraday_fetch"
CATEGORY_QUOTE_FETCH = "quote_fetch"

PROVIDER_NAME = "ibkr"

_AFTER_MARKET_CLOSE = time_of_day(20, 0)

_MARKET_DATA_TYPE_LIVE = 1
_MARKET_DATA_TYPE_DELAYED = 3


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

    def _fetch_raw_bars(self, ticker: str, target_date: date, method: str) -> list[BarData]:
        # Shared connect/qualify/reqHistoricalData/disconnect sequence, parameterized by IBKR's
        # own whatToShow value ("TRADES", "BID_ASK", ...) -- the single point where fetch_bars and
        # fetch_quote_bars distinguish which feed they're pulling.
        normalized_ticker = ticker.upper()
        contract = Stock(normalized_ticker, "SMART", "USD")
        # "1 D" ending at the after-market close covers the full 4:00-20:00 ET session this
        # repo's session model understands (shared.sessions) -- there's no bar data beyond that
        # boundary we'd do anything with anyway.
        end_date_time = datetime.combine(target_date, _AFTER_MARKET_CLOSE, tzinfo=EASTERN)

        ib = self._client_factory()
        connect_start = time.perf_counter()
        try:
            # fetchFields=StartupFetch(0): connect()'s default startup fetch (positions/orders/
            # account updates) needs write-level API access, which a Read-Only API Gateway (the
            # sensible setting for a data-only tool with no trading involved) rejects -- surfaced
            # as noisy stdout warnings and a Gateway popup on every connect. This provider only
            # ever calls reqHistoricalData (unaffected either way), so there's nothing to fetch at
            # startup in the first place.
            ib.connect(self._host, self._port, clientId=self._client_id, timeout=self._timeout, fetchFields=StartupFetch(0))
            Logger.perf(f"connected to IBKR at {self._host}:{self._port}", time.perf_counter() - connect_start)

            ib.qualifyContracts(contract)
            raw_bars = ib.reqHistoricalData(
                contract,
                endDateTime=end_date_time,
                durationStr="1 D",
                barSizeSetting="1 min",
                whatToShow=method,
                useRTH=False,
                formatDate=2,  # timezone-aware UTC datetimes on each bar, not TWS-local
            )
        except Exception as error:
            raise AppError(f"Failed to fetch {method} bars for '{normalized_ticker}' on {target_date.isoformat()} from IBKR: {error}") from error
        finally:
            ib.disconnect()

        return raw_bars

    def fetch_bars(self, ticker: str, target_date: date) -> list[DayBar]:
        normalized_ticker = ticker.upper()
        raw_bars = self._fetch_raw_bars(ticker, target_date, method="TRADES")

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

    def fetch_quote_bars(self, ticker: str, target_date: date) -> list[QuoteBar]:
        # Two independent IBKR calls, distinguished by the `method` argument on _fetch_raw_bars:
        # TRADES for wap/trade_count (already returned by IBKR on every TRADES bar, just unused by
        # fetch_bars), BID_ASK for avg_bid/avg_ask (IBKR's own semantics for a BID_ASK bar: open is
        # the time-averaged bid, close is the time-averaged ask). Deliberately a second TRADES call
        # rather than sharing fetch_bars's -- keeps DayBar/QuoteBar fully decoupled at the cost
        # of one redundant call (see quant-scratch#26 for the trade-off discussion).
        normalized_ticker = ticker.upper()
        trades_bars = self._fetch_raw_bars(ticker, target_date, method="TRADES")
        bid_ask_bars = self._fetch_raw_bars(ticker, target_date, method="BID_ASK")

        bid_ask_by_timestamp: dict[datetime, BarData] = {}
        for raw_bar in bid_ask_bars:
            if isinstance(raw_bar.date, datetime):
                bid_ask_by_timestamp[raw_bar.date] = raw_bar

        # Left join on the TRADES timestamps -- every TRADES minute gets an QuoteBar, with
        # avg_bid/avg_ask left None for any minute BID_ASK didn't return a bar for.
        quote_bars: list[QuoteBar] = []
        for raw_bar in trades_bars:
            if not isinstance(raw_bar.date, datetime):
                raise AppError(f"Unexpected non-intraday bar date '{raw_bar.date}' for '{normalized_ticker}' on {target_date.isoformat()}.")
            timestamp_utc = raw_bar.date
            matching_bid_ask = bid_ask_by_timestamp.get(timestamp_utc)
            quote_bars.append(
                QuoteBar(
                    timestamp=timestamp_utc,
                    wap=None if math.isnan(raw_bar.average) or raw_bar.average < 0 else float(raw_bar.average),
                    trade_count=None if raw_bar.barCount < 0 else int(raw_bar.barCount),
                    avg_bid=None if matching_bid_ask is None else matching_bid_ask.open,
                    avg_ask=None if matching_bid_ask is None else matching_bid_ask.close,
                    # This provider only fetches TRADES/BID_ASK, not MIDPOINT -- these come through
                    # populated when the data is quant-data-sourced instead (its own IBKR-derived
                    # archive already carries MIDPOINT), not from this direct-to-Gateway path.
                    midpoint_open=None,
                    midpoint_high=None,
                    midpoint_low=None,
                    midpoint_close=None,
                )
            )

        Logger.info(
            f"ibkr: fetched {len(quote_bars)} quote bars for {normalized_ticker} on {target_date.isoformat()} from IBKR.",
            category=CATEGORY_INTRADAY_FETCH,
        )
        return quote_bars


class IBKRQuote:
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
        self._client_factory = IB if client_factory is None else client_factory

    def fetch_quote(self, ticker: str) -> StockQuote:
        normalized_ticker = ticker.upper()
        contract = Stock(normalized_ticker, "SMART", "USD")

        ib = self._client_factory()
        connect_start = time.perf_counter()
        try:
            ib.connect(self._host, self._port, clientId=self._client_id, timeout=self._timeout, fetchFields=StartupFetch(0))
            Logger.perf(f"connected to IBKR at {self._host}:{self._port}", time.perf_counter() - connect_start)

            ib.qualifyContracts(contract)
            ticker_data = ib.reqTickers(contract)[0]
            if math.isnan(ticker_data.last):
                # No live entitlement for this account/contract (confirmed empirically -- see
                # tasks/stock_quote_ibkr_integration.md): the live request comes back with every
                # field NaN, no automatic fallback. Request delayed data explicitly and retry --
                # an account that *does* have live entitlement never reaches this branch.
                ib.reqMarketDataType(_MARKET_DATA_TYPE_DELAYED)
                ticker_data = ib.reqTickers(contract)[0]
        except Exception as error:
            raise AppError(f"Failed to fetch quote for '{normalized_ticker}' from IBKR: {error}") from error
        finally:
            ib.disconnect()

        if math.isnan(ticker_data.last):
            raise AppError(f"No quote data available for '{normalized_ticker}' from IBKR.")

        volume = 0 if math.isnan(ticker_data.volume) else int(ticker_data.volume)
        quote = StockQuote(
            ticker=normalized_ticker,
            price=float(ticker_data.last),
            timestamp=datetime.now(timezone.utc).isoformat(),
            volume=volume,
            provider=PROVIDER_NAME,
            # Reflects what actually came back (ticker_data.marketDataType), not which branch ran
            # above -- an entitled account requesting live data that happens to return 1 either way
            # should report delayed=False even though the code path looks the same either way.
            delayed=ticker_data.marketDataType != _MARKET_DATA_TYPE_LIVE,
        )
        Logger.info(
            f"ibkr: fetched quote for {normalized_ticker} (delayed={quote.delayed}).",
            category=CATEGORY_QUOTE_FETCH,
        )
        return quote
