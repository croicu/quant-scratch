from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from .diagnostics import ConsoleLogSink, Logger
from .errors import AppError
from .settings import Settings


@dataclass
class CliArguments:
    debug: bool = False


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="quant-scratch",
        usage="quant-scratch [--debug]",
        description="Short experiments for validating assumptions about signals and correlations across financial market parameters.",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="override settings.json's debug flag",
    )

    args = parser.parse_args(argv)

    return CliArguments(debug=args.debug)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        settings = Settings.load()
    except AppError as error:
        print(f"quant-scratch: error: {error}", file=sys.stderr)
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
        Logger.info("quant-scratch: started.")
        Logger.info("quant-scratch: completed.")
        return 0
    except AppError as error:
        if debug:
            raise
        print(f"quant-scratch: error: {error}", file=sys.stderr)
        return 1
    finally:
        Logger.set_logger(None)


if __name__ == "__main__":
    raise SystemExit(main())
