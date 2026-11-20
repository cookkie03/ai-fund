import uuid

import pytest
from fastapi.testclient import TestClient

from bootstrap import build_test_office
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB


@pytest.fixture
def runtime_setup(tmp_path):
    db_path = tmp_path / "http_test.db"
    db = OfficeDB(db_path)
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    app = create_app(rt, token=None, host="127.0.0.1")
    client = TestClient(app)
    return {"runtime": rt, "app": app, "client": client, "db_path": db_path}


def test_http_health_endpoint(runtime_setup):
    client: TestClient = runtime_setup["client"]
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["runtime_version"] == "0.1.0"
    assert data["halted"] is False


def test_http_command_enqueue_task(runtime_setup):
    client: TestClient = runtime_setup["client"]
    cmd_id = str(uuid.uuid4())
    payload = {"agent": "market_analyst", "ticker": "AAPL", "reason": "Earnings"}

    resp = client.post(
        "/v1/commands/enqueue_task",
        json=payload,
        headers={"Idempotency-Key": cmd_id, "X-Actor": "test_client"},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["ok"] is True
    assert "task_id" in res_data["data"]


def test_http_command_approve_order_validation_error(runtime_setup):
    client: TestClient = runtime_setup["client"]
    # Missing confirm=True should return 422
    resp = client.post(
        "/v1/commands/approve_order",
        json={"order_id": 1, "confirm": False},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


def test_http_command_refresh_data_202(runtime_setup):
    client: TestClient = runtime_setup["client"]
    resp = client.post(
        "/v1/commands/refresh_data",
        json={"force": False},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 202


def test_http_read_endpoints(runtime_setup):
    client: TestClient = runtime_setup["client"]

    # Add watchlist
    client.post(
        "/v1/commands/add_watchlist",
        json={"ticker": "TSLA", "note": "EV"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    resp = client.get("/v1/read/watchlist")
    assert resp.status_code == 200
    wl = resp.json()
    assert any(it["ticker"] == "TSLA" for it in wl)

    resp_orders = client.get("/v1/read/orders")
    assert resp_orders.status_code == 200
    assert isinstance(resp_orders.json(), list)


def test_http_sse_events_replay_and_format(runtime_setup):
    client: TestClient = runtime_setup["client"]
    rt: Runtime = runtime_setup["runtime"]

    # Emit two events
    rt.event_log.append("e.test1", "sub1", {"v": 1}, actor="test")
    rt.event_log.append("e.test2", "sub2", {"v": 2}, actor="test")

    with client.stream("GET", "/v1/events?after=0") as resp:
        assert resp.status_code == 200
        lines = []
        for line in resp.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 6:  # 2 events * 3 lines (id, event, data)
                break

    text = "\n".join(lines)
    assert "event: e.test1" in text
    assert "event: e.test2" in text


def test_token_auth_required_when_configured(runtime_setup):
    rt: Runtime = runtime_setup["runtime"]
    app = create_app(rt, token="secret123", host="127.0.0.1")
    client = TestClient(app)

    # Without token -> 401
    resp = client.get("/v1/health")
    assert resp.status_code == 401

    # With invalid token -> 401
    resp = client.get("/v1/health", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401

    # With valid token -> 200
    resp = client.get("/v1/health", headers={"Authorization": "Bearer secret123"})
    assert resp.status_code == 200


def test_token_mandatory_on_non_loopback(runtime_setup):
    rt: Runtime = runtime_setup["runtime"]
    with pytest.raises(ValueError, match="token è obbligatorio"):
        create_app(rt, token=None, host="0.0.0.0")


def test_single_writer_lock_prevents_second_runtime(tmp_path):
    db_path = tmp_path / "lock_test.db"
    db1 = OfficeDB(db_path)
    office1 = build_test_office(db=db1)
    rt1 = Runtime(office=office1)
    rt1.start()

    db2 = OfficeDB(db_path)
    office2 = build_test_office(db=db2)
    rt2 = Runtime(office=office2)

    with pytest.raises(RuntimeError, match="Another Runtime process is already running"):
        rt2.start()

    rt1.stop()
    # Now rt2 can start
    rt2.start()
    rt2.stop()
