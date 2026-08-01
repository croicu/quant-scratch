from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from day_chart import cli
from tests.mocks.quant_data import MockQuantDataIntraDay

SETTINGS_PATH = Path(__file__).parent.parent / "data" / "settings.json"


def test_resolve_session_date_defaults_to_weekday_as_is():
    resolved = cli.resolve_session_date(None, today=date(2026, 1, 2))  # Friday

    assert resolved == date(2026, 1, 2)


def test_resolve_session_date_rolls_saturday_back_to_friday():
    resolved = cli.resolve_session_date(None, today=date(2026, 1, 3))  # Saturday

    assert resolved == date(2026, 1, 2)


def test_resolve_session_date_rolls_sunday_back_to_friday():
    resolved = cli.resolve_session_date(None, today=date(2026, 1, 4))  # Sunday

    assert resolved == date(2026, 1, 2)


def test_resolve_session_date_accepts_explicit_valid_date():
    resolved = cli.resolve_session_date("2026-01-02", today=date(2026, 1, 5))

    assert resolved == date(2026, 1, 2)


def test_resolve_session_date_rejects_malformed_string():
    with pytest.raises(cli.AppError):
        cli.resolve_session_date("not-a-date", today=date(2026, 1, 5))


def test_resolve_session_date_rejects_future_date():
    with pytest.raises(cli.AppError):
        cli.resolve_session_date("2026-01-10", today=date(2026, 1, 5))


def test_resolve_session_date_rejects_weekend_date():
    with pytest.raises(cli.AppError):
        cli.resolve_session_date("2026-01-03", today=date(2026, 1, 5))  # Saturday


def test_resolve_date_range_with_both_bounds_is_inclusive():
    resolved = cli.resolve_date_range("2026-01-02", "2026-01-05", today=date(2026, 1, 10))

    assert resolved == [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4), date(2026, 1, 5)]


def test_resolve_date_range_start_only_defaults_end_to_last_trading_day():
    resolved = cli.resolve_date_range("2026-01-02", None, today=date(2026, 1, 4))  # Sunday

    assert resolved == [date(2026, 1, 2)]  # last trading day for Sunday is Friday 01-02


def test_resolve_date_range_end_only_defaults_start_to_same_day():
    resolved = cli.resolve_date_range(None, "2026-01-05", today=date(2026, 1, 10))

    assert resolved == [date(2026, 1, 5)]


def test_resolve_date_range_rejects_start_after_end():
    with pytest.raises(cli.AppError):
        cli.resolve_date_range("2026-01-05", "2026-01-02", today=date(2026, 1, 10))


def test_resolve_date_range_rejects_malformed_bound():
    with pytest.raises(cli.AppError):
        cli.resolve_date_range("not-a-date", "2026-01-05", today=date(2026, 1, 10))


def test_resolve_date_range_rejects_future_bound():
    with pytest.raises(cli.AppError):
        cli.resolve_date_range("2026-01-02", "2026-01-20", today=date(2026, 1, 10))


def test_resolve_date_range_allows_weekend_bounds():
    # Individual range bounds may land on a weekend -- the caller skips no-data days rather than
    # rejecting the bound outright, unlike resolve_session_date's single-day strictness.
    resolved = cli.resolve_date_range("2026-01-03", "2026-01-03", today=date(2026, 1, 10))  # Saturday

    assert resolved == [date(2026, 1, 3)]


def test_main_shows_chart_and_writes_csv_and_returns_zero(tmp_path, capsys):
    shown_calls = []

    exit_code = cli.main(
        ["spy", "--date", "2026-01-02"],
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days: shown_calls.append((ticker, days)),
    )

    captured = capsys.readouterr()
    csv_path = tmp_path / "SPY_2026-01-02_data.csv"

    assert exit_code == 0
    assert csv_path.exists()
    assert str(csv_path) in captured.out
    assert len(shown_calls) == 1
    assert shown_calls[0][0] == "SPY"
    assert len(shown_calls[0][1]) == 1
    assert shown_calls[0][1][0][0] == date(2026, 1, 2)


def test_main_returns_one_on_no_data(tmp_path, capsys):
    exit_code = cli.main(
        ["NOTINFIXTURE", "--date", "2026-01-02"],
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error" in captured.err


def test_main_exits_two_on_missing_argument():
    with pytest.raises(SystemExit) as exc_info:
        cli.main([])

    assert exc_info.value.code == 2


def test_main_returns_one_when_postgres_settings_missing(tmp_path, capsys):
    exit_code = cli.main(
        ["SPY", "--date", "2026-01-02"],
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "postgres" in captured.err


def test_main_range_mode_skips_weekend_and_writes_combined_csv(tmp_path):
    # Fixture has SPY data for 2026-01-02 (Fri) and 2026-01-05 (Mon) only; the weekend in between
    # (03/04) has no fixture entry, so it should be skipped with a warning rather than failing.
    shown_calls = []

    exit_code = cli.main(
        ["spy", "--start-date", "2026-01-02", "--end-date", "2026-01-05"],
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days: shown_calls.append((ticker, days)),
    )

    csv_path = tmp_path / "SPY_2026-01-02_2026-01-05_data.csv"

    assert exit_code == 0
    assert csv_path.exists()
    assert len(shown_calls) == 1
    charted_dates = []
    for session_date, _ in shown_calls[0][1]:
        charted_dates.append(session_date)
    assert charted_dates == [date(2026, 1, 2), date(2026, 1, 5)]


def test_main_range_mode_ignores_date_argument(tmp_path):
    shown_calls = []

    exit_code = cli.main(
        ["spy", "--date", "2026-01-02", "--start-date", "2026-01-05", "--end-date", "2026-01-05"],
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days: shown_calls.append((ticker, days)),
    )

    assert exit_code == 0
    assert len(shown_calls[0][1]) == 1
    assert shown_calls[0][1][0][0] == date(2026, 1, 5)


def test_main_range_mode_returns_one_when_every_day_has_no_data(tmp_path, capsys):
    exit_code = cli.main(
        ["NOTINFIXTURE", "--start-date", "2026-01-02", "--end-date", "2026-01-05"],
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error" in captured.err
