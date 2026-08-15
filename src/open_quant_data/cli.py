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
from pathlib import Path

import paramiko

# sshtunnel 0.4.0 (its latest PyPI release, last published 2021) unconditionally references
# paramiko.DSSKey while building an internal key-type lookup table used to scan for default keys --
# paramiko removed DSSKey (DSA key support) entirely in a later major version, since DSA is
# deprecated/insecure. This crashes even though we're ed25519-only, because the lookup table is
# built eagerly for every key type regardless of which one is actually in use. Shimming the
# attribute (rather than downgrading paramiko to an EOL version with since-fixed CVEs) is the
# standard workaround -- mirrors the same shim quant-data's own internal SSH transport applies.
if not hasattr(paramiko, "DSSKey"):
    paramiko.DSSKey = paramiko.RSAKey

from sshtunnel import SSHTunnelForwarder  # noqa: E402

from shared.diagnostics import ConsoleLogSink, Logger, TelemetryLevel  # noqa: E402
from shared.errors import AppError  # noqa: E402
from shared.settings import PostgresSettings, Settings  # noqa: E402

CATEGORY_TUNNEL = "tunnel"

SSH_PORT = 22
# Local port the tunnel binds to; must match the ODBC DSN's configured port. Fixed (not an
# ephemeral OS-assigned port, unlike quant-data's own internal SSH transport) since the DSN is
# pre-configured in Windows to always look for Postgres at this specific local address.
LOCAL_PORT = 5433

EXCEL_PROCESS_NAME = "EXCEL.EXE"
EXCEL_STARTUP_TIMEOUT_SEC = 15.0
EXCEL_POLL_INTERVAL_SEC = 1.0

PortChecker = Callable[[str, int], bool]
TunnelFactory = Callable[[str, str, str, int, int], SSHTunnelForwarder]
Opener = Callable[[str], None]
KeepAliveFn = Callable[[], None]
ProcessRunningChecker = Callable[[], bool]


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


def _open_tunnel(host: str, ssh_user: str, ssh_key_path: str, remote_port: int, local_port: int) -> SSHTunnelForwarder:
    try:
        tunnel = SSHTunnelForwarder(
            (host, SSH_PORT),
            ssh_username=ssh_user,
            ssh_pkey=ssh_key_path,
            remote_bind_address=("localhost", remote_port),
            local_bind_address=("127.0.0.1", local_port),
        )
        tunnel.start()
    except Exception as error:
        raise AppError(f"Failed to open SSH tunnel to {host} as {ssh_user} (key: {ssh_key_path}): {error}") from error

    return tunnel


def start_tunnel(
    postgres_settings: PostgresSettings | None,
    port_checker: PortChecker | None = None,
    tunnel_factory: TunnelFactory | None = None,
    port: int = LOCAL_PORT,
) -> SSHTunnelForwarder | None:
    """Opens an SSH tunnel forwarding local `port` to Postgres on `postgres_settings`'s remote
    box, using the same sshtunnel/paramiko mechanism quant-data's own auto-tunnel uses internally
    -- no PuTTY/plink involved. Returns the opened tunnel, or None if `port` was already accepting
    connections (nothing for the caller to manage)."""
    check_port = _port_is_open if port_checker is None else port_checker
    open_tunnel = _open_tunnel if tunnel_factory is None else tunnel_factory

    if check_port("localhost", port):
        Logger.info(f"Tunnel already up on port {port}, reusing it.", category=CATEGORY_TUNNEL)
        return None

    if postgres_settings is None or postgres_settings.ssh_user is None or postgres_settings.ssh_key_path is None:
        raise AppError(
            "open-quant-data needs a 'postgres' section in settings.local.json with 'sshUser'/'sshKeyPath' set "
            "so it can open its own SSH tunnel -- see docs/PROTOCOL.md's 'postgres' settings section."
        )

    Logger.info(f"Opening SSH tunnel to {postgres_settings.host} as {postgres_settings.ssh_user}...", category=CATEGORY_TUNNEL)
    tunnel = open_tunnel(postgres_settings.host, postgres_settings.ssh_user, postgres_settings.ssh_key_path, postgres_settings.port, port)
    Logger.info("Tunnel is up.", category=CATEGORY_TUNNEL)
    return tunnel


def stop_tunnel(tunnel: SSHTunnelForwarder | None) -> None:
    if tunnel is not None:
        Logger.info("Closing SSH tunnel...", category=CATEGORY_TUNNEL)
        tunnel.stop()


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


def _excel_is_running() -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {EXCEL_PROCESS_NAME}", "/NH"],
        capture_output=True,
        text=True,
    )
    return EXCEL_PROCESS_NAME in result.stdout


def wait_for_excel_to_close(
    is_excel_running: ProcessRunningChecker | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    startup_timeout_sec: float = EXCEL_STARTUP_TIMEOUT_SEC,
    poll_interval_sec: float = EXCEL_POLL_INTERVAL_SEC,
) -> None:
    """Blocks until Excel closes. Waits for EXCEL.EXE to first appear (confirming it actually
    launched) before waiting for it to disappear again -- if it never appears within
    `startup_timeout_sec`, gives up waiting and returns rather than blocking forever."""
    check_running = _excel_is_running if is_excel_running is None else is_excel_running
    sleep = time.sleep if sleep_fn is None else sleep_fn

    deadline = time.time() + startup_timeout_sec
    started = False
    while time.time() < deadline:
        if check_running():
            started = True
            break
        sleep(poll_interval_sec)

    if not started:
        Logger.warning(
            f"Excel didn't appear to start within {startup_timeout_sec}s; exiting without waiting for it to close.",
            category=CATEGORY_TUNNEL,
        )
        return

    print("\nExcel is open. This will exit automatically once you close Excel (or press Ctrl+C to close the tunnel manually).")
    try:
        while check_running():
            sleep(poll_interval_sec)
    except KeyboardInterrupt:
        pass


def main(
    argv: list[str] | None = None,
    keep_alive: KeepAliveFn | None = None,
    settings_path: Path | None = None,
) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        settings = Settings.load() if settings_path is None else Settings.load(path=settings_path)
    except AppError as error:
        print(f"open-quant-data: error: {error}", file=sys.stderr)
        return 1

    Logger.set_logger(ConsoleLogSink(min_level=TelemetryLevel.INFO))
    wait = wait_for_excel_to_close if keep_alive is None else keep_alive
    try:
        tunnel = start_tunnel(settings.postgres)
        atexit.register(stop_tunnel, tunnel)

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
