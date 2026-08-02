from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from defs.contracts import YahooFinanceProvider
from shared.diagnostics import ConsoleLogSink, Logger
from shared.errors import AppError
from shared.providers import ibkr, yahoo_finance
from shared.providers.ibkr import IBKRQuote
from shared.providers.yahoo_finance import YahooFinance
from shared.settings import Settings

from .output import quote_to_csv

# Reuses each provider's own PROVIDER_NAME (the value it stamps onto StockQuote.provider) as the
# --provider flag's choices, rather than duplicating the strings here -- keeps the CLI flag and
# the provider's self-reported identity from being able to drift apart.
PROVIDER_YAHOO = yahoo_finance.PROVIDER_NAME
PROVIDER_IBKR = ibkr.PROVIDER_NAME


@dataclass
class CliArguments:
    ticker: str
    provider: str = PROVIDER_YAHOO
    debug: bool = False


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="stock-quote",
        usage="stock-quote TICKER [--provider {yahoo,ibkr}] [--debug]",
        description="Fetch and print the current quote for a single stock ticker as CSV.",
    )

    parser.add_argument("ticker", help="stock ticker symbol, e.g. AAPL")
    parser.add_argument(
        "--provider",
        choices=[PROVIDER_YAHOO, PROVIDER_IBKR],
        default=PROVIDER_YAHOO,
        help=(
            f"quote source; '{PROVIDER_YAHOO}' (default) is close to real-time, "
            f"'{PROVIDER_IBKR}' uses a local IB Gateway/TWS instance (delayed ~15-20min without a paid real-time subscription)"
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="override settings.json's debug flag",
    )

    args = parser.parse_args(argv)

    return CliArguments(ticker=args.ticker, provider=args.provider, debug=args.debug)


def _build_provider(provider_name: str, settings: Settings) -> YahooFinanceProvider:
    if provider_name == PROVIDER_IBKR:
        ibkr_settings = settings.ibkr
        if ibkr_settings is None:
            return IBKRQuote()
        return IBKRQuote(
            host=ibkr_settings.host,
            port=ibkr_settings.port,
            client_id=ibkr_settings.client_id,
        )

    return YahooFinance()


def main(
    argv: list[str] | None = None,
    provider: YahooFinanceProvider | None = None,
    settings_path: Path | None = None,
) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)

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
        active_provider = provider if provider is not None else _build_provider(arguments.provider, settings)
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
