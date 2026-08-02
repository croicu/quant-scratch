from __future__ import annotations

from pathlib import Path

import pytest

from shared.settings import IBKRSettings, Settings
from stock_quote import cli
from tests.mocks.yahoo_finance import MockYahooFinance

SETTINGS_PATH = Path(__file__).parent.parent / "data" / "settings.json"


def test_main_prints_csv_and_returns_zero(capsys):
    exit_code = cli.main(["aapl"], provider=MockYahooFinance(), settings_path=SETTINGS_PATH)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ticker,price,timestamp,volume,provider,delayed" in captured.out
    assert "AAPL,150.25," in captured.out
    assert captured.out.strip().endswith(",1000000,yahoo,False")


def test_main_returns_one_on_fetch_error(capsys):
    exit_code = cli.main(["NOTINFIXTURE"], provider=MockYahooFinance(), settings_path=SETTINGS_PATH)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error" in captured.err


def test_main_exits_two_on_missing_argument():
    with pytest.raises(SystemExit) as exc_info:
        cli.main([])

    assert exc_info.value.code == 2


def test_build_provider_yahoo_is_default():
    settings = Settings(debug=False)

    provider = cli._build_provider(cli.PROVIDER_YAHOO, settings)

    assert type(provider).__name__ == "YahooFinance"


def test_build_provider_ibkr_uses_defaults_when_no_ibkr_settings(monkeypatch):
    captured_kwargs = {}

    class FakeIBKRQuote:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(cli, "IBKRQuote", FakeIBKRQuote)
    settings = Settings(debug=False)  # ibkr defaults to None

    provider = cli._build_provider(cli.PROVIDER_IBKR, settings)

    assert isinstance(provider, FakeIBKRQuote)
    assert captured_kwargs == {}


def test_build_provider_ibkr_forwards_settings_ibkr_fields(monkeypatch):
    captured_kwargs = {}

    class FakeIBKRQuote:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(cli, "IBKRQuote", FakeIBKRQuote)
    settings = Settings(debug=False, ibkr=IBKRSettings(host="10.0.0.5", port=4001, client_id=9))

    cli._build_provider(cli.PROVIDER_IBKR, settings)

    assert captured_kwargs == {"host": "10.0.0.5", "port": 4001, "client_id": 9}
