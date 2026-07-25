from __future__ import annotations

from pathlib import Path

import pytest

from stock_quote import cli
from tests.mocks.yahoo_finance import MockYahooFinance

SETTINGS_PATH = Path(__file__).parent.parent / "data" / "settings.json"


def test_main_prints_csv_and_returns_zero(capsys):
    exit_code = cli.main(["aapl"], provider=MockYahooFinance(), settings_path=SETTINGS_PATH)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ticker,price,timestamp,volume" in captured.out
    assert "AAPL,150.25," in captured.out
    assert captured.out.strip().endswith(",1000000")


def test_main_returns_one_on_fetch_error(capsys):
    exit_code = cli.main(["NOTINFIXTURE"], provider=MockYahooFinance(), settings_path=SETTINGS_PATH)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error" in captured.err


def test_main_exits_two_on_missing_argument():
    with pytest.raises(SystemExit) as exc_info:
        cli.main([])

    assert exc_info.value.code == 2
