from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from day_chart import cli
from defs.protocols import DayBar, QuoteBar
from shared.settings import DatabentoSettings, IBKRSettings, MassiveSettings, Settings
from tests.mocks.quant_data import MockQuantDataIntraDay

SETTINGS_PATH = Path(__file__).parent.parent / "data" / "settings.json"


class _FakeProviderTrackingQuantDataFetches:
    def __init__(self):
        self.fetch_conflicts_calls: list[tuple[str, date, date]] = []
        self.fetch_rejected_bars_calls: list[tuple[str, date, date]] = []
        self.fetch_quote_bars_calls: list[tuple[str, date]] = []

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

    def fetch_quote_bars(self, ticker: str, target_date: date) -> list[QuoteBar]:
        self.fetch_quote_bars_calls.append((ticker, target_date))
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


def test_resolve_session_date_default_lookback_shifts_back_by_n_days():
    # 2026-01-06 is a Tuesday; shifting back 1 day lands on Monday 2026-01-05, a normal weekday --
    # no further rollback needed.
    resolved = cli.resolve_session_date(None, today=date(2026, 1, 6), default_lookback_days=1)

    assert resolved == date(2026, 1, 5)


def test_resolve_session_date_default_lookback_still_rolls_back_over_a_weekend():
    # 2026-01-05 is a Monday; shifting back 1 day lands on Sunday 2026-01-04, which itself rolls
    # back to Friday 2026-01-02 -- the same "last trading day" logic still applies after the shift.
    resolved = cli.resolve_session_date(None, today=date(2026, 1, 5), default_lookback_days=1)

    assert resolved == date(2026, 1, 2)


def test_resolve_session_date_default_lookback_ignored_when_date_given_explicitly():
    resolved = cli.resolve_session_date("2026-01-05", today=date(2026, 1, 6), default_lookback_days=1)

    assert resolved == date(2026, 1, 5)


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


def test_resolve_date_range_default_lookback_shifts_end_back_by_n_days():
    resolved = cli.resolve_date_range("2026-01-02", None, today=date(2026, 1, 6), default_lookback_days=1)

    # end defaults to 2026-01-05 (Tuesday minus 1 day), not today's last trading day.
    assert resolved == [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4), date(2026, 1, 5)]


def test_resolve_date_range_default_lookback_ignored_when_end_date_given_explicitly():
    resolved = cli.resolve_date_range(None, "2026-01-05", today=date(2026, 1, 6), default_lookback_days=1)

    assert resolved == [date(2026, 1, 5)]


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
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: shown_calls.append((ticker, days)),
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
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: shown_calls.append((ticker, days)),
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
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: shown_calls.append((ticker, days)),
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


def test_build_provider_massive_raises_when_massive_settings_missing():
    settings = Settings(debug=False)  # massive defaults to None

    with pytest.raises(cli.AppError):
        cli._build_provider(cli.PROVIDER_MASSIVE, settings)


def test_build_provider_massive_forwards_settings_fields(monkeypatch):
    captured_kwargs = {}

    class FakeMassiveIntraDay:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(cli, "MassiveIntraDay", FakeMassiveIntraDay)
    settings = Settings(debug=False, massive=MassiveSettings(api_key="massive-test-key"))

    provider = cli._build_provider(cli.PROVIDER_MASSIVE, settings)

    assert isinstance(provider, FakeMassiveIntraDay)
    assert captured_kwargs == {"api_key": "massive-test-key"}


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


def test_main_range_mode_warns_but_proceeds_for_oversized_massive_range(monkeypatch, tmp_path):
    # Reuses MockQuantDataIntraDay as a stand-in fetch source (same pattern as the quant-data cap
    # test below) -- only its fixture-backed days (01-02, 01-05) actually chart, the rest are
    # dropped by the ordinary per-day-skip path, same as any other provider with partial data.
    warnings = []
    monkeypatch.setattr(cli.Logger, "warning", lambda message, category=None: warnings.append((message, category)))

    exit_code = cli.main(
        ["SPY", "--start-date", "2026-01-01", "--end-date", "2026-01-10", "--provider", "massive"],  # > 5 days
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: None,
    )

    assert exit_code == 0
    soft_limit_warnings = [message for message, category in warnings if "soft limit" in message]
    assert len(soft_limit_warnings) == 1
    assert "5-day soft limit" in soft_limit_warnings[0]


