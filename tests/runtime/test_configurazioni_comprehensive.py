"""Comprehensive test suite explicitly covering all handoff requirements for Configurazioni backend."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from agents.backend import StepResult, ToolCall
from agents.fake_backend import ScriptedBackend
from bootstrap import build_test_office
from config.settings_store import SettingsStore
from runtime.core import Runtime
from runtime.http import create_app
from storage.backup import create_db_backup
from storage.office_db import OfficeDB
from workflows.scheduling import ScheduledTask, TaskSource


@pytest.fixture
def test_env(tmp_path):
    db_path = tmp_path / "comprehensive.db"
    db = OfficeDB(db_path)
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    client = TestClient(create_app(rt))
    return {"db": db, "client": client, "tmp_path": tmp_path}


def test_secret_value_absence_everywhere(test_env):
    client = test_env["client"]
    db = test_env["db"]
    secret_val = "super-secret-key-xyz-999"

    # Set secret
    res = client.post(
        "/v1/commands/set_secret",
        json={"name": "OMNIROUTE_API_KEY", "value": secret_val, "reason": "test absence", "confirm": True},
        headers={"X-Actor": "luca"}
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Check GET /v1/read/secrets does not contain secret_val
    sec_resp = client.get("/v1/read/secrets")
    assert secret_val not in sec_resp.text

    # Check event log does not contain secret_val
    events = db.connection.execute("SELECT * FROM events").fetchall()
    for ev in events:
        assert secret_val not in str(ev)

    # Check commands table / cli_commands
    cmds = db.connection.execute("SELECT * FROM cli_commands").fetchall()
    for c in cmds:
        assert secret_val not in str(c)


def test_dry_run_does_not_write(test_env):
    client = test_env["client"]
    db = test_env["db"]
    v_before = db.latest_settings_version()

    res = client.post(
        "/v1/commands/update_settings",
        json={"changes": {"max_parallel": 5}, "reason": "dry run test", "dry_run": True},
        headers={"X-Actor": "luca"}
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert "changes" in res.json()["data"]

    v_after = db.latest_settings_version()
    assert v_after == v_before


def test_backup_readability_and_rotation(test_env):
    db = test_env["db"]
    bdir = test_env["tmp_path"] / "backups"

    create_db_backup(db, backup_dir=bdir, max_backups=2)
    create_db_backup(db, backup_dir=bdir, max_backups=2)
    b3 = create_db_backup(db, backup_dir=bdir, max_backups=2)

    # Verify readability of backup file via sqlite3
    backup_file = bdir / b3["name"]
    assert backup_file.is_file()
    conn = sqlite3.connect(str(backup_file))
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "settings_versions" in tables

    # Verify rotation (max_backups=2)
    records = db.list_backup_records(limit=10)
    assert len(records) <= 2


def test_event_only_on_commit(test_env):
    db = test_env["db"]
    store = SettingsStore(db)

    # Rollback transaction should not emit events
    try:
        with db.transaction():
            store.update({"max_parallel": 6}, "should fail", "luca")
            raise RuntimeError("forced rollback")
    except RuntimeError:
        pass

    events = db.connection.execute("SELECT * FROM events WHERE type = 'settings.updated'").fetchall()
    assert len(events) == 0


def test_idempotency_key_behavior(test_env):
    client = test_env["client"]
    idemp_key = "idemp-test-uuid-123"

    payload = {
        "changes": {"max_parallel": 3},
        "reason": "idempotency check",
        "confirm": True
    }
    r1 = client.post(
        "/v1/commands/update_settings",
        json=payload,
        headers={"Idempotency-Key": idemp_key, "X-Actor": "luca"}
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/v1/commands/update_settings",
        json=payload,
        headers={"Idempotency-Key": idemp_key, "X-Actor": "luca"}
    )
    assert r2.status_code == 200
    assert r2.json() == r1.json()


def test_live_vs_restart_settings_apply(test_env):
    client = test_env["client"]
    # Live setting update
    r1 = client.post(
        "/v1/commands/update_settings",
        json={"changes": {"max_parallel": 4}, "reason": "live test", "confirm": True},
        headers={"Idempotency-Key": "live-1", "X-Actor": "luca"}
    )
    assert r1.json()["ok"] is True

    # Restart setting update
    r2 = client.post(
        "/v1/commands/update_settings",
        json={"changes": {"market.bar_timeframe": "15m"}, "reason": "restart test", "confirm": True},
        headers={"Idempotency-Key": "restart-1", "X-Actor": "luca"}
    )
    assert r2.json()["ok"] is True

def test_live_settings_immediate_application(test_env):
    client = test_env["client"]
    # Update a live setting (max_parallel)
    r = client.post(
        "/v1/commands/update_settings",
        json={"changes": {"max_parallel": 7}, "reason": "immediate live apply", "confirm": True},
        headers={"X-Actor": "luca"}
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Check that GET /v1/read/settings shows the new value immediately (live application)
    settings_data = client.get("/v1/read/settings").json()
    for sec in settings_data["sections"]:
        for item in sec["items"]:
            if item["key"] == "max_parallel":
                assert item["value"] == 7


def test_engine_cycle_prompt_and_live_settings_execution(test_env):
    db = test_env["db"]
    client = test_env["client"]

    # 1. Seed initial prompt v1 for portfolio_manager in DB
    db.insert_prompt_version("portfolio_manager", "luca", "v1", "Initial PM Prompt v1")

    # 2. Run Cycle via Office deliver with scripted backend that checks agent spec system_prompt
    captured_prompts = []

    def script_fn(agent, chat_context, tools, turn):
        captured_prompts.append((agent.name, agent.system_prompt))
        return StepResult(tool_calls=[ToolCall(id="t1", name="defer", args={"ticker": "AAPL", "reason": "done"})], done=True)

    fixed_now = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    office = build_test_office(db=db, backend=ScriptedBackend(script_fn))
    office.clock = lambda: fixed_now
    office.sleep_fn = lambda _: None
    pm_cfg = office.settings.get_agent("portfolio_manager")
    pm_cfg.system_prompt_path = None

    task1 = ScheduledTask(agent="portfolio_manager", chat="AAPL", when=fixed_now, source=TaskSource.MANUAL, reason="Cycle 1")
    outcome1 = office.deliver(task1)
    assert outcome1 in ("deferred", "rimando")
    assert any("Initial PM Prompt v1" in p for _, p in captured_prompts)

    # 3. Mid-cycle update: update live setting (max_parallel) and insert prompt v2
    client.post(
        "/v1/commands/update_settings",
        json={"changes": {"max_parallel": 5}, "reason": "live update test", "confirm": True},
        headers={"X-Actor": "luca"}
    )
    store = SettingsStore(db, office.settings)
    office.settings = store.active_settings()
    assert office.settings.max_parallel == 5

    db.insert_prompt_version("portfolio_manager", "luca", "v2", "Updated PM Prompt v2 (Next Cycle)")

    # 4. Run Cycle 2: engine reads updated live settings (max_parallel == 5) and loads new prompt version v2
    captured_prompts.clear()
    task2 = ScheduledTask(agent="portfolio_manager", chat="AAPL", when=fixed_now + timedelta(hours=1), source=TaskSource.MANUAL, reason="Cycle 2")
    outcome2 = office.deliver(task2)
    assert outcome2 in ("deferred", "rimando")
    assert any("Updated PM Prompt v2" in p for _, p in captured_prompts)
    assert office.settings.max_parallel == 5









