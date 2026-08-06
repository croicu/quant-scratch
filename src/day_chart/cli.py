from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

from defs.contracts import IntraDayProvider
from defs.protocols import BarConflict
from shared.diagnostics import ConsoleLogSink, Logger
from shared.errors import AppError
from shared.providers import databento, yahoo_finance
from shared.providers.databento import DatabentoIntraDay
from shared.providers.ibkr import IBKRIntraDay
from shared.providers.quant_data import QuantDataIntraDay
from shared.providers.yahoo_finance import YahooFinanceIntraDay
from shared.settings import Settings

from . import chart
from .chart import DayChartData
from .output import bars_to_csv

CATEGORY_DATE_RANGE = "date_range"

PROVIDER_IBKR = "ibkr"
PROVIDER_QUANT_DATA = "quant-data"
# Alias of yahoo_finance.PROVIDER_NAME, not an independent literal -- same reasoning as
# stock_quote.cli's PROVIDER_YAHOO/PROVIDER_IBKR aliases (see that module's own comment). day-chart
# doesn't stamp a provider identity onto DayBar the way stock-quote does onto StockQuote, but
# keeping this one aliased too avoids a stray third spelling of "yahoo" existing in the codebase.
PROVIDER_YAHOO = yahoo_finance.PROVIDER_NAME
# Same aliasing reasoning, against shared.providers.databento.PROVIDER_NAME.
PROVIDER_DATABENTO = databento.PROVIDER_NAME

# IBKR's historical-data API enforces its own pacing limits (documented ceiling: 60 requests per
# 10 minutes). Range mode calls fetch_bars once per day, so an unbounded range could plausibly
# cross that ceiling -- a live probe of 7 rapid same-contract requests (~2.6s total) found no
# pacing-violation errors, well below this cap, so 30 stays a comfortable, untested-but-documented
# margin rather than a measured breaking point. quant-data has no equivalent constraint (Postgres
# reads), so this only applies to the ibkr provider.
MAX_IBKR_RANGE_DAYS = 30

ShowChartFn = Callable[[str, list[DayChartData], list[BarConflict]], None]