def test_main_passes_massive_default_lookback_to_resolve_session_date(monkeypatch, tmp_path):
    # Massive's free tier has no same-day data (confirmed live -- see issue #26's discussion) --
    # when no --date is given, --provider massive should shift the default back a day rather than
    # resolving to today/last-trading-day the way every other provider does.
    real_resolve_session_date = cli.resolve_session_date
    captured_kwargs = []

    def spy_resolve_session_date(date_argument, today=None, default_lookback_days=0):
        captured_kwargs.append(default_lookback_days)
        return real_resolve_session_date(date_argument, today, default_lookback_days)

    monkeypatch.setattr(cli, "resolve_session_date", spy_resolve_session_date)

    cli.main(
        ["SPY", "--provider", "massive"],
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
    )

    assert captured_kwargs == [cli.MASSIVE_DEFAULT_LOOKBACK_DAYS]


def test_main_passes_zero_lookback_to_resolve_session_date_for_ibkr(monkeypatch, tmp_path):
    real_resolve_session_date = cli.resolve_session_date
    captured_kwargs = []

    def spy_resolve_session_date(date_argument, today=None, default_lookback_days=0):
        captured_kwargs.append(default_lookback_days)
        return real_resolve_session_date(date_argument, today, default_lookback_days)

    monkeypatch.setattr(cli, "resolve_session_date", spy_resolve_session_date)

    cli.main(
        ["SPY", "--provider", "ibkr"],
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
    )

    assert captured_kwargs == [0]


def test_main_range_mode_ibkr_cap_does_not_apply_to_quant_data_provider(tmp_path):
    # Same oversized range as above, but --provider quant-data has no pacing constraint to cap --
    # only the two fixture-backed days (01-02, 01-05) actually chart, and the command still succeeds.
    exit_code = cli.main(
        ["SPY", "--start-date", "2026-01-01", "--end-date", "2026-03-01", "--provider", "quant-data"],
        provider=MockQuantDataIntraDay(),
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: None,
    )

    assert exit_code == 0


def test_main_fetches_conflicts_for_quant_data_provider_single_day(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()

    exit_code = cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "quant-data"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: None,
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
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: None,
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
            show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: None,
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
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: shown_calls.append(conflicts),
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
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: shown_calls.append(rejected_bars),
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
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: shown_calls.append(conflicts),
    )

    assert shown_calls == [[]]


def test_main_fetches_quote_bars_for_ibkr_provider_single_day(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()

    exit_code = cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "ibkr"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: None,
    )

    assert exit_code == 0
    assert fake_provider.fetch_quote_bars_calls == [("SPY", date(2026, 1, 2))]


