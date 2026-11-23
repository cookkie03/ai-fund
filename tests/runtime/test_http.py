import uuid
from datetime import UTC

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


def test_dossier_and_history_are_available_over_http(runtime_setup):
    runtime = runtime_setup["runtime"]
    client = runtime_setup["client"]
    env = runtime.office.get_env(None)
    from agents.backend import ToolCall

    write = next(t for t in env.tools_for("technical_analyst") if t.name == "write_analysis")
    write.execute(ToolCall(id="a", name="write_analysis", args={
        "ticker": "AAPL", "section_text": "Trend upward",
    }))
    response = client.get("/v1/read/dossier", params={"ticker": "aapl"})
    assert response.status_code == 200
    dossier = response.json()
    assert dossier["ticker"] == "AAPL"
    assert dossier["version"] == 1
    assert dossier["status"] == "idle"
    assert dossier["desks"][0]["text"] == "Trend upward"
    assert dossier["stale_count"] == 0
    assert set(dossier) == {"ticker", "version", "updated_ts", "updated_by", "status", "identity",
        "portfolio", "desks", "thesis", "proposal", "risk", "decisions", "lessons", "notes", "stale_count"}
    history = client.get("/v1/read/dossier_history", params={"ticker": "AAPL"}).json()
    assert history[0]["sections_changed"] == ["desks"]


def test_dossier_note_is_idempotent_and_signed_by_actor(runtime_setup):
    client = runtime_setup["client"]
    headers = {"Idempotency-Key": "note-1", "X-Actor": "user"}
    for _ in range(2):
        response = client.post("/v1/commands/add_dossier_note", headers=headers,
                               json={"ticker": "aapl", "text": "Check margins"})
        assert response.status_code == 200 and response.json()["ok"]
    dossier = client.get("/v1/read/dossier", params={"ticker": "AAPL"}).json()
    assert len(dossier["notes"]) == 1
    assert dossier["notes"][0]["author"] == "user"
    assert dossier["notes"][0]["text"] == "Check margins"
    assert dossier["version"] == 1


def test_agent_reads_user_note_in_dossier(runtime_setup):
    from agents.backend import ToolCall

    client = runtime_setup["client"]
    client.post("/v1/commands/add_dossier_note", headers={"X-Actor": "user", "Idempotency-Key": "note"},
                json={"ticker": "AAPL", "text": "Review margins"})
    env = runtime_setup["runtime"].office.get_env(None)
    tools = {tool.name: tool for tool in env.tools_for("technical_analyst")}
    result = tools["read_dossier"].execute(ToolCall(id="1", name="read_dossier", args={"ticker": "AAPL"}))
    assert result["notes"][0]["text"] == "Review margins"


def test_old_specialist_contribution_is_stale_on_read(runtime_setup):
    from datetime import UTC, datetime

    from agents.backend import ToolCall

    env = runtime_setup["runtime"].office.get_env(None)
    env._now = datetime(2020, 1, 1, tzinfo=UTC)
    write = next(t for t in env.tools_for("technical_analyst") if t.name == "write_analysis")
    write.execute(ToolCall(id="a", name="write_analysis", args={
        "ticker": "AAPL", "section_text": "Old analysis",
    }))
    dossier = runtime_setup["client"].get("/v1/read/dossier", params={"ticker": "AAPL"}).json()
    assert dossier["desks"][0]["status"] == "stale"
    assert dossier["stale_count"] == 1


def test_agents_endpoint_identifies_core_and_registered_ticker_agents(runtime_setup):
    runtime = runtime_setup["runtime"]
    runtime.office.db.register_agent("ticker:AAPL", "ticker_agent")
    agents = runtime_setup["client"].get("/v1/read/agents").json()
    ticker = next(agent for agent in agents if agent["name"] == "ticker:AAPL")
    assert (ticker["kind"], ticker["ticker"], ticker["supervisor"]) == (
        "ticker", "AAPL", "portfolio_manager")
    pm = next(agent for agent in agents if agent["name"] == "portfolio_manager")
    assert (pm["kind"], pm["ticker"], pm["supervisor"]) == ("core", None, None)


