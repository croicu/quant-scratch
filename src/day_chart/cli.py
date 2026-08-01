from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

from defs.contracts import IntraDayProvider
from shared.diagnostics import ConsoleLogSink, Logger
from shared.errors import AppError
from shared.providers.quant_data import QuantDataIntraDay
from shared.settings import Settings

from . import chart
from .chart import DayChartData
from .output import bars_to_csv

CATEGORY_DATE_RANGE = "date_range"

ShowChartFn = Callable[[str, list[DayChartData]], None]


@dataclass
class CliArguments:
    ticker: str
    date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    debug: bool = False


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="day-chart",
        usage="day-chart TICKER [--date YYYY-MM-DD | --start-date YYYY-MM-DD --end-date YYYY-MM-DD] [--debug]",
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
        if provider is not None:
            active_provider = provider
        else:
            if settings.postgres is None:
                raise AppError("day-chart requires a 'postgres' section in settings.json to reach quant-data.")
            active_provider = QuantDataIntraDay(
                host=settings.postgres.host,
                port=settings.postgres.port,
                dbname=settings.postgres.dbname,
                user=settings.postgres.user,
                password=settings.postgres.password,
                ssh_user=settings.postgres.ssh_user,
                ssh_key_path=settings.postgres.ssh_key_path,
            )

        active_show_chart = chart.show_chart if show_chart is None else show_chart

        normalized_ticker = arguments.ticker.upper()
        is_range_mode = arguments.start_date is not None or arguments.end_date is not None

        fetch_phase_start = perf_counter()

        if is_range_mode:
            session_dates = resolve_date_range(arguments.start_date, arguments.end_date)

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

        all_bars = []
        for _, day_bars in days:
            all_bars.extend(day_bars)

        active_show_chart(normalized_ticker, days)

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