def test_main_fetches_quote_bars_once_per_day_in_range_mode(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()

    exit_code = cli.main(
        ["SPY", "--start-date", "2026-01-02", "--end-date", "2026-01-03", "--provider", "ibkr"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: None,
    )

    assert exit_code == 0
    assert fake_provider.fetch_quote_bars_calls == [("SPY", date(2026, 1, 2)), ("SPY", date(2026, 1, 3))]


def test_main_does_not_fetch_quote_bars_for_yahoo_provider(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()

    exit_code = cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", cli.PROVIDER_YAHOO],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: None,
    )

    assert exit_code == 0
    assert fake_provider.fetch_quote_bars_calls == []


def test_main_fetches_quote_bars_for_quant_data_provider(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()

    exit_code = cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "quant-data"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: None,
    )

    assert exit_code == 0
    assert fake_provider.fetch_quote_bars_calls == [("SPY", date(2026, 1, 2))]


def test_main_reaches_quant_data_quote_bars_via_both_csv_and_chart(tmp_path):
    # Unlike massive, quant-data can populate avg_bid/avg_ask (IBKR-sourced under the hood) -- it
    # gets the same bid/ask chart panel ibkr does, not the CSV-only treatment massive gets.
    quote_bar = QuoteBar(
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        wap=None,
        trade_count=None,
        avg_bid=471.4,
        avg_ask=471.6,
        midpoint_open=471.45,
        midpoint_high=471.75,
        midpoint_low=471.35,
        midpoint_close=471.55,
    )

    class _FakeQuantDataProvider(_FakeProviderTrackingQuantDataFetches):
        def fetch_quote_bars(self, ticker: str, target_date: date) -> list[QuoteBar]:
            self.fetch_quote_bars_calls.append((ticker, target_date))
            return [quote_bar]

    fake_provider = _FakeQuantDataProvider()
    shown_calls = []

    cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "quant-data"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: shown_calls.append(quote_bars),
    )

    assert shown_calls == [[quote_bar]]

    csv_path = tmp_path / "SPY_2026-01-02_data.csv"
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "471.4,471.6,471.45,471.75,471.35,471.55" in csv_text


def test_main_passes_quote_bars_through_to_show_chart_and_csv(tmp_path):
    quote_bar = QuoteBar(
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        wap=1.5,
        trade_count=10,
        avg_bid=0.9,
        avg_ask=1.1,
        midpoint_open=None,
        midpoint_high=None,
        midpoint_low=None,
        midpoint_close=None,
    )

    class _FakeIBKRProvider(_FakeProviderTrackingQuantDataFetches):
        def fetch_quote_bars(self, ticker: str, target_date: date) -> list[QuoteBar]:
            self.fetch_quote_bars_calls.append((ticker, target_date))
            return [quote_bar]

    fake_provider = _FakeIBKRProvider()
    shown_calls = []

    cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "ibkr"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: shown_calls.append(quote_bars),
    )

    assert shown_calls == [[quote_bar]]

    csv_path = tmp_path / "SPY_2026-01-02_data.csv"
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "1.5,10,0.9,1.1" in csv_text


def test_main_passes_none_quote_bars_to_show_chart_when_none_fetched(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()
    shown_calls = []

    cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "ibkr"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: shown_calls.append(quote_bars),
    )

    assert shown_calls == [None]


def test_main_fetches_quote_bars_for_massive_provider(tmp_path):
    fake_provider = _FakeProviderTrackingQuantDataFetches()

    exit_code = cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "massive"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: None,
    )

    assert exit_code == 0
    assert fake_provider.fetch_quote_bars_calls == [("SPY", date(2026, 1, 2))]


def test_main_reaches_massive_quote_bars_via_csv_but_not_the_chart(tmp_path):
    # Per the user's explicit call: Massive/yfinance charts stay exactly as they are (no bid/ask
    # panel -- Massive never has avg_bid/avg_ask anyway) -- only the CSV export gains the new
    # wap/trade_count columns for --provider massive.
    quote_bar = QuoteBar(
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        wap=471.9,
        trade_count=42,
        avg_bid=None,
        avg_ask=None,
        midpoint_open=None,
        midpoint_high=None,
        midpoint_low=None,
        midpoint_close=None,
    )

    class _FakeMassiveProvider(_FakeProviderTrackingQuantDataFetches):
        def fetch_quote_bars(self, ticker: str, target_date: date) -> list[QuoteBar]:
            self.fetch_quote_bars_calls.append((ticker, target_date))
            return [quote_bar]

    fake_provider = _FakeMassiveProvider()
    shown_calls = []

    cli.main(
        ["SPY", "--date", "2026-01-02", "--provider", "massive"],
        provider=fake_provider,
        settings_path=SETTINGS_PATH,
        output_dir=tmp_path,
        show_chart=lambda ticker, days, conflicts=None, rejected_bars=None, quote_bars=None: shown_calls.append(quote_bars),
    )

    # Chart never sees Massive's quote_bars -- no bid/ask panel for this provider.
    assert shown_calls == [None]

    csv_path = tmp_path / "SPY_2026-01-02_data.csv"
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "471.9,42,," in csv_text
