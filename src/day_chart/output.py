from __future__ import annotations

import csv
import io

from defs.protocols import DayBar

CSV_HEADERS = ["timestamp", "open", "high", "low", "close", "volume", "session", "incomplete"]


def bars_to_csv(bars: list[DayBar]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADERS)
    for bar in bars:
        writer.writerow([bar.timestamp.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume, bar.session, bar.incomplete])
    return buffer.getvalue()