def test_dossiers_list_includes_latest_version_per_ticker(runtime_setup):
    client = runtime_setup["client"]
    for i, ticker in enumerate(("AAPL", "MSFT", "AAPL")):
        response = client.post("/v1/commands/add_dossier_note", json={"ticker": ticker, "text": "note"},
                               headers={"X-Actor": "user", "Idempotency-Key": str(i)})
        assert response.json()["ok"]
    response = client.get("/v1/read/dossiers", params={"limit": 10})
    assert response.status_code == 200
    result = response.json()
    assert {item["ticker"] for item in result} == {"AAPL", "MSFT"}
    assert all(item["status"] == "idle" for item in result)


def test_dossier_rollback_leaves_no_history_or_note(runtime_setup):
    import pytest

    runtime = runtime_setup["runtime"]
    db = runtime.office.db
    with pytest.raises(RuntimeError), db.transaction():
        db.write_dossier_section("AAPL", "notes", {
            "id": "1", "author": "user", "text": "test", "ts": "2026-11-22T00:00:00Z"
        }, "user", "2026-11-22T00:00:00Z")
        raise RuntimeError("rollback")
    assert runtime.read.dossier_history("AAPL") == []
    assert runtime.read.dossier("AAPL") is None


def test_dossier_note_requires_idempotency_key_and_actor(runtime_setup):
    client = runtime_setup["client"]
    payload = {"ticker": "AAPL", "text": "note"}
    assert client.post("/v1/commands/add_dossier_note", json=payload).status_code == 422
    assert client.post("/v1/commands/add_dossier_note", json=payload,
                       headers={"Idempotency-Key": "1"}).status_code == 422


def test_user_can_defer_proposal_with_confirmation(runtime_setup):
    from agents.backend import ToolCall

    runtime = runtime_setup["runtime"]
    runtime.office.db.register_agent("ticker:AAPL", "ticker_agent")
    env = runtime.office.get_env(None)
    submit = next(t for t in env.tools_for("ticker:AAPL") if t.name == "submit_proposal")
    proposal = submit.execute(ToolCall(id="1", name="submit_proposal", args={
        "ticker": "AAPL", "direction": "buy", "conviction": 0.8, "reason": "Trend",
    }))
    client = runtime_setup["client"]
    payload = {"proposal_id": proposal["id"], "action": "defer", "reason": "Review later", "when": "2030-01-01T10:00:00Z", "confirm": True}
    headers = {"Idempotency-Key": "decision-1", "X-Actor": "user"}
    result = client.post("/v1/commands/decide_proposal", json=payload, headers=headers)
    assert result.status_code == 200 and result.json()["ok"]
    assert client.get("/v1/read/proposals", params={"status": "deferred"}).json()[0]["id"] == proposal["id"]
    assert client.post("/v1/commands/decide_proposal", json=payload, headers=headers).json() == result.json()


def test_user_can_accept_proposal_through_risk_gate(runtime_setup):
    from agents.backend import ToolCall

    runtime = runtime_setup["runtime"]
    runtime.office.db.register_agent("ticker:AAPL", "ticker_agent")
    runtime.office.db.set_ticker_state("AAPL", {"coefficients": {"risk_fraction": 0.003}})
    env = runtime.office.get_env(None)
    submit = next(t for t in env.tools_for("ticker:AAPL") if t.name == "submit_proposal")
    proposal = submit.execute(ToolCall(id="1", name="submit_proposal", args={
        "ticker": "AAPL", "direction": "buy", "conviction": 0.8, "reason": "Trend",
    }))
    result = runtime_setup["client"].post("/v1/commands/decide_proposal", json={
        "proposal_id": proposal["id"], "action": "accept", "reason": "Approve", "confirm": True,
    }, headers={"Idempotency-Key": "accept-1", "X-Actor": "user"})
    assert result.status_code == 200
    assert result.json()["ok"]
    assert runtime.office.db.connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1


