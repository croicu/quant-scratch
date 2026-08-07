from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from day_chart import cli
from defs.protocols import DayBar
from shared.settings import DatabentoSettings, IBKRSettings, Settings
from tests.mocks.quant_data import MockQuantDataIntraDay

SETTINGS_PATH = Path(__file__).parent.parent / "data" / "settings.json"


class _FakeProviderTrackingQuantDataFetches:
    def __init__(self):
        self.fetch_conflicts_calls: list[tuple[str, date, date]] = []
        self.fetch_rejected_bars_calls: list[tuple[str, date, date]] = []

    def fetch_bars(self, ticker: str, target_date: date) -> list[DayBar]:
        return [
            DayBar(
                timestamp=datetime(target_date.year, target_date.month, target_date.day, 14, 30, tzinfo=timezone.utc),
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1,
                session="regular",
            )
        ]

    def fetch_conflicts(self, ticker: str, start_date: date, end_date: date) -> list:
        self.fetch_conflicts_calls.append((ticker, start_date, end_date))
        return []

    def fetch_rejected_bars(self, ticker: str, start_date: date, end_date: date) -> list:
        self.fetch_rejected_bars_calls.append((ticker, start_date, end_date))
        return []


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
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None: shown_calls.append((ticker, days)),
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
        ["SPY", "--date", "2026-01-02", "--provider", "quant-data"],
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
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None: shown_calls.append((ticker, days)),
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
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None: shown_calls.append((ticker, days)),
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


def test_build_provider_ibkr_uses_defaults_when_no_ibkr_settings(monkeypatch):
    captured_kwargs = {}

    class FakeIBKRIntraDay:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(cli, "IBKRIntraDay", FakeIBKRIntraDay)
    settings = Settings(debug=False)  # ibkr defaults to None

    provider = cli._build_provider(cli.PROVIDER_IBKR, settings)

    assert isinstance(provider, FakeIBKRIntraDay)
    assert captured_kwargs == {}


def test_build_provider_ibkr_forwards_settings_ibkr_fields(monkeypatch):
    captured_kwargs = {}

    class FakeIBKRIntraDay:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(cli, "IBKRIntraDay", FakeIBKRIntraDay)
    settings = Settings(debug=False, ibkr=IBKRSettings(host="10.0.0.5", port=4001, client_id=9))

    cli._build_provider(cli.PROVIDER_IBKR, settings)

    assert captured_kwargs == {"host": "10.0.0.5", "port": 4001, "client_id": 9}


def test_build_provider_quant_data_raises_when_postgres_settings_missing():
    settings = Settings(debug=False)  # postgres defaults to None

    with pytest.raises(cli.AppError):
        cli._build_provider(cli.PROVIDER_QUANT_DATA, settings)


def test_build_provider_yahoo_needs_no_settings():
    settings = Settings(debug=False)  # postgres/ibkr both None -- yahoo needs neither

    provider = cli._build_provider(cli.PROVIDER_YAHOO, settings)

    assert type(provider).__name__ == "YahooFinanceIntraDay"


def test_build_provider_databento_raises_when_databento_settings_missing():
    settings = Settings(debug=False)  # databento defaults to None

    with pytest.raises(cli.AppError):
        cli._build_provider(cli.PROVIDER_DATABENTO, settings)


def test_build_provider_databento_forwards_settings_fields(monkeypatch):
    captured_kwargs = {}

    class FakeDatabentoIntraDay:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(cli, "DatabentoIntraDay", FakeDatabentoIntraDay)
    settings = Settings(debug=False, databento=DatabentoSettings(api_key="db-test-key", dataset="XNAS.ITCH"))

    provider = cli._build_provider(cli.PROVIDER_DATABENTO, settings)

    assert isinstance(provider, FakeDatabentoIntraDay)
    assert captured_kwargs == {"api_key": "db-test-key", "dataset": "XNAS.ITCH"}


def test_main_range_mode_rejects_oversized_range_for_ibkr_provider(tmp_path, capsys):
    # No provider injected -- IBKRIntraDay() constructs offline (connect-per-call, not at
    # __init__), so this exercises the real default-provider path up to the cap check.
    exit_code = cli.main(
        ["SPY", "--start-date", "2026-01-01", "--end-date", "2026-03-01"],  # > 30 days
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "cap" in captured.err


def test_main_range_mode_ibkr_cap_does_not_apply_to_quant_data_provider(tmp_path):
    # Same oversized range as above, but --provider quant-data has no pacing constraint to cap --
    # only the two fixture-backed days (01-02, 01-05) actually chart, and the command still succeeds.
    exit_code = cli.main(
        ["SPY", "--start-date", "2026-01-01", "--end-date", "2026-03-01", "--provider", "quant-data"],
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None: None,
    )

    assert exit_code == 0


def test_main_fetches_conflicts_for_quant_data_provider_single_day(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()

    exit_code = cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "quant-data"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None: None,
    )

    assert exit_code == 0
    assert fake_provider.fetch_conflicts_calls == [("SPY", date(2026, 1, 2), date(2026, 1, 2))]
    assert fake_provider.fetch_rejected_bars_calls == [("SPY", date(2026, 1, 2), date(2026, 1, 2))]


def test_main_fetches_conflicts_once_for_whole_range_not_per_day(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()

    exit_code = cli.main(
        ["SPY", "--start-date", "2026-01-02", "--end-date", "2026-01-05", "--provider", "quant-data"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None: None,
    )

    assert exit_code == 0
    assert fake_provider.fetch_conflicts_calls == [("SPY", date(2026, 1, 2), date(2026, 1, 5))]
    assert fake_provider.fetch_rejected_bars_calls == [("SPY", date(2026, 1, 2), date(2026, 1, 5))]


def test_main_does_not_fetch_conflicts_for_ibkr_or_yahoo_providers(tmp_path):
    for provider_name in (cli.PROVIDER_IBKR, cli.PROVIDER_YAHOO):
        fake_provider = _FakeProviderTrackingQuantDataFetches()

        exit_code = cli.main(
            ["SPY", "--date", "2026-01-02", "--provider", provider_name],
            provider=fake_provider,
            settings_path=SETTINGS_PATH,
            output_dir=tmp_path,
            show_chart=lambda ticker, days, conflicts=None, rejected_bars=None: None,
        )

        assert exit_code == 0
        assert fake_provider.fetch_conflicts_calls == []
        assert fake_provider.fetch_rejected_bars_calls == []


def test_main_passes_conflicts_through_to_show_chart(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()
    shown_calls = []

    cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "quant-data"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None: shown_calls.append(conflicts),
    )

    assert shown_calls == [[]]  # fake provider reports no conflicts, but the parameter is still threaded through


def test_main_passes_rejected_bars_through_to_show_chart(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()
    shown_calls = []

    cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "quant-data"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None: shown_calls.append(rejected_bars),
    )

    assert shown_calls == [[]]  # fake provider reports none rejected, but the parameter is still threaded through


def test_main_passes_empty_conflicts_for_ibkr_provider(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()
    shown_calls = []

    cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "ibkr"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None: shown_calls.append(conflicts),
    )

    assert shown_calls == [[]]
