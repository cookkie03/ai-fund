"""Limiti del Risk Gate versionati: bounds, versioni, evento al commit, lettura a ogni valutazione."""

from __future__ import annotations

from decimal import Decimal

import pytest

from bootstrap import build_test_office
from config.office_settings import OfficeSettings
from execution.risk_gate import GateOrder, run_risk_gate
from execution.risk_limits import (
    BOUNDS,
    LimitsValidationError,
    RiskLimitsStore,
    active_gate_limits,
    defaults_from_settings,
)
from runtime.events import EventBus, EventLog
from storage.office_db import OfficeDB


@pytest.fixture
def db(tmp_path) -> OfficeDB:
    return OfficeDB(tmp_path / "limits.db")


@pytest.fixture
def store(db) -> RiskLimitsStore:
    return RiskLimitsStore(db, defaults_from_settings(OfficeSettings().limits))


def test_defaults_come_from_office_toml_as_version_zero(store):
    active = store.active()
    assert active.version == 0
    assert active.limits["max_risk_per_trade_fraction"] == 0.01
    assert active.limits["max_open_positions"] == 30
    assert active.updated_by is None


def test_update_creates_version_with_before_and_after(db, store):
    with db.transaction():
        active = store.update({"max_position_fraction": 0.12}, "più spazio", "luca")
    assert active.version == 1
    assert active.limits["max_position_fraction"] == 0.12
    assert active.limits["max_sector_fraction"] == 0.30  # invariato
    hist = store.history()
    assert hist[0]["version"] == 1
    assert hist[0]["actor"] == "luca" and hist[0]["reason"] == "più spazio"
    assert hist[0]["before"] == {"max_position_fraction": 0.10}
    assert hist[0]["after"] == {"max_position_fraction": 0.12}


def test_versions_are_monotonic_and_latest_wins(db, store):
    with db.transaction():
        store.update({"max_open_positions": 20}, "a", "luca")
    with db.transaction():
        store.update({"max_open_positions": 15}, "b", "luca")
    assert store.active().version == 2
    assert store.active().limits["max_open_positions"] == 15
    assert [h["version"] for h in store.history()] == [2, 1]


@pytest.mark.parametrize(
    "partial",
    [
        {"max_risk_per_trade_fraction": 0.06},
        {"max_risk_per_trade_fraction": 0.0},
        {"min_risk_reward_ratio": 0.9},
        {"min_cash_reserve_fraction": -0.01},
        {"max_open_positions": 0},
        {"max_open_positions": 2.5},
        {"unknown_limit": 1},
        {"max_position_fraction": "alto"},
        {},
    ],
)
def test_out_of_bounds_rejected_and_nothing_written(db, store, partial):
    with pytest.raises(LimitsValidationError) as exc:
        with db.transaction():
            store.update(partial, "prova", "luca")
    assert exc.value.reasons
    assert store.active().version == 0
    assert db.list_risk_limits_versions() == []


def test_bounds_are_inclusive_and_cash_reserve_can_be_zero(db, store):
    lo, hi = BOUNDS["max_risk_per_trade_fraction"]
    assert hi == 0.05
    assert BOUNDS["min_cash_reserve_fraction"][0] == 0.0
    assert BOUNDS["min_risk_reward_ratio"][0] == 1.0
    with db.transaction():
        store.update({"max_risk_per_trade_fraction": hi, "min_cash_reserve_fraction": 0.0}, "x", "l")
    assert store.active().limits["max_risk_per_trade_fraction"] == hi


def test_reason_required_and_noop_rejected(db, store):
    with pytest.raises(LimitsValidationError):
        with db.transaction():
            store.update({"max_open_positions": 10}, "  ", "luca")
    with pytest.raises(LimitsValidationError):
        with db.transaction():
            store.update({"max_open_positions": 30}, "uguale", "luca")


def test_update_writes_inbox_entry(db, store):
    with db.transaction():
        store.update({"max_open_positions": 12}, "ridotto", "luca")
    rows = db.connection.execute("SELECT kind, text FROM inbox").fetchall()
    assert [r["kind"] for r in rows] == ["risk_limits_updated"]
    assert "max_open_positions" in rows[0]["text"]


def test_event_published_only_after_commit(db, store):
    bus = EventBus()
    db.event_log = EventLog(db, bus)
    sub = bus.subscribe()
    try:
        with pytest.raises(RuntimeError):
            with db.transaction():
                store.update({"max_open_positions": 12}, "boom", "luca")
                raise RuntimeError("rollback")
        assert sub._queue.empty()
        assert db.list_risk_limits_versions() == []
        with db.transaction():
            store.update({"max_open_positions": 12}, "ok", "luca")
            assert sub._queue.empty()  # non ancora committato
        ev = sub.get(timeout=1)
        assert ev.type == "risk_limits.updated"
        assert ev.payload["version"] == 1
        assert ev.payload["after"] == {"max_open_positions": 12}
    finally:
        sub.unsubscribe()


def test_risk_gate_reads_new_limits_without_restart(db, store):
    settings = OfficeSettings()
    order = GateOrder(
        symbol="AAPL",
        side="buy",
        quantity=Decimal("100"),
        entry=Decimal("100"),
        stop=Decimal("97"),
        take_profit=Decimal("110"),
        sector="Tech",
    )
    from execution.risk_gate import RiskGateContext

    def ctx():
        return RiskGateContext(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            limits=active_gate_limits(db, settings.limits),
        )

    # rischio 300 <= 1000; R:R 10/3=3.3 ok ma posizione 10000 = 10% (limite incluso)
    assert run_risk_gate(order, ctx()).allowed
    with db.transaction():
        store.update({"max_position_fraction": 0.05}, "stretto", "luca")
    res = run_risk_gate(order, ctx())
    assert not res.allowed
    assert any("(5% equity)" in r for r in res.reasons)  # motivo con la nuova soglia


def test_office_build_risk_gate_context_uses_active_version(tmp_path):
    db = OfficeDB(tmp_path / "o.db")
    office = build_test_office(db=db)
    assert office.build_risk_gate_context().limits.max_open_positions == 30
    store = RiskLimitsStore(db, defaults_from_settings(office.settings.limits))
    with db.transaction():
        store.update({"max_open_positions": 7}, "meno posizioni", "luca")
    assert office.build_risk_gate_context().limits.max_open_positions == 7