@dataclass
class CliArguments:
    ticker: str
    date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    provider: str = PROVIDER_IBKR
    debug: bool = False


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="day-chart",
        usage="day-chart TICKER [--date YYYY-MM-DD | --start-date YYYY-MM-DD --end-date YYYY-MM-DD] [--provider {ibkr,quant-data,yahoo,databento}] [--debug]",
        description="Fetch full-day intraday bars for a stock ticker, pop up a price/volume chart, and export a CSV.",
    )

    parser.add_argument("ticker", help="stock ticker symbol, e.g. SPY")
    parser.add_argument(
        "--date",
        default=None,
        help="session date as YYYY-MM-DD; defaults to today (or the last trading day if today is a weekend). Ignored if --start-date or --end-date is given.",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="start of a date range as YYYY-MM-DD; overrides --date. Defaults to --end-date if omitted.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="end of a date range as YYYY-MM-DD; overrides --date. Defaults to today (or the last trading day if today is a weekend) if omitted.",
    )
    parser.add_argument(
        "--provider",
        choices=[PROVIDER_IBKR, PROVIDER_QUANT_DATA, PROVIDER_YAHOO, PROVIDER_DATABENTO],
        default=PROVIDER_IBKR,
        help=(
            f"intraday data source; '{PROVIDER_IBKR}' (default) has real extended-hours volume, "
            f"'{PROVIDER_QUANT_DATA}' reads the quant-data warehouse (Yahoo-sourced, no extended-hours volume), "
            f"'{PROVIDER_YAHOO}' hits Yahoo directly (same extended-hours gap as quant-data's ingest -- "
            f"useful for comparing what's actually in the warehouse against the raw source, not for everyday use), "
            f"'{PROVIDER_DATABENTO}' hits Databento's consolidated equities feed (paid API key required)"
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="override settings.json's debug flag",
    )

    args = parser.parse_args(argv)

    return CliArguments(
        ticker=args.ticker,
        date=args.date,
        start_date=args.start_date,
        end_date=args.end_date,
        provider=args.provider,
        debug=args.debug,
    )


def _parse_and_validate_date(date_argument: str, current_date: date) -> date:
    try:
        parsed_date = date.fromisoformat(date_argument)
    except ValueError as error:
        raise AppError(f"Invalid date: '{date_argument}' is not a valid YYYY-MM-DD date.") from error

    if parsed_date > current_date:
        raise AppError(f"Invalid date: '{parsed_date.isoformat()}' is in the future.")

    return parsed_date


def resolve_session_date(date_argument: str | None, today: date | None = None) -> date:
    current_date = date.today() if today is None else today

    if date_argument is None:
        return _last_trading_day(current_date)

    parsed_date = _parse_and_validate_date(date_argument, current_date)
    if parsed_date.weekday() >= 5:
        raise AppError(f"Invalid date: '{parsed_date.isoformat()}' falls on a weekend.")

    return parsed_date


def resolve_date_range(
    start_date_argument: str | None,
    end_date_argument: str | None,
    today: date | None = None,
) -> list[date]:
    current_date = date.today() if today is None else today

    if end_date_argument is None:
        parsed_end = _last_trading_day(current_date)
    else:
        parsed_end = _parse_and_validate_date(end_date_argument, current_date)

    if start_date_argument is None:
        parsed_start = parsed_end
    else:
        parsed_start = _parse_and_validate_date(start_date_argument, current_date)

    if parsed_start > parsed_end:
        raise AppError(f"Invalid range: start date '{parsed_start.isoformat()}' is after end date '{parsed_end.isoformat()}'.")

    session_dates: list[date] = []
    current = parsed_start
    while current <= parsed_end:
        session_dates.append(current)
        current += timedelta(days=1)

    return session_dates


def _last_trading_day(current_date: date) -> date:
    if current_date.weekday() == 5:  # Saturday
        return current_date - timedelta(days=1)
    if current_date.weekday() == 6:  # Sunday
        return current_date - timedelta(days=2)
    return current_date


def _build_provider(provider_name: str, settings: Settings) -> IntraDayProvider:
    if provider_name == PROVIDER_IBKR:
        ibkr_settings = settings.ibkr
        if ibkr_settings is None:
            return IBKRIntraDay()
        return IBKRIntraDay(
            host=ibkr_settings.host,
            port=ibkr_settings.port,
            client_id=ibkr_settings.client_id,
        )

    if provider_name == PROVIDER_YAHOO:
        return YahooFinanceIntraDay()

    if provider_name == PROVIDER_DATABENTO:
        if settings.databento is None:
            raise AppError("day-chart requires a 'databento' section in settings.json (or settings.local.json) with an apiKey to use --provider databento.")
        return DatabentoIntraDay(api_key=settings.databento.api_key, dataset=settings.databento.dataset)

    if settings.postgres is None:
        raise AppError("day-chart requires a 'postgres' section in settings.json to reach quant-data.")
    return QuantDataIntraDay(
        host=settings.postgres.host,
        port=settings.postgres.port,
        dbname=settings.postgres.dbname,
        user=settings.postgres.user,
        password=settings.postgres.password,
        ssh_user=settings.postgres.ssh_user,
        ssh_key_path=settings.postgres.ssh_key_path,
    )


def main(
    argv: list[str] | None = None,
    provider: IntraDayProvider | None = None,
    settings_path: Path | None = None,
    output_dir: Path | None = None,
    show_chart: ShowChartFn | None = None,
) -> int:
    cli_start = perf_counter()
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    active_output_dir = Path(".") if output_dir is None else output_dir

    try:
        settings = Settings.load() if settings_path is None else Settings.load(path=settings_path)
    except AppError as error:
        print(f"day-chart: error: {error}", file=sys.stderr)
        return 1

    debug = settings.debug or arguments.debug

    # Installed as early as possible -- anything that runs before this point (arg parsing,
    # Settings.load()) can't be logged at all, since ConsoleLogSink needs settings.logging/
    # log_categories/excluded_categories first. Previously this happened *after* constructing
    # QuantDataIntraDay (which opens the SSH tunnel/DB connection), so that connection's own perf
    # marker was silently swallowed by the default no-op sink -- moved up so it's visible.
    Logger.set_logger(
        ConsoleLogSink(
            min_level=settings.logging,
            categories=settings.log_categories,
            excluded_categories=settings.excluded_categories,
        )
    )
    Logger.perf("cli started, args parsed and settings loaded", perf_counter() - cli_start)

    try:
        active_provider = provider if provider is not None else _build_provider(arguments.provider, settings)

        active_show_chart = chart.show_chart if show_chart is None else show_chart

        normalized_ticker = arguments.ticker.upper()
        is_range_mode = arguments.start_date is not None or arguments.end_date is not None

        fetch_phase_start = perf_counter()

        if is_range_mode:
            session_dates = resolve_date_range(arguments.start_date, arguments.end_date)

            if arguments.provider == PROVIDER_IBKR and len(session_dates) > MAX_IBKR_RANGE_DAYS:
                raise AppError(
                    f"Range of {len(session_dates)} days exceeds the {MAX_IBKR_RANGE_DAYS}-day cap for "
                    f"--provider {PROVIDER_IBKR} (IBKR historical-data pacing limits, untested past this size -- "
                    f"use --provider {PROVIDER_QUANT_DATA} for longer ranges)."
                )

            days: list[DayChartData] = []
            for session_date in session_dates:
                try:
                    bars = active_provider.fetch_bars(normalized_ticker, session_date)
                except AppError as error:
                    Logger.warning(f"day-chart: skipping {session_date.isoformat()}: {error}", category=CATEGORY_DATE_RANGE)
                    continue
                days.append((session_date, bars))

            if not days:
                raise AppError(f"No data available for '{normalized_ticker}' between {session_dates[0].isoformat()} and {session_dates[-1].isoformat()}.")

            csv_path = active_output_dir / f"{normalized_ticker}_{session_dates[0].isoformat()}_{session_dates[-1].isoformat()}_data.csv"
        else:
            session_date = resolve_session_date(arguments.date)
            bars = active_provider.fetch_bars(normalized_ticker, session_date)
            days = [(session_date, bars)]

            csv_path = active_output_dir / f"{normalized_ticker}_{session_date.isoformat()}_data.csv"

        Logger.perf(f"fetch phase ({len(days)} day(s))", perf_counter() - fetch_phase_start)

        # Pending-resolution ("disputed") bars are a quant-data-only reconciliation concept --
        # ibkr/yahoo are raw single-source fetches with nothing to be disputed against, so this is
        # a silent no-op for them rather than an error. Always on for quant-data, no separate flag:
        # one call for the whole resolved range (not per-day) since fetch_conflicts already
        # accepts a range natively.
        conflicts: list[BarConflict] = []
        if arguments.provider == PROVIDER_QUANT_DATA:
            if is_range_mode:
                conflicts = active_provider.fetch_conflicts(normalized_ticker, session_dates[0], session_dates[-1])
            else:
                conflicts = active_provider.fetch_conflicts(normalized_ticker, session_date, session_date)

        all_bars = []
        for _, day_bars in days:
            all_bars.extend(day_bars)

        active_show_chart(normalized_ticker, days, conflicts)

        write_start = perf_counter()
        csv_path.write_text(bars_to_csv(all_bars), encoding="utf-8", newline="")
        Logger.perf(f"wrote {len(all_bars)} rows to {csv_path}", perf_counter() - write_start)

        print(f"day-chart: wrote {csv_path}")
        return 0
    except AppError as error:
        if debug:
            raise
        print(f"day-chart: error: {error}", file=sys.stderr)
        return 1
    finally:
        Logger.set_logger(None)


if __name__ == "__main__":
    raise SystemExit(main())