def test_replayed_rejected_acceptance_does_not_create_order(runtime_setup):
    from agents.backend import ToolCall

    rt = runtime_setup["runtime"]
    rt.office.db.register_agent("ticker:AAPL", "ticker_agent")
    env = rt.office.get_env(None)
    submit = next(t for t in env.tools_for("ticker:AAPL") if t.name == "submit_proposal")
    proposal = submit.execute(ToolCall(id="1", name="submit_proposal", args={
        "ticker": "AAPL", "direction": "hold", "conviction": 0.5, "reason": "Wait"}))
    headers = {"Idempotency-Key": "bad-accept", "X-Actor": "user"}
    payload = {"proposal_id": proposal["id"], "action": "accept", "reason": "Review", "confirm": True}
    client = runtime_setup["client"]
    assert not client.post("/v1/commands/decide_proposal", json=payload, headers=headers).json()["ok"]
    assert not client.post("/v1/commands/decide_proposal", json=payload, headers=headers).json()["ok"]
    assert rt.office.db.connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_watchlist_records_command_actor(runtime_setup):
    client = runtime_setup["client"]
    response = client.post(
        "/v1/commands/add_watchlist", json={"ticker": "AAPL"}, headers={"X-Actor": "user"}
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert client.get("/v1/read/watchlist").json()[0]["added_by"] == "user"


def test_annotation_lifecycle(runtime_setup):
    client = runtime_setup["client"]
    headers = {"X-Actor": "user"}
    drawing = {"type": "trendline", "points": [{"time": 1700000000, "price": 100.0}]}
    created = client.post(
        "/v1/commands/upsert_annotation",
        json={"id": "a1", "ticker": "AAPL", "drawing": drawing},
        headers=headers,
    )
    assert created.status_code == 200
    assert created.json()["ok"]
    annotations = client.get("/v1/read/annotations?ticker=AAPL").json()
    assert annotations[0]["author"] == "user"
    assert annotations[0]["drawing"] == drawing
    struck = client.post(
        "/v1/commands/strike_annotation", json={"id": "a1"}, headers={"X-Actor": "analyst"}
    )
    assert struck.json()["ok"]
    assert client.get("/v1/read/annotations?ticker=AAPL").json() == []
    item = client.get("/v1/read/annotations?ticker=AAPL&include_struck=true").json()[0]
    assert item["status"] == "struck"
    assert item["struck_by"] == "analyst"


def test_annotation_rejects_invalid_drawing(runtime_setup):
    response = runtime_setup["client"].post(
        "/v1/commands/upsert_annotation",
        json={"id": "bad", "ticker": "AAPL", "drawing": {"points": [{"time": "bad", "price": "bad"}]}},
    )
    assert response.status_code == 422


def test_annotation_retry_without_key_does_not_emit_duplicate_event(runtime_setup):
    client = runtime_setup["client"]
    runtime = runtime_setup["runtime"]
    payload = {"id": "same", "ticker": "AAPL", "drawing": {"type": "line", "points": [{"time": 1, "price": 2}]}}
    client.post("/v1/commands/upsert_annotation", json=payload)
    client.post("/v1/commands/upsert_annotation", json=payload)
    events = runtime.event_log.since(after_id=0)
    assert [event.type for event in events if event.type.startswith("annotation.")] == ["annotation.created"]


def test_bars_are_chronological_utc_chart_data(runtime_setup):
    client = runtime_setup["client"]
    market = runtime_setup["runtime"].office.get_env().market_data
    market.ohlcv = lambda symbol, interval, limit: [
        {"ts": "2026-01-01T00:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2, "v": 10},
        {"ts": "2026-01-02T00:00:00Z", "o": 2, "h": 3, "l": 2, "c": 3, "v": 20},
    ]
    response = client.get("/v1/read/bars", params={"ticker": "AAPL", "limit": 2})
    assert response.status_code == 200
    bars = response.json()
    assert len(bars) == 2
    assert set(bars[0]) == {"time", "open", "high", "low", "close", "volume"}
    assert isinstance(bars[0]["time"], int)
    assert bars[0]["time"] < bars[1]["time"]


def test_chart_defaults_to_configured_timeframe(runtime_setup):
    runtime = runtime_setup["runtime"]
    runtime.office.settings.market.bar_timeframe = "1d"
    intervals = []
    market = runtime.office.get_env().market_data
    market.ohlcv = lambda symbol, interval, limit: intervals.append(interval) or []
    client = runtime_setup["client"]
    assert client.get("/v1/read/bars?ticker=AAPL").status_code == 200
    result = client.get("/v1/read/indicators?ticker=AAPL").json()
    assert result["timeframe"] == "1d"
    assert intervals and set(intervals) == {"1d"}
    client.get("/v1/read/bars?ticker=AAPL&timeframe=5m")
    assert intervals[-1] == "5m"


def test_indicators_aligned_with_bars(runtime_setup):
    client = runtime_setup["client"]
    market = runtime_setup["runtime"].office.get_env().market_data
    market.ohlcv = lambda symbol, interval, limit: [
        {
            "ts": f"2026-01-{i + 1:02d}T00:00:00Z",
            "o": 100 + i,
            "h": 105 + i,
            "l": 95 + i,
            "c": 100 + i,
            "v": 1000,
        }
        for i in range(30)
    ]
    response = client.get(
        "/v1/read/indicators", params={"ticker": "AAPL", "names": "ema20,rsi14,atr14"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["series"]) == 30
    assert len(data["indicators"]["ema20"]) == 30
    assert data["indicators"]["ema20"][0] is None
    assert isinstance(data["indicators"]["ema20"][-1], float)


def test_indicators_reject_invalid_window(runtime_setup):
    client = runtime_setup["client"]
    response = client.get("/v1/read/indicators", params={"ticker": "AAPL", "names": "ema0"})
    assert response.status_code == 422


def test_indicator_range_matches_bars(runtime_setup):
    client = runtime_setup["client"]
    params = {"ticker": "AAPL", "start": "2026-01-10T00:00:00Z", "end": "2026-01-12T00:00:00Z"}
    bars = client.get("/v1/read/bars", params=params).json()
    indicators = client.get("/v1/read/indicators", params=params).json()
    assert indicators["series"] == [bar["time"] for bar in bars]


def test_indicator_window_uses_prior_history(runtime_setup):
    client = runtime_setup["client"]
    full = client.get("/v1/read/indicators", params={"ticker": "AAPL", "names": "ema20", "limit": 35}).json()
    subset = client.get("/v1/read/indicators", params={"ticker": "AAPL", "names": "ema20", "limit": 5}).json()
    assert subset["series"] == full["series"][-5:]
    assert subset["indicators"]["ema20"] == full["indicators"]["ema20"][-5:]
    assert subset["indicators"]["ema20"][0] is not None


def test_indicators_supports_sma_macd_and_pivot(runtime_setup):
    client = runtime_setup["client"]
    market = runtime_setup["runtime"].office.get_env().market_data
    from datetime import datetime, timedelta
    base = datetime(2026, 1, 1, tzinfo=UTC)
    market.ohlcv = lambda symbol, interval, limit: [
        {"ts": (base + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ"), "o": 100 + i, "h": 105 + i, "l": 95 + i, "c": 100 + i, "v": 1000}
        for i in range(40)
    ]
    response = client.get("/v1/read/indicators", params={"ticker": "AAPL", "names": "sma20,macd,pivot"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["indicators"]["sma20"]) == 40
    assert len(data["indicators"]["macd_line"]) == 40
    assert len(data["indicators"]["pivot_p"]) == 40


def test_equity_history_query(runtime_setup):
    client = runtime_setup["client"]
    db = runtime_setup["runtime"].office.db
    db.insert_portfolio_snapshot(
        equity=10000.0, cash=5000.0, positions=[], ts="2026-01-01T10:00:00Z"
    )
    db.insert_portfolio_snapshot(
        equity=10500.0, cash=4500.0, positions=[], ts="2026-01-02T10:00:00Z"
    )
    response = client.get("/v1/read/equity_history")
    assert response.status_code == 200
    history = response.json()
    assert len(history) == 2
    assert history[0]["equity"] == 10000.0
    assert history[1]["equity"] == 10500.0


def test_equity_history_filters_dates(runtime_setup):
    client = runtime_setup["client"]
    db = runtime_setup["runtime"].office.db
    db.insert_portfolio_snapshot(equity=100, cash=50, ts="2026-01-01T00:00:00Z")
    db.insert_portfolio_snapshot(equity=200, cash=50, ts="2026-01-02T00:00:00Z")
    result = client.get("/v1/read/equity_history", params={"from": "2026-01-02T00:00:00Z"})
    assert [row["equity"] for row in result.json()] == [200]


def test_dev_server_runner_starts_and_responds(runtime_setup, monkeypatch):
    from scripts.dev_cockpit_server import create_dev_app

    app = create_dev_app(db_path=":memory:")
    client = TestClient(app)
    assert client.get("/v1/health").status_code == 200
    bars = client.get("/v1/read/bars?ticker=AAPL&limit=5").json()
    assert len(bars) == 5
    annotations = client.get("/v1/read/annotations?ticker=AAPL").json()
    assert len(annotations) >= 1


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
