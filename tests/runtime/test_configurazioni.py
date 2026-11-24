"""Tests for Configurazioni backend: versioned settings, versioned prompts, secrets, runtime health, backups."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from bootstrap import build_test_office
from config.settings_store import SettingsStore, SettingsValidationError
from runtime.core import Runtime
from runtime.http import create_app
from storage.backup import create_db_backup
from storage.office_db import OfficeDB
from storage.secrets import SecretsManager


@pytest.fixture
def db(tmp_path) -> OfficeDB:
    return OfficeDB(tmp_path / "config.db")


@pytest.fixture
def client(tmp_path) -> TestClient:
    db = OfficeDB(tmp_path / "client.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    return TestClient(create_app(rt))


def test_settings_store_defaults_and_validation(db):
    store = SettingsStore(db)
    active = store.active_dict()
    assert active["max_parallel"] == 3

    # Valid update
    res = store.update({"max_parallel": 5}, "aumento parallelismo", "luca")
    assert res["version"] == 1
    assert store.active_dict()["max_parallel"] == 5

    # Out of bounds
    with pytest.raises(SettingsValidationError):
        store.update({"max_parallel": 50}, "troppo alto", "luca")


def test_prompt_versioning_and_diff(db):
    from prompts.loader import compute_prompt_diff, load_prompt_full
    v1, chars1 = db.insert_prompt_version("portfolio_manager", "luca", "v1", "Sei il Portfolio Manager v1.")
    v2, chars2 = db.insert_prompt_version("portfolio_manager", "luca", "v2", "Sei il Portfolio Manager v2.")
    assert v2 == 2

    text, _, ver, is_def = load_prompt_full("portfolio_manager", db=db)
    assert ver == 2
    assert "v2" in text

    diff = compute_prompt_diff("Sei il Portfolio Manager v1.", "Sei il Portfolio Manager v2.")
    assert "-Sei il Portfolio Manager v1." in diff
    assert "+Sei il Portfolio Manager v2." in diff


def test_secrets_manager_permissions_and_no_leakage(tmp_path):
    sec_file = tmp_path / "secrets.env"
    meta_file = tmp_path / "secrets.meta.json"
    manager = SecretsManager(secrets_path=sec_file, meta_path=meta_file)

    res = manager.set("OMNIROUTE_API_KEY", "sk-secret-123456", "luca", "setup key")
    assert res["set"] is True
    assert res["last4"] == "3456"

    # Verify 0600 permissions
    stat_mode = os.stat(sec_file).st_mode
    assert (stat_mode & 0o077) == 0  # no group or other permissions

    # Precedence & get
    assert manager.get("OMNIROUTE_API_KEY") == "sk-secret-123456"

    # List secrets never returns full value
    listed = manager.list_secrets()
    omni = next(s for s in listed if s["name"] == "OMNIROUTE_API_KEY")
    assert omni["set"] is True
    assert omni["last4"] == "3456"
    assert "sk-secret-123456" not in str(listed)

    # Clear
    manager.clear("OMNIROUTE_API_KEY", "luca", "remove")
    assert manager.get("OMNIROUTE_API_KEY") is None


def test_backup_and_rotation(db, tmp_path):
    bdir = tmp_path / "backups"
    create_db_backup(db, backup_dir=bdir, max_backups=2)
    create_db_backup(db, backup_dir=bdir, max_backups=2)
    create_db_backup(db, backup_dir=bdir, max_backups=2)

    backs = db.list_backup_records(limit=10)
    assert len(backs) <= 2  # rotation kept max 2


def test_http_read_endpoints_and_commands(client):
    # GET settings
    r_set = client.get("/v1/read/settings")
    assert r_set.status_code == 200
    assert "sections" in r_set.json()

    # POST update_settings with dry_run
    r_dry = client.post("/v1/commands/update_settings", json={
        "changes": {"max_parallel": 4},
        "reason": "test dry run",
        "dry_run": True
    })
    assert r_dry.status_code == 200
    assert r_dry.json()["ok"] is True
    assert r_dry.json()["data"]["changes"][0]["new"] == 4

    # POST update_settings real change
    r_up = client.post("/v1/commands/update_settings", json={
        "changes": {"max_parallel": 4},
        "reason": "test commit",
        "confirm": True
    }, headers={"X-Actor": "luca"})
    assert r_up.status_code == 200
    assert r_up.json()["ok"] is True

    # GET runtime_health
    r_hlth = client.get("/v1/read/runtime_health")
    assert r_hlth.status_code == 200
    assert "commit" in r_hlth.json()


def test_prompt_and_secret_endpoints(client):
    r_prompt = client.get("/v1/read/prompt", params={"agent": "portfolio_manager"})
    assert r_prompt.status_code == 200
    assert "text" in r_prompt.json()

    r_sec = client.get("/v1/read/secrets")
    assert r_sec.status_code == 200
    assert isinstance(r_sec.json(), list)

    r_test = client.post("/v1/commands/test_connection", json={"target": "omniroute"}, headers={"X-Actor": "luca"})
    assert r_test.status_code == 200
    assert r_test.json()["ok"] is True

    r_backup = client.post("/v1/commands/backup_db", json={}, headers={"X-Actor": "luca"})
    assert r_backup.status_code == 200
    assert r_backup.json()["ok"] is True

    r_backups = client.get("/v1/read/backups")
    assert r_backups.status_code == 200
    assert isinstance(r_backups.json(), list)
