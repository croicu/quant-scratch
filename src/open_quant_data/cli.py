from __future__ import annotations

import argparse
import atexit
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

from shared.diagnostics import ConsoleLogSink, Logger, TelemetryLevel
from shared.errors import AppError

CATEGORY_TUNNEL = "tunnel"

# Name of the saved PuTTY session (see tasks/excel_postgres_ssh_automation.md / issue #19 for the
# one-time manual setup). The remote host/port/key live only in that saved session, never here or
# in any committed file.
PLINK_SESSION = "quant-tunnel"
# Local port the tunnel forwards to Postgres; must match the ODBC DSN's configured port.
LOCAL_PORT = 5433
TUNNEL_TIMEOUT_SEC = 15.0
TUNNEL_POLL_INTERVAL_SEC = 0.5

PortChecker = Callable[[str, int], bool]
ProcessLauncher = Callable[[str], subprocess.Popen]
Opener = Callable[[str], None]
KeepAliveFn = Callable[[], None]


@dataclass
class CliArguments:
    spreadsheet: str


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog="open-quant-data",
        usage="open-quant-data SPREADSHEET",
        description="Open an SSH-tunneled ODBC connection to quant-data's Postgres warehouse, then open the given Excel workbook.",
    )
    parser.add_argument("spreadsheet", help="path to the .xlsx workbook to open, e.g. public/reports/quant_data_dashboard.xlsx")

    args = parser.parse_args(argv)

    return CliArguments(spreadsheet=args.spreadsheet)


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def _launch_plink(session: str) -> subprocess.Popen:
    return subprocess.Popen(
        ["plink", "-load", session, "-N", "-batch"],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def start_tunnel(
    port_checker: PortChecker | None = None,
    process_launcher: ProcessLauncher | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    session: str = PLINK_SESSION,
    port: int = LOCAL_PORT,
    timeout_sec: float = TUNNEL_TIMEOUT_SEC,
) -> subprocess.Popen | None:
    """Launch plink using the saved PuTTY session, forwarding `port`. Returns the launched
    process, or None if a tunnel was already up (nothing for the caller to manage)."""
    check_port = _port_is_open if port_checker is None else port_checker
    launch = _launch_plink if process_launcher is None else process_launcher
    sleep = time.sleep if sleep_fn is None else sleep_fn

    if check_port("localhost", port):
        Logger.info(f"Tunnel already up on port {port}, reusing it.", category=CATEGORY_TUNNEL)
        return None

    Logger.info(f"Starting SSH tunnel (session '{session}')...", category=CATEGORY_TUNNEL)
    process = launch(session)

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if check_port("localhost", port):
            Logger.info("Tunnel is up.", category=CATEGORY_TUNNEL)
            return process
        if process.poll() is not None:
            raise AppError(
                "plink exited before the tunnel came up. Run "
                f"'plink -load {session} -N' manually to see the error "
                "(likely an unrecognized host key or auth failure)."
            )
        sleep(TUNNEL_POLL_INTERVAL_SEC)

    raise AppError(f"Tunnel didn't come up within {timeout_sec}s on port {port}.")


def stop_tunnel(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        Logger.info("Closing SSH tunnel...", category=CATEGORY_TUNNEL)
        process.terminate()


def _default_opener(path: str) -> None:
    if os.name == "nt":
        os.startfile(path)  # noqa: S606 - intentional, opens in the OS-associated app (Excel)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def open_spreadsheet(path: str, opener: Opener | None = None) -> None:
    if not os.path.exists(path):
        raise AppError(f"Spreadsheet not found at {path}")

    open_with = _default_opener if opener is None else opener
    Logger.info(f"Opening {path} ...", category=CATEGORY_TUNNEL)
    open_with(path)


def _wait_until_interrupted() -> None:
    print("\nTunnel is running in the background. Leave this terminal open while you work in Excel. Press Ctrl+C here to close the tunnel and exit.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass


def main(argv: list[str] | None = None, keep_alive: KeepAliveFn | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)

    Logger.set_logger(ConsoleLogSink(min_level=TelemetryLevel.INFO))
    wait = _wait_until_interrupted if keep_alive is None else keep_alive
    try:
        process = start_tunnel()
        atexit.register(stop_tunnel, process)

        open_spreadsheet(arguments.spreadsheet)

        wait()
        return 0
    except AppError as error:
        print(f"open-quant-data: error: {error}", file=sys.stderr)
        return 1
    finally:
        Logger.set_logger(None)


if __name__ == "__main__":
    raise SystemExit(main())
