from __future__ import annotations

import pytest

from shared.errors import AppError
from stock_quote import cli
from stock_quote.protocols import StockQuote


def test_main_prints_csv_and_returns_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def fake_fetch_quote(ticker: str) -> StockQuote:
        return StockQuote(ticker=ticker.upper(), price=100.0, timestamp="2026-01-01T00:00:00+00:00", volume=42)

    monkeypatch.setattr(cli, "fetch_quote", fake_fetch_quote)

    exit_code = cli.main(["aapl"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ticker,price,timestamp,volume" in captured.out
    assert "AAPL,100.0,2026-01-01T00:00:00+00:00,42" in captured.out


def test_main_returns_one_on_fetch_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def fake_fetch_quote(ticker: str) -> StockQuote:
        raise AppError(f"No quote data available for '{ticker}'.")

    monkeypatch.setattr(cli, "fetch_quote", fake_fetch_quote)

    exit_code = cli.main(["BADTICKER"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error" in captured.err


def test_main_exits_two_on_missing_argument(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        cli.main([])

    assert exc_info.value.code == 2
