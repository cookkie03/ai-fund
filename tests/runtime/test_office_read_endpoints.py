"""HTTP contract tests for the office read model."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from bootstrap import build_test_office
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB


def test_agents_include_configured_agents_and_only_todays_usage(tmp_path):
    db = OfficeDB(tmp_path / "office.db")
    office = build_test_office(db=db)
    client = TestClient(create_app(Runtime(office=office)))
    today = datetime.now(UTC)
    db.log_llm_call(agent="portfolio_manager", model="my-combo", tokens_in=100,
                    tokens_out=50, cost=0.015, duration_ms=10, ts=today.isoformat())
    db.log_llm_call(agent="portfolio_manager", model="my-combo", tokens_in=200,
                    tokens_out=100, cost=0.03, duration_ms=10, ts=(today - timedelta(days=1)).isoformat())

    response = client.get("/v1/read/agents")

    assert response.status_code == 200
    agents = response.json()
    assert {agent["name"] for agent in agents} == set(office.settings.agents)
    pm = next(agent for agent in agents if agent["name"] == "portfolio_manager")
    assert pm["model"] == office.settings.agents["portfolio_manager"].model
    assert pm["status"] == "idle"
    assert pm["today_tokens_in"] == 100
    assert pm["today_tokens_out"] == 50
    assert pm["today_cost"] == 0.015


def test_chat_topics_preserve_agent_configuration_and_messages(tmp_path):
    db = OfficeDB(tmp_path / "office.db")
    office = build_test_office(db=db)
    client = TestClient(create_app(Runtime(office=office)))
    chat_id = db.get_or_create_chat("technical_analyst", "NVDA")
    db.append_message(chat_id, "technical_analyst", "Analisi")
    db.append_message(chat_id, "user", "Grazie")
    db.get_or_create_chat("technical_analyst", "macro")
    response = client.get("/v1/read/chat_topics", params={"agent": "technical_analyst"})
    assert response.status_code == 200
    topics = response.json()
    assert len(topics) == 2
    topic = next(t for t in topics if t["topic"] == "NVDA")
    assert topic["id"] == chat_id
    assert topic["message_count"] == 2
    assert topic["last_message"]["text"] == "Grazie"
    assert len(client.get("/v1/read/chat", params={"agent": "technical_analyst", "topic": "NVDA"}).json()) == 2

    # Verify say command accepts topic field directly
    post_say = client.post("/v1/commands/say", json={"agent": "technical_analyst", "topic": "NVDA", "text": "Aggiornamento"})
    assert post_say.status_code == 200
    assert post_say.json()["ok"] is True
    assert len(client.get("/v1/read/chat", params={"agent": "technical_analyst", "topic": "NVDA"}).json()) == 3


def test_usage_filters_and_aggregates_calls(tmp_path):
    db = OfficeDB(tmp_path / "usage.db")
    client = TestClient(create_app(Runtime(office=build_test_office(db=db))))
    db.log_llm_call(agent="a", model="m", tokens_in=10, tokens_out=3, cost=0.5,
                    duration_ms=1, ts="2026-11-20T12:00:00Z")
    db.log_llm_call(agent="a", model="m", tokens_in=20, tokens_out=5, cost=1.0,
                    duration_ms=1, ts="2026-11-21T12:00:00Z")
    db.log_llm_call(agent="b", model="m", tokens_in=50, tokens_out=7, cost=2.0,
                    duration_ms=1, ts="2026-11-21T12:00:00Z")
    response = client.get("/v1/read/usage", params={"agent": "a", "from": "2026-11-21T00:00:00Z"})
    assert response.status_code == 200
    assert response.json() == [{"agent": "a", "tokens_in": 20, "tokens_out": 5,
                                "cost": 1.0, "calls": 1}]


def test_tool_calls_expose_context_and_compaction(tmp_path):
    db = OfficeDB(tmp_path / "tools.db")
    rt = Runtime(office=build_test_office(db=db))
    client = TestClient(create_app(rt))
    chat_id = db.get_or_create_chat("technical_analyst", "NVDA")
    call_id = db.log_tool_call("technical_analyst", "bars", {"ticker": "NVDA"},
                               {"count": 10}, chat_id=chat_id, duration_ms=42, cycle_id=7)
    db.log_tool_call("technical_analyst", "news", {}, {}, error="timeout", compacted=True)
    result = client.get("/v1/read/tool_calls", params={"agent": "technical_analyst"})
    assert result.status_code == 200
    calls = result.json()
    call = next(c for c in calls if c["id"] == call_id)
    assert call["duration_ms"] == 42
    assert call["cycle_id"] == 7
    assert call["topic"] == "NVDA"
    assert call["params"] == {"ticker": "NVDA"}
    assert call["success"] is True
    assert call["compacted"] is False
    assert next(c for c in calls if c["tool"] == "news")["compacted"] is True


def test_message_and_tool_events_are_published_only_after_commit(tmp_path):
    db = OfficeDB(tmp_path / "events.db")
    rt = Runtime(office=build_test_office(db=db))
    chat = db.get_or_create_chat("technical_analyst", "NVDA")
    received = []
    rt.bus.add_listener(received.append)
    with db.transaction():
        db.append_message(chat, "user", "Hello")
        db.log_tool_call("technical_analyst", "bars", {}, {}, chat_id=chat, duration_ms=42)
        assert received == []
    assert [event.type for event in received] == ["chat.message", "tool.called"]
    assert received[0].payload["topic"] == "NVDA"
    assert received[1].payload["duration_ms"] == 42
    assert received[1].payload["success"] is True


def test_agent_status_reflects_active_work_and_emits_event(tmp_path):
    db = OfficeDB(tmp_path / "status.db")
    rt = Runtime(office=build_test_office(db=db))
    client = TestClient(create_app(rt))
    db.set_agent_status("technical_analyst", "working", {"cycle_id": 4, "ticker": "NVDA"})
    agent = next(a for a in client.get("/v1/read/agents").json() if a["name"] == "technical_analyst")
    assert agent["status"] == "working"
    assert agent["current_task"]["ticker"] == "NVDA"
    assert agent["last_activity_ts"] is not None
    event = rt.event_log.since(0)[-1]
    assert event.type == "agent.status"
    assert event.payload["status"] == "working"


def test_dev_cockpit_scenario_seeds_office_data(tmp_path):
    from scripts.dev_cockpit_server import create_dev_app

    dev_db = str(tmp_path / "dev-scenario.db")
    app = create_dev_app(db_path=dev_db)
    client = TestClient(app)

    # 1. Agents
    agents = client.get("/v1/read/agents").json()
    assert len(agents) >= 7
    pm = next(a for a in agents if a["name"] == "portfolio_manager")
    assert pm["status"] == "working"
    assert pm["today_cost"] > 0
    assert pm["today_tokens"] > 0

    # 2. Topics for market_analyst and PM
    ma_topics = client.get("/v1/read/chat_topics", params={"agent": "market_analyst"}).json()
    assert any(t["topic"] == "macro" for t in ma_topics)
    assert any(t["topic"] == "semiconductors" for t in ma_topics)

    pm_topics = client.get("/v1/read/chat_topics", params={"agent": "portfolio_manager"}).json()
    assert any(t["topic"] == "direct" for t in pm_topics)

    # 3. Tool calls
    tool_calls = client.get("/v1/read/tool_calls").json()
    assert len(tool_calls) >= 5
    assert any(tc["compacted"] is True for tc in tool_calls)
    assert any(tc["success"] is False and tc["error"] is not None for tc in tool_calls)

    # 4. Usage
    usage = client.get("/v1/read/usage").json()
    assert len(usage) >= 3

