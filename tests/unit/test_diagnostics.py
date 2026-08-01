from __future__ import annotations

from shared.diagnostics import CATEGORY_PERF, CATEGORY_PERF_UI, DiagnosticsLogSink, Logger


def test_perf_defaults_to_perf_category():
    sink = DiagnosticsLogSink()
    Logger.set_logger(sink)

    Logger.perf("did a thing", 0.081)

    # DiagnosticsLogSink._pending is a class-level list shared across the whole test session (see
    # diagnostics.py), so only the last-appended record is ours to assert on -- not the list length.
    record = DiagnosticsLogSink._pending[-1]
    assert record.message == "duration: 0.081s - did a thing"
    assert record.category == CATEGORY_PERF

    Logger.set_logger(None)


def test_perf_accepts_an_explicit_category():
    sink = DiagnosticsLogSink()
    Logger.set_logger(sink)

    Logger.perf("event-loop poll 1", 0.1, category=CATEGORY_PERF_UI)

    record = DiagnosticsLogSink._pending[-1]
    assert record.message == "duration: 0.100s - event-loop poll 1"
    assert record.category == CATEGORY_PERF_UI

    Logger.set_logger(None)
