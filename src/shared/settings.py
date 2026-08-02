from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from .diagnostics import CATEGORY_GENERAL, TelemetryLevel
from .errors import TaskError

_SETTINGS_PATH = Path("./settings.json")
_LOCAL_FILENAME = "settings.local.json"


@dataclass
class PostgresSettings:
    host: str
    port: int
    user: str
    password: str
    dbname: str
    ssh_user: str | None = None
    ssh_key_path: str | None = None


@dataclass
class WindowSettings:
    x: int
    y: int


@dataclass
class IBKRSettings:
    # Unlike PostgresSettings, every field already has a genuinely usable default (matching
    # IBKRIntraDay's own constructor defaults for the one local paper-Gateway setup this repo
    # targets) -- this section exists to override those defaults for a different setup, not
    # because they need replacing, so no required-keys validation applies to it.
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 1


@dataclass
class Settings:
    debug: bool
    logging: TelemetryLevel = TelemetryLevel.ERROR
    log_categories: list[str] = field(default_factory=list)
    excluded_categories: list[str] = field(default_factory=list)
    postgres: PostgresSettings | None = None
    ibkr: IBKRSettings | None = None
    window: WindowSettings | None = None

    _instance: ClassVar[Settings | None] = None

    @classmethod
    def load(cls, path: Path = _SETTINGS_PATH, local_path: Path | None = None) -> Settings:
        # local_path defaults to a settings.local.json sibling of `path`, not a fixed repo-root
        # path -- otherwise a test/consumer passing a custom `path` (e.g. a fixture settings.json)
        # would still silently pick up whatever real settings.local.json happens to sit at the
        # real cwd's repo root, breaking isolation.
        active_local_path = (path.parent / _LOCAL_FILENAME) if local_path is None else local_path

        debug = False
        log_level = TelemetryLevel.ERROR
        log_categories: list[str] = []
        excluded_categories: list[str] = []

        settings_payload: dict = {}

        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                settings_file = json.load(f)
            if not isinstance(settings_file, dict):
                raise TaskError("settings.json must contain a JSON object.")
            base_settings = settings_file.get("settings", {})
            if not isinstance(base_settings, dict):
                raise TaskError("'settings' in settings.json must be a JSON object.")
            settings_payload = dict(base_settings)

        if active_local_path.exists():
            with active_local_path.open("r", encoding="utf-8") as f:
                local_payload = json.load(f)
            if isinstance(local_payload, dict):
                local_settings = local_payload.get("settings", {})
                if isinstance(local_settings, dict):
                    settings_payload.update(local_settings)

        if settings_payload:
            debug = bool(settings_payload.get("debug", False))
            try:
                log_level = TelemetryLevel(settings_payload.get("logLevel", "error"))
            except ValueError:
                valid_levels = []
                for level in TelemetryLevel:
                    valid_levels.append(level.value)
                raise TaskError(f"'settings.logLevel' in settings.json must be one of: {', '.join(valid_levels)}")

            log_categories_payload = settings_payload.get("logCategories", [])
            if not isinstance(log_categories_payload, list):
                raise TaskError("'settings.logCategories' in settings.json must be an array of strings.")
            log_categories = []
            for category_name in log_categories_payload:
                log_categories.append(str(category_name))

            if log_categories and debug and CATEGORY_GENERAL not in log_categories:
                # debug=true always keeps CATEGORY_GENERAL alongside an explicit narrower list —
                # debug mode's baseline info should stay visible even while zoomed into one
                # category, not be silently dropped by naming a single other category.
                log_categories = [CATEGORY_GENERAL] + log_categories

            excluded_categories_payload = settings_payload.get("excludedCategories", [])
            if not isinstance(excluded_categories_payload, list):
                raise TaskError("'settings.excludedCategories' in settings.json must be an array of strings.")
            excluded_categories = []
            for category_name in excluded_categories_payload:
                excluded_categories.append(str(category_name))

        if not log_categories:
            # No explicit override: debug=false restricts console noise to CATEGORY_GENERAL;
            # debug=true shows everything, same as an empty filter always has.
            log_categories = [] if debug else [CATEGORY_GENERAL]

        postgres_settings: PostgresSettings | None = None
        postgres_payload = settings_payload.get("postgres")
        if postgres_payload is not None:
            if not isinstance(postgres_payload, dict):
                raise TaskError("'settings.postgres' must be a JSON object.")
            required_keys = ["host", "port", "user", "password", "dbname"]
            missing_keys = []
            for key in required_keys:
                if key not in postgres_payload:
                    missing_keys.append(key)
            if missing_keys:
                raise TaskError(f"'settings.postgres' is missing required key(s): {', '.join(missing_keys)}")

            ssh_user = postgres_payload.get("sshUser")
            ssh_key_path = postgres_payload.get("sshKeyPath")
            if (ssh_user is None) != (ssh_key_path is None):
                raise TaskError("'settings.postgres.sshUser' and 'sshKeyPath' must both be set, or neither.")

            postgres_settings = PostgresSettings(
                host=str(postgres_payload["host"]),
                port=int(postgres_payload["port"]),
                user=str(postgres_payload["user"]),
                password=str(postgres_payload["password"]),
                dbname=str(postgres_payload["dbname"]),
                ssh_user=None if ssh_user is None else str(ssh_user),
                ssh_key_path=None if ssh_key_path is None else str(ssh_key_path),
            )

        ibkr_settings: IBKRSettings | None = None
        ibkr_payload = settings_payload.get("ibkr")
        if ibkr_payload is not None:
            if not isinstance(ibkr_payload, dict):
                raise TaskError("'settings.ibkr' must be a JSON object.")
            default_ibkr = IBKRSettings()
            ibkr_settings = IBKRSettings(
                host=str(ibkr_payload.get("host", default_ibkr.host)),
                port=int(ibkr_payload.get("port", default_ibkr.port)),
                client_id=int(ibkr_payload.get("clientId", default_ibkr.client_id)),
            )

        window_settings: WindowSettings | None = None
        window_payload = settings_payload.get("window")
        if window_payload is not None:
            if not isinstance(window_payload, dict):
                raise TaskError("'settings.window' must be a JSON object.")
            missing_keys = []
            for key in ["x", "y"]:
                if key not in window_payload:
                    missing_keys.append(key)
            if missing_keys:
                raise TaskError(f"'settings.window' is missing required key(s): {', '.join(missing_keys)}")
            window_settings = WindowSettings(x=int(window_payload["x"]), y=int(window_payload["y"]))

        cls._instance = cls(
            debug=debug,
            logging=log_level,
            log_categories=log_categories,
            excluded_categories=excluded_categories,
            postgres=postgres_settings,
            ibkr=ibkr_settings,
            window=window_settings,
        )

        return cls._instance

    @classmethod
    def save_window_position(cls, x: int, y: int, local_path: Path = Path(_LOCAL_FILENAME)) -> None:
        # A hint, not a hard requirement -- read back via the same best-effort 'window' section
        # Settings.load() already parses. Merges into local_path rather than overwriting it
        # wholesale, so this never clobbers unrelated local overrides (e.g. postgres.sshKeyPath).
        payload: dict = {}
        if local_path.exists():
            with local_path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                payload = loaded

        settings_section = payload.get("settings")
        if not isinstance(settings_section, dict):
            settings_section = {}
        settings_section["window"] = {"x": x, "y": y}
        payload["settings"] = settings_section

        with local_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")

    @classmethod
    def current(cls) -> Settings:
        if cls._instance is None:
            raise RuntimeError("Settings.load() must be called first.")
        return cls._instance
