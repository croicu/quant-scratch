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
        prog="__project_name__",
        usage="__project_name__ [--debug]",
        description="__description__",
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
        print(f"__project_name__: error: {error}", file=sys.stderr)
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
        Logger.info("__project_name__: started.")
        Logger.info("__project_name__: completed.")
        return 0
    except AppError as error:
        if debug:
            raise
        print(f"__project_name__: error: {error}", file=sys.stderr)
        return 1
    finally:
        Logger.set_logger(None)


if __name__ == "__main__":
    raise SystemExit(main())
