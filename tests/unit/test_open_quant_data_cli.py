from __future__ import annotations

import subprocess

import pytest

from open_quant_data import cli
from shared.errors import AppError


class _FakeProcess:
    def __init__(self, exited: bool = False) -> None:
        self._exited = exited
        self.terminated = False

    def poll(self) -> int | None:
        return 1 if self._exited else None

    def terminate(self) -> None:
        self.terminated = True


def test_parse_args_returns_spreadsheet_path():
    arguments = cli.parse_args(["public/reports/quant_data_dashboard.xlsx"])

    assert arguments.spreadsheet == "public/reports/quant_data_dashboard.xlsx"


def test_parse_args_exits_two_on_missing_argument():
    with pytest.raises(SystemExit) as exc_info:
        cli.parse_args([])

    assert exc_info.value.code == 2


def test_start_tunnel_reuses_already_open_port():
    launcher_called = False

    def fake_launcher(session: str) -> subprocess.Popen:
        nonlocal launcher_called
        launcher_called = True
        return _FakeProcess()

    process = cli.start_tunnel(port_checker=lambda host, port: True, process_launcher=fake_launcher)

    assert process is None
    assert launcher_called is False


def test_start_tunnel_launches_and_waits_for_port():
    fake_process = _FakeProcess()
    check_calls = {"count": 0}

    def fake_checker(host: str, port: int) -> bool:
        check_calls["count"] += 1
        return check_calls["count"] > 1

    def fake_launcher(session: str) -> subprocess.Popen:
        return fake_process

    process = cli.start_tunnel(
        port_checker=fake_checker,
        process_launcher=fake_launcher,
        sleep_fn=lambda seconds: None,
    )

    assert process is fake_process


def test_start_tunnel_raises_when_process_exits_early():
    def fake_launcher(session: str) -> subprocess.Popen:
        return _FakeProcess(exited=True)

    with pytest.raises(AppError, match="plink exited"):
        cli.start_tunnel(
            port_checker=lambda host, port: False,
            process_launcher=fake_launcher,
            sleep_fn=lambda seconds: None,
        )


def test_start_tunnel_raises_on_timeout():
    def fake_launcher(session: str) -> subprocess.Popen:
        return _FakeProcess()

    with pytest.raises(AppError, match="didn't come up"):
        cli.start_tunnel(
            port_checker=lambda host, port: False,
            process_launcher=fake_launcher,
            sleep_fn=lambda seconds: None,
            timeout_sec=0.0,
        )


def test_stop_tunnel_terminates_running_process():
    fake_process = _FakeProcess(exited=False)

    cli.stop_tunnel(fake_process)

    assert fake_process.terminated is True


def test_stop_tunnel_ignores_already_exited_process():
    fake_process = _FakeProcess(exited=True)

    cli.stop_tunnel(fake_process)

    assert fake_process.terminated is False


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


def test_main_happy_path_returns_zero(monkeypatch, tmp_path):
    workbook = tmp_path / "dashboard.xlsx"
    workbook.write_text("placeholder")
    monkeypatch.setattr(cli, "start_tunnel", lambda: None)
    monkeypatch.setattr(cli, "_default_opener", lambda path: None)

    exit_code = cli.main([str(workbook)], keep_alive=lambda: None)

    assert exit_code == 0


def test_main_returns_one_when_tunnel_fails(monkeypatch, capsys, tmp_path):
    workbook = tmp_path / "dashboard.xlsx"
    workbook.write_text("placeholder")

    def failing_start_tunnel():
        raise AppError("tunnel exploded")

    monkeypatch.setattr(cli, "start_tunnel", failing_start_tunnel)

    exit_code = cli.main([str(workbook)], keep_alive=lambda: None)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "tunnel exploded" in captured.err


def test_main_returns_one_when_spreadsheet_missing(monkeypatch):
    monkeypatch.setattr(cli, "start_tunnel", lambda: None)

    exit_code = cli.main(["does/not/exist.xlsx"], keep_alive=lambda: None)

    assert exit_code == 1
