from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from defs.contracts import YahooFinanceProvider
from shared.diagnostics import ConsoleLogSink, Logger
from shared.errors import AppError
from shared.providers.yahoo_finance import YahooFinance
from shared.settings import Settings

from .output import quote_to_csv


@dataclass
class CliArguments:
    ticker: str
    debug: bool = False


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="stock-quote",
        usage="stock-quote TICKER [--debug]",
        description="Fetch and print the current quote for a single stock ticker as CSV.",
    )

    parser.add_argument("ticker", help="stock ticker symbol, e.g. AAPL")
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="override settings.json's debug flag",
    )

    args = parser.parse_args(argv)

    return CliArguments(ticker=args.ticker, debug=args.debug)


def main(
    argv: list[str] | None = None,
    provider: YahooFinanceProvider | None = None,
    settings_path: Path | None = None,
) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    active_provider = YahooFinance() if provider is None else provider

    try:
        settings = Settings.load() if settings_path is None else Settings.load(path=settings_path)
    except AppError as error:
        print(f"stock-quote: error: {error}", file=sys.stderr)
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
        quote = active_provider.fetch_quote(arguments.ticker)
        print(quote_to_csv(quote), end="")
        return 0
    except AppError as error:
        if debug:
            raise
        print(f"stock-quote: error: {error}", file=sys.stderr)
        return 1
    finally:
        Logger.set_logger(None)


if __name__ == "__main__":
    raise SystemExit(main())
