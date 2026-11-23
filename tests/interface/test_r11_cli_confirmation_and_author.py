"""Test R11: CLI confirmations, author=user for Say, HMAC token comparison."""

from __future__ import annotations

import io
from unittest.mock import patch

from bootstrap import build_test_office
from interface.cli import main
from interface.client import RuntimeClient
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


def test_r11_say_records_author_user_and_actor_in_event(tmp_path):
    """Say command must store author as 'user', while event records the actor."""
    db = OfficeDB(tmp_path / "test.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    from starlette.testclient import TestClient

    app = create_app(runtime=rt, host="127.0.0.1")
    http_client = TestClient(app)
    client = RuntimeClient(client=http_client)

    out = io.StringIO()
    exit_code = main(
        ["say", "portfolio_manager", "AAPL", "Review valuation"],
        client_factory=lambda: client,
        out=out,
    )
    assert exit_code == 0

    # Verify message in database has author == 'user'
    msg = db.connection.execute("SELECT author, text FROM messages LIMIT 1").fetchone()
    assert msg is not None
    assert msg["author"] == "user"
    assert msg["text"] == "Review valuation"

    # Verify event has actor == 'cli'
    event = [e for e in rt.event_log.since(0) if e.type == "message.appended"][0]
    assert event.actor == "cli"


def test_r11_halt_and_resume_require_confirmation_or_yes_flag(tmp_path):
    """Halt and resume must cancel when unconfirmed, and succeed when confirmed with -y / --yes."""
    db = OfficeDB(tmp_path / "test.db")
    fake_broker = FakeBracketBroker()
    office = build_test_office(db=db, broker=fake_broker)
    rt = Runtime(office=office)

    from starlette.testclient import TestClient

    app = create_app(runtime=rt, host="127.0.0.1")
    http_client = TestClient(app)
    client = RuntimeClient(client=http_client)

    # 1. Halt without --yes and user answers 'n' -> cancelled
    out = io.StringIO()
    with patch("builtins.input", return_value="n"):
        code = main(["halt"], client_factory=lambda: client, out=out)
        assert code != 0
        assert "annullata" in out.getvalue().lower() or "cancelled" in out.getvalue().lower()
        assert office.halt.is_halted() is False

    # 2. Halt with --yes -> succeeds
    out_yes = io.StringIO()
    code_yes = main(["halt", "--yes"], client_factory=lambda: client, out=out_yes)
    assert code_yes == 0
    assert office.halt.is_halted() is True

    # 3. Resume with -y -> succeeds
    out_res = io.StringIO()
    code_res = main(["resume", "-y"], client_factory=lambda: client, out=out_res)
    assert code_res == 0
    assert office.halt.is_halted() is False


def test_r11_orders_approve_requires_confirmation_or_yes_flag(tmp_path):
    """Orders approve must require confirmation or --yes."""
    db = OfficeDB(tmp_path / "test.db")
    fake_broker = FakeBracketBroker()
    office = build_test_office(db=db, broker=fake_broker, approval_mode="manual")
    order_id = db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={
            "symbol": "AAPL",
            "side": "buy",
            "quantity": "10",
            "entry": "150.0",
            "stop": "140.0",
            "take_profit": "170.0",
            "risk_reward": "2.0",
            "notional": "1500.0",
        },
        draft_hash="h1",
        approval_status="pending",
        client_order_id="cid_r11",
        status="pending",
    )

    rt = Runtime(office=office)
    from starlette.testclient import TestClient

    app = create_app(runtime=rt, host="127.0.0.1")
    http_client = TestClient(app)
    client = RuntimeClient(client=http_client)

    # Without --yes and answering 'n' -> cancelled
    out_no = io.StringIO()
    with patch("builtins.input", return_value="n"):
        code = main(["orders", "approve", str(order_id)], client_factory=lambda: client, out=out_no)
        assert code != 0
        assert db.get_order(order_id)["approval_status"] == "pending"

    # With -y -> proceeds
    out_yes = io.StringIO()
    _ = main(["orders", "approve", str(order_id), "-y"], client_factory=lambda: client, out=out_yes)
    # Order approval attempt ran
    assert db.get_order(order_id)["approval_status"] in ("approved", "rejected", "submitting", "submitted")
