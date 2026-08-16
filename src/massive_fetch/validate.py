"""One-off pipeline-fetch script for issue #23 (tasks/alpha_vantage_integration.md): fetches
extended-hours-inclusive 1-minute intraday bars for a ticker/date from Massive (formerly
Polygon.io), prints a spot-check summary, and writes them to CSV. Replaces the earlier Alpha
Vantage attempt (see shared/providers/alpha_vantage.py's own note) -- Alpha Vantage's intraday and
daily time series endpoints turned out to be premium-only on the free tier, discovered live;
Massive's free Basic tier includes 1-minute extended-hours bars with no such gate.

Not a registered CLI (no pyproject.toml entry point) -- run directly with
Settings.massive.api_key configured in settings.local.json:

    python -m massive_fetch.validate [TICKER] [YYYY-MM-DD]

Defaults to SPY on 2026-07-31.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from day_chart.output import bars_to_csv
from defs.protocols import DayBar
from shared.diagnostics import CATEGORY_GENERAL, ConsoleLogSink, Logger, TelemetryLevel
from shared.errors import AppError
from shared.providers.massive import MassiveIntraDay
from shared.sessions import AFTER_MARKET, PRE_MARKET, REGULAR
from shared.settings import Settings

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
        settings = Settings.load()
        if settings.massive is None:
            raise AppError("settings.local.json needs a 'massive' section with 'apiKey' set -- see docs/PROTOCOL.md.")

        provider = MassiveIntraDay(api_key=settings.massive.api_key)
        bars = provider.fetch_bars(ticker, target_date)

        print(_spot_check(bars))

        csv_path = Path(".") / f"{ticker.upper()}_{target_date.isoformat()}_massive_data.csv"
        csv_path.write_text(bars_to_csv(bars), encoding="utf-8", newline="")
        print(f"massive-fetch-validate: wrote {csv_path}")
        return 0
    except AppError as error:
        print(f"massive-fetch-validate: error: {error}", file=sys.stderr)
        return 1
    finally:
        Logger.set_logger(None)


if __name__ == "__main__":
    raise SystemExit(main())
