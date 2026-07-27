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


def test_main_writes_chart_and_csv_and_returns_zero(tmp_path, capsys):
    exit_code = cli.main(
        ["spy", "--date", "2026-01-02"],
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
    )

    captured = capsys.readouterr()
    chart_path = tmp_path / "SPY_2026-01-02_chart.png"
    csv_path = tmp_path / "SPY_2026-01-02_data.csv"

    assert exit_code == 0
    assert chart_path.exists()
    assert csv_path.exists()
    assert str(chart_path) in captured.out
    assert str(csv_path) in captured.out


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
