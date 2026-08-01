"""One-off pipeline-validation script for tasks/ibkr_fetch_historical_spy.md.

Not a registered CLI (no pyproject.toml entry point) -- run directly against a running IB
Gateway/TWS instance to confirm the IBKR historical-bars pipeline works before day-chart is
wired up to use IBKRIntraDay as a provider:

    python -m ibkr_fetch.validate [TICKER] [YYYY-MM-DD]

Defaults to SPY on 2026-07-31, the task's original scope.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from day_chart.output import bars_to_csv
from defs.protocols import DayBar
from shared.diagnostics import CATEGORY_GENERAL, ConsoleLogSink, Logger, TelemetryLevel
from shared.errors import AppError
from shared.providers.ibkr import IBKRIntraDay
from shared.sessions import AFTER_MARKET, PRE_MARKET, REGULAR

DEFAULT_TICKER = "SPY"
DEFAULT_DATE = date(2026, 7, 31)


def _spot_check(bars: list[DayBar]) -> str:
    lines = [f"total bars: {len(bars)}"]
    lines.append(f"first timestamp: {bars[0].timestamp.isoformat()}")
    lines.append(f"last timestamp: {bars[-1].timestamp.isoformat()}")

    for session in (PRE_MARKET, REGULAR, AFTER_MARKET):
        session_bar_count = 0
        zero_volume_bar_count = 0
        for bar in bars:
            if bar.session != session:
                continue
            session_bar_count += 1
            if bar.volume == 0:
                zero_volume_bar_count += 1
        lines.append(f"{session}: {session_bar_count} bars, {zero_volume_bar_count} with zero volume")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    ticker = arguments[0] if len(arguments) > 0 else DEFAULT_TICKER
    target_date = date.fromisoformat(arguments[1]) if len(arguments) > 1 else DEFAULT_DATE

    Logger.set_logger(ConsoleLogSink(min_level=TelemetryLevel.INFO, categories=[CATEGORY_GENERAL, "intraday_fetch", "perf"]))

    try:
        provider = IBKRIntraDay()
        bars = provider.fetch_bars(ticker, target_date)

        print(_spot_check(bars))

        csv_path = Path(".") / f"{ticker.upper()}_{target_date.isoformat()}_ibkr_data.csv"
        csv_path.write_text(bars_to_csv(bars), encoding="utf-8", newline="")
        print(f"ibkr-fetch-validate: wrote {csv_path}")
        return 0
    except AppError as error:
        print(f"ibkr-fetch-validate: error: {error}", file=sys.stderr)
        return 1
    finally:
        Logger.set_logger(None)


if __name__ == "__main__":
    raise SystemExit(main())
