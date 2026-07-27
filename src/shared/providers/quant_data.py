from __future__ import annotations

from datetime import date, datetime, timezone

from quant_data.client.market_data import MarketData

from defs.protocols import DayBar

from ..diagnostics import Logger
from ..errors import AppError
from ..sessions import infer_session

CATEGORY_INTRADAY_FETCH = "intraday_fetch"


def _ensure_utc(timestamp: datetime) -> datetime:
    # quant_data.defs.protocols.OHLCV.timestamp is documented "timezone-aware, UTC", but
    # MarketData has been observed returning naive datetimes (psycopg's default for a Postgres
    # TIMESTAMP WITHOUT TIME ZONE column) -- a naive value silently gets reinterpreted as the
    # *system's local timezone* by datetime.astimezone(), which infer_session and the chart's ET
    # conversion both call. Normalizing here means session/chart correctness doesn't depend on
    # which machine this runs on. See https://github.com/croicu/quant-data/issues/8.
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


class QuantDataIntraDay:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        dbname: str | None = None,
        user: str = "quant_reader",
        password: str = "",
        client: MarketData | None = None,
    ) -> None:
        if client is not None:
            self._client = client
            return

        if host is None or port is None or dbname is None:
            raise AppError("QuantDataIntraDay requires host/port/dbname (or an injected client).")

        try:
            self._client = MarketData(host=host, port=port, dbname=dbname, user=user, password=password)
        except Exception as error:
            raise AppError(f"Failed to connect to quant-data at {host}:{port}/{dbname}: {error}") from error

    def fetch_bars(self, ticker: str, target_date: date) -> list[DayBar]:
        normalized_ticker = ticker.upper()

        try:
            ohlcv_bars = self._client.fetch_bars(normalized_ticker, target_date, target_date)
        except Exception as error:
            raise AppError(f"Failed to fetch bars for '{normalized_ticker}' on {target_date.isoformat()} from quant-data: {error}") from error

        if not ohlcv_bars:
            raise AppError(f"No data available for '{normalized_ticker}' on {target_date.isoformat()}.")

        bars: list[DayBar] = []
        skipped_count = 0
        for ohlcv in ohlcv_bars:
            timestamp_utc = _ensure_utc(ohlcv.timestamp)
            try:
                session = infer_session(timestamp_utc)
            except AppError:
                # quant-data's warehouse can contain bars outside the 4:00-20:00 ET window this
                # repo's session model covers (e.g. thin overnight activity, or stale/anomalous
                # ingest rows -- see github.com/croicu/quant-data/issues/9). day-chart's whole
                # purpose is session-transition analysis, so a handful of unclassifiable bars
                # shouldn't fail the entire fetch; skip them and note the count instead.
                skipped_count += 1
                continue

            bar = DayBar(
                timestamp=timestamp_utc,
                open=ohlcv.open,
                high=ohlcv.high,
                low=ohlcv.low,
                close=ohlcv.close,
                volume=ohlcv.volume,
                session=session,
                incomplete=ohlcv.incomplete,
            )
            bars.append(bar)

        if skipped_count:
            Logger.warning(
                f"day-chart: skipped {skipped_count} bar(s) for {normalized_ticker} on {target_date.isoformat()} outside the 4:00-20:00 ET session window.",
                category=CATEGORY_INTRADAY_FETCH,
            )

        if not bars:
            raise AppError(
                f"No bars for '{normalized_ticker}' on {target_date.isoformat()} fall within a known session "
                "(4:00-20:00 ET) — all returned data was outside that window."
            )

        Logger.info(
            f"day-chart: fetched {len(bars)} intraday bars for {normalized_ticker} on {target_date.isoformat()} from quant-data.",
            category=CATEGORY_INTRADAY_FETCH,
        )
        return bars
