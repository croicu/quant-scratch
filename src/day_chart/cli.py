from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from defs.contracts import IntraDayProvider
from shared.diagnostics import ConsoleLogSink, Logger
from shared.errors import AppError
from shared.settings import Settings
from shared.yahoo_finance import YahooFinanceIntraDay

from .chart import render_chart
from .output import bars_to_csv


@dataclass
class CliArguments:
    ticker: str
    date: str | None = None
    debug: bool = False


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="day-chart",
        usage="day-chart TICKER [--date YYYY-MM-DD] [--debug]",
        description="Fetch full-day intraday bars for a stock ticker and generate a price/volume chart plus CSV export.",
    )

    parser.add_argument("ticker", help="stock ticker symbol, e.g. SPY")
    parser.add_argument(
        "--date",
        default=None,
        help="session date as YYYY-MM-DD; defaults to today (or the last trading day if today is a weekend)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="override settings.json's debug flag",
    )

    args = parser.parse_args(argv)

    return CliArguments(ticker=args.ticker, date=args.date, debug=args.debug)


def resolve_session_date(date_argument: str | None, today: date | None = None) -> date:
    current_date = date.today() if today is None else today

    if date_argument is None:
        return _last_trading_day(current_date)

    try:
        parsed_date = date.fromisoformat(date_argument)
    except ValueError as error:
        raise AppError(f"Invalid date: '{date_argument}' is not a valid YYYY-MM-DD date.") from error

    if parsed_date > current_date:
        raise AppError(f"Invalid date: '{parsed_date.isoformat()}' is in the future.")
    if parsed_date.weekday() >= 5:
        raise AppError(f"Invalid date: '{parsed_date.isoformat()}' falls on a weekend.")

    return parsed_date


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
) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    active_provider = YahooFinanceIntraDay() if provider is None else provider
    active_output_dir = Path(".") if output_dir is None else output_dir

    try:
        settings = Settings.load() if settings_path is None else Settings.load(path=settings_path)
    except AppError as error:
        print(f"day-chart: error: {error}", file=sys.stderr)
        return 1

    debug = settings.debug or arguments.debug

    Logger.set_logger(
        ConsoleLogSink(
            min_level=settings.logging,
            categories=settings.log_categories,
            excluded_categories=settings.excluded_categories,
        )
    )
    try:
        normalized_ticker = arguments.ticker.upper()
        session_date = resolve_session_date(arguments.date)
        bars = active_provider.fetch_bars(normalized_ticker, session_date)

        chart_path = active_output_dir / f"{normalized_ticker}_{session_date.isoformat()}_chart.png"
        csv_path = active_output_dir / f"{normalized_ticker}_{session_date.isoformat()}_data.csv"

        render_chart(normalized_ticker, session_date, bars, chart_path)
        csv_path.write_text(bars_to_csv(bars), encoding="utf-8", newline="")

        print(f"day-chart: wrote {chart_path}")
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
