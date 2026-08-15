from __future__ import annotations

from pathlib import Path

import pytest

from open_quant_data import cli
from shared.errors import AppError
from shared.settings import PostgresSettings

SETTINGS_PATH = Path(__file__).parent.parent / "data" / "settings.json"

_POSTGRES_SETTINGS = PostgresSettings(
    host="example-host",
    port=5432,
    user="quant_reader",
    password="",
    dbname="quant_data",
    ssh_user="alex",
    ssh_key_path="/fake/key",
)


class _FakeTunnel:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def test_parse_args_returns_spreadsheet_path():
    arguments = cli.parse_args(["public/reports/quant_data_dashboard.xlsx"])

    assert arguments.spreadsheet == "public/reports/quant_data_dashboard.xlsx"


def test_parse_args_exits_two_on_missing_argument():
    with pytest.raises(SystemExit) as exc_info:
        cli.parse_args([])

    assert exc_info.value.code == 2


def test_start_tunnel_reuses_already_open_port():
    factory_called = False

    def fake_factory(host: str, ssh_user: str, ssh_key_path: str, remote_port: int, local_port: int) -> _FakeTunnel:
        nonlocal factory_called
        factory_called = True
        return _FakeTunnel()

    tunnel = cli.start_tunnel(_POSTGRES_SETTINGS, port_checker=lambda host, port: True, tunnel_factory=fake_factory)

    assert tunnel is None
    assert factory_called is False


def test_start_tunnel_raises_when_ssh_settings_missing():
    postgres_settings = PostgresSettings(host="example-host", port=5432, user="quant_reader", password="", dbname="quant_data")

    with pytest.raises(AppError, match="sshUser"):
        cli.start_tunnel(postgres_settings, port_checker=lambda host, port: False)


def test_start_tunnel_raises_when_postgres_settings_missing():
    with pytest.raises(AppError, match="sshUser"):
        cli.start_tunnel(None, port_checker=lambda host, port: False)


def test_start_tunnel_opens_tunnel_with_settings():
    captured_args = {}

    def fake_factory(host: str, ssh_user: str, ssh_key_path: str, remote_port: int, local_port: int) -> _FakeTunnel:
        captured_args.update(host=host, ssh_user=ssh_user, ssh_key_path=ssh_key_path, remote_port=remote_port, local_port=local_port)
        return _FakeTunnel()

    tunnel = cli.start_tunnel(_POSTGRES_SETTINGS, port_checker=lambda host, port: False, tunnel_factory=fake_factory, port=5433)

    assert isinstance(tunnel, _FakeTunnel)
    assert captured_args == {
        "host": "example-host",
        "ssh_user": "alex",
        "ssh_key_path": "/fake/key",
        "remote_port": 5432,
        "local_port": 5433,
    }


def test_stop_tunnel_stops_tunnel():
    fake_tunnel = _FakeTunnel()

    cli.stop_tunnel(fake_tunnel)

    assert fake_tunnel.stopped is True


def test_stop_tunnel_ignores_none():
    cli.stop_tunnel(None)


def test_open_spreadsheet_raises_when_missing():
    with pytest.raises(AppError, match="not found"):
        cli.open_spreadsheet("does/not/exist.xlsx")


def test_open_spreadsheet_calls_opener_when_present(tmp_path):
    workbook = tmp_path / "dashboard.xlsx"
    workbook.write_text("placeholder")
    opened_paths = []

    cli.open_spreadsheet(str(workbook), opener=opened_paths.append)

    assert opened_paths == [str(workbook)]


def test_wait_for_excel_to_close_returns_when_excel_never_starts():
    cli.wait_for_excel_to_close(
        is_excel_running=lambda: False,
        sleep_fn=lambda seconds: None,
        startup_timeout_sec=0.0,
    )


def test_wait_for_excel_to_close_returns_once_excel_exits():
    calls = {"count": 0}

    def fake_is_running() -> bool:
        calls["count"] += 1
        return calls["count"] <= 3

    cli.wait_for_excel_to_close(is_excel_running=fake_is_running, sleep_fn=lambda seconds: None)

    assert calls["count"] == 4


def test_wait_for_excel_to_close_handles_keyboard_interrupt():
    def raise_interrupt(seconds: float) -> None:
        raise KeyboardInterrupt

    cli.wait_for_excel_to_close(is_excel_running=lambda: True, sleep_fn=raise_interrupt)


def test_main_happy_path_returns_zero(monkeypatch, tmp_path):
    workbook = tmp_path / "dashboard.xlsx"
    workbook.write_text("placeholder")
    monkeypatch.setattr(cli, "start_tunnel", lambda postgres_settings: None)
    monkeypatch.setattr(cli, "_default_opener", lambda path: None)

    exit_code = cli.main([str(workbook)], keep_alive=lambda: None, settings_path=SETTINGS_PATH)

    assert exit_code == 0


def test_main_returns_one_when_tunnel_fails(monkeypatch, capsys, tmp_path):
    workbook = tmp_path / "dashboard.xlsx"
    workbook.write_text("placeholder")

    def failing_start_tunnel(postgres_settings):
        raise AppError("tunnel exploded")

    monkeypatch.setattr(cli, "start_tunnel", failing_start_tunnel)

    exit_code = cli.main([str(workbook)], keep_alive=lambda: None, settings_path=SETTINGS_PATH)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "tunnel exploded" in captured.err


def test_main_returns_one_when_spreadsheet_missing(monkeypatch):
    monkeypatch.setattr(cli, "start_tunnel", lambda postgres_settings: None)

    exit_code = cli.main(["does/not/exist.xlsx"], keep_alive=lambda: None, settings_path=SETTINGS_PATH)

    assert exit_code == 1
