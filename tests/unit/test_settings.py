from __future__ import annotations

import json

import pytest

from shared.errors import TaskError
from shared.settings import Settings


def _write_settings(tmp_path, postgres: dict) -> object:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"settings": {"postgres": postgres}}), encoding="utf-8")
    return settings_path


def _base_postgres(**overrides) -> dict:
    postgres = {
        "host": "localhost",
        "port": 5433,
        "user": "quant_reader",
        "password": "",
        "dbname": "quant_data",
    }
    postgres.update(overrides)
    return postgres


def test_load_postgres_without_ssh_fields_defaults_to_none(tmp_path):
    settings_path = _write_settings(tmp_path, _base_postgres())

    settings = Settings.load(path=settings_path, local_path=tmp_path / "settings.local.json")

    assert settings.postgres.ssh_user is None
    assert settings.postgres.ssh_key_path is None


def test_load_postgres_with_both_ssh_fields_set(tmp_path):
    settings_path = _write_settings(tmp_path, _base_postgres(sshUser="alex", sshKeyPath="/home/alex/.ssh/id_ed25519"))

    settings = Settings.load(path=settings_path, local_path=tmp_path / "settings.local.json")

    assert settings.postgres.ssh_user == "alex"
    assert settings.postgres.ssh_key_path == "/home/alex/.ssh/id_ed25519"


def test_load_postgres_with_only_ssh_user_raises(tmp_path):
    settings_path = _write_settings(tmp_path, _base_postgres(sshUser="alex"))

    with pytest.raises(TaskError):
        Settings.load(path=settings_path, local_path=tmp_path / "settings.local.json")


def test_load_postgres_with_only_ssh_key_path_raises(tmp_path):
    settings_path = _write_settings(tmp_path, _base_postgres(sshKeyPath="/home/alex/.ssh/id_ed25519"))

    with pytest.raises(TaskError):
        Settings.load(path=settings_path, local_path=tmp_path / "settings.local.json")
