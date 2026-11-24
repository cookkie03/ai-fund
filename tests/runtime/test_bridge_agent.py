"""Unit and integration tests for Bridge Agent, turns, tools, commands, and briefing."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from agents.backend import StepResult, ToolCall
from agents.fake_backend import ScriptedBackend, ScriptedBridgeBackend
from bootstrap import build_test_office
from runtime.commands import (
    BridgeActionDecide,
    BridgeSay,
    BridgeStop,
    Halt,
    MarkBriefingSeen,
)
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB


def _wait_for_turn(runtime: Runtime, conv_id: int, timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    time.sleep(0.05)
    while time.time() < deadline:
        with runtime.bridge_runner._lock:
            active = (
                conv_id in runtime.bridge_runner._active_conversations
                or conv_id in runtime.bridge_runner._queued_conversations
            )
        conv = runtime.office.db.get_bridge_conversation(conv_id)
        if not active and conv and conv["status"] == "idle":
            return
        time.sleep(0.02)
    raise TimeoutError(f"Turn for conversation {conv_id} did not complete within {timeout}s")


def test_bridge_say_creates_conversation_and_turn_with_status_transitions(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    rt.bridge_runner.set_backend(ScriptedBridgeBackend())

    statuses = []
    rt.bus.add_listener(lambda ev: statuses.append(ev) if ev.type == "bridge.status" else None)

    # Send say without conversation_id -> creates new conversation
    res = rt.execute(BridgeSay(conversation_id=None, text="Verifica il portafoglio"), actor="luca")
    assert res.ok is True
    conv_id = res.data["conversation_id"]
    assert conv_id > 0

    _wait_for_turn(rt, conv_id)

    conv = rt.office.db.get_bridge_conversation(conv_id)
    assert conv["status"] == "idle"

    # Verify messages
    msgs = rt.office.db.list_bridge_messages(conv_id)
    assert len(msgs) == 2
    assert msgs[0]["author"] == "luca"
    assert msgs[0]["kind"] == "text"
    assert msgs[1]["author"] == "bridge"
    assert msgs[1]["kind"] == "text"

    # Status transitioned: thinking -> tool -> thinking -> idle
    status_types = [
        ev.payload["status"] for ev in statuses if ev.payload["conversation_id"] == conv_id
    ]
    assert "thinking" in status_types
    assert "idle" in status_types


def test_parallel_conversations_isolated_and_queued_messages(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    rt.bridge_runner.set_backend(ScriptedBridgeBackend())

    # Create two conversations
    res1 = rt.execute(BridgeSay(conversation_id=None, text="Prima conversazione"), actor="luca")
    res2 = rt.execute(BridgeSay(conversation_id=None, text="Seconda conversazione"), actor="luca")

    c1 = res1.data["conversation_id"]
    c2 = res2.data["conversation_id"]
    assert c1 != c2

    _wait_for_turn(rt, c1)
    _wait_for_turn(rt, c2)

    msgs1 = rt.office.db.list_bridge_messages(c1)
    msgs2 = rt.office.db.list_bridge_messages(c2)

    assert all(m["conversation_id"] == c1 for m in msgs1)
    assert all(m["conversation_id"] == c2 for m in msgs2)

    # Queue second message into c1
    rt.execute(BridgeSay(conversation_id=c1, text="Secondo messaggio su c1"), actor="luca")
    _wait_for_turn(rt, c1)

    msgs1_updated = rt.office.db.list_bridge_messages(c1)
    assert len(msgs1_updated) >= 4
    assert msgs1_updated[-1]["author"] == "bridge"
    assert msgs1_updated[-2]["author"] == "luca"
    assert msgs1_updated[-2]["text"] == "Secondo messaggio su c1"


def test_message_agent_and_agent_relay_and_pm_task(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    rt.bridge_runner.set_backend(ScriptedBridgeBackend())

    # Start conversation asking to relay with technical_analyst
    res = rt.execute(
        BridgeSay(conversation_id=None, text="Invia un messaggio a Technical Analyst su AMD"),
        actor="luca",
    )
    conv_id = res.data["conversation_id"]
    _wait_for_turn(rt, conv_id)

    # Check chat of technical_analyst
    tech_chat = (
        db.get_chat_by_agent_topic("technical_analyst", "AMD")
        if hasattr(db, "get_chat_by_agent_topic")
        else None
    )
    if not tech_chat:
        cid = db.get_or_create_chat("technical_analyst", "AMD")
    else:
        cid = tech_chat["id"]
    chat_msgs = db.list_messages(cid)
    assert any("[Per conto di Luca]" in m["text"] for m in chat_msgs)

    # Technical Analyst replies in the chat
    db.append_message(
        chat_id=cid,
        author="technical_analyst",
        text="Livello di supporto a 118.50$ confermato con divergenza rialzista.",
    )

    # Wait for the relay turn triggered by commit
    _wait_for_turn(rt, conv_id)

    bridge_msgs = db.list_bridge_messages(conv_id)
    relay_msg = next((m for m in bridge_msgs if m["kind"] == "agent_relay"), None)
    assert relay_msg is not None
    assert relay_msg["author"] == "technical_analyst"
    # Verify that the relay triggered an automatic synthesis turn from Bridge
    synthesis_msg = next(
        (m for m in bridge_msgs if m["author"] == "bridge" and m["id"] > relay_msg["id"]), None
    )
    assert synthesis_msg is not None, "Bridge must synthesize response after agent_relay"
    assert synthesis_msg["kind"] == "text"

    # Also test message to PM creates Scheduled task
    res_pm = rt.execute(
        BridgeSay(conversation_id=None, text="Chiedi a Portfolio Manager su NVDA di valutare"),
        actor="luca",
    )
    _wait_for_turn(rt, res_pm.data["conversation_id"])

    # Directly verify tool message_agent to PM creates scheduled task
    from tools.bridge_tools import build_bridge_tools

    tools = build_bridge_tools(rt, conv_id)
    msg_tool = next(t for t in tools if t.name == "message_agent")
    msg_tool.fn(agent="portfolio_manager", topic="NVDA", text="Controlla la tesi")

    due_tasks = db.due_scheduled_tasks(rt.office.get_now_iso())
    assert any(t["agent"] == "portfolio_manager" and t["chat"] == "NVDA" for t in due_tasks)


def test_action_without_capital_executed_immediately_with_actor_bridge(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    from tools.bridge_tools import build_bridge_tools

    tools = build_bridge_tools(rt, conversation_id=1)
    add_w_tool = next(t for t in tools if t.name == "add_watchlist")
    res = add_w_tool.fn(ticker="MSFT", note="Aggiunto per test")
    assert res["ok"] is True

    # Watchlist updated with actor bridge
    watch = rt.read.watchlist()
    assert any(w.ticker == "MSFT" and w.added_by == "bridge" for w in watch)

    # Test add dossier note
    add_note_tool = next(t for t in tools if t.name == "add_dossier_note")
    res_note = add_note_tool.fn(ticker="MSFT", text="Verifica livelli")
    assert res_note["ok"] is True
    dossier = rt.read.dossier("MSFT")
    assert dossier is not None
    assert any("[Bridge per Luca]" in n["text"] for n in dossier.get("notes", []))


def test_capital_action_only_proposed_pending_and_confirmation_flow(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    conv_id = db.create_bridge_conversation(title="Test Azioni")

    from tools.bridge_tools import CAPITAL_COMMAND_MODELS, build_bridge_tools

    # 1. Negative test: Capital commands are NOT in the Bridge tools catalog directly
    tools = build_bridge_tools(rt, conversation_id=conv_id)
    tool_names = {t.name for t in tools}
    for cap_cmd in CAPITAL_COMMAND_MODELS:
        assert cap_cmd not in tool_names, (
            f"Capital command '{cap_cmd}' must NOT be in tool registry"
        )

    assert "propose_action" in tool_names

    # 2. Propose action: close_position without an open trade -> preview reflects state
    prop_tool = next(t for t in tools if t.name == "propose_action")
    action_data = prop_tool.fn(
        command="close_position",
        payload={"ticker": "NVDA", "qty": 5.0, "order_type": "market"},
        summary="Chiudi 5 NVDA",
    )
    assert action_data["status"] == "pending"
    assert action_data["capital"] is True
    action_id = action_data["id"]

    # 3. bridge_action_decide without confirm: true is rejected by pydantic validator
    with pytest.raises(ValueError):
        BridgeActionDecide(action_id=action_id, decision="confirm", confirm=False)

    # 4. Deciding confirm when position does not exist fails from original handler
    decide_res = rt.execute(
        BridgeActionDecide(action_id=action_id, decision="confirm", confirm=True),
        actor="luca",
    )
    assert decide_res.ok is False
    assert any("nessuna posizione" in r.lower() for r in decide_res.reasons)
    action_after = db.get_bridge_action(action_id)
    assert action_after["status"] == "failed"

    # 5. Dismiss action
    action2 = prop_tool.fn(
        command="close_position",
        payload={"ticker": "NVDA", "qty": 5.0, "order_type": "market"},
        summary="Altro tentativo NVDA",
    )
    dismiss_res = rt.execute(
        BridgeActionDecide(action_id=action2["id"], decision="dismiss", confirm=False),
        actor="luca",
    )
    assert dismiss_res.ok is True
    assert db.get_bridge_action(action2["id"])["status"] == "dismissed"

    # 6. Halt blocks action confirmation (with real open position on NVDA)
    oid = db.insert_order(
        ticker="NVDA",
        side="buy",
        draft={"symbol": "NVDA", "side": "buy"},
        draft_hash="hash_nvda_halt",
        client_order_id="c_nvda_halt",
        approval_status="approved",
        status="filled",
    )
    db.insert_trade(
        ticker="NVDA",
        entry_order_id=oid,
        entry_price=150.0,
        qty=10.0,
        opened_ts=office.get_now_iso(),
        stop_price=140.0,
        target_price=170.0,
    )
    action3 = prop_tool.fn(
        command="close_position",
        payload={"ticker": "NVDA", "qty": 5.0, "order_type": "market"},
        summary="Azione sotto Halt",
    )
    rt.execute(Halt(reason="Emergenza", confirm=True), actor="luca")
    halt_res = rt.execute(
        BridgeActionDecide(action_id=action3["id"], decision="confirm", confirm=True),
        actor="luca",
    )
    assert halt_res.ok is False
    assert any("halt" in r.lower() for r in halt_res.reasons)


def test_budget_exhaustion_emits_error_message(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    # Set low daily budget
    office.settings.agents["bridge"].daily_budget = 0.05
    rt = Runtime(office=office)
    rt.bridge_runner.set_backend(ScriptedBridgeBackend())

    # Log LLM calls to exhaust budget
    db.log_llm_call(
        agent="bridge",
        model="my-combo",
        tokens_in=2000,
        tokens_out=500,
        cost=0.10,
        duration_ms=1000,
        ts=datetime.now(UTC).isoformat(),
    )

    res = rt.execute(BridgeSay(conversation_id=None, text="Test budget"), actor="luca")
    conv_id = res.data["conversation_id"]
    _wait_for_turn(rt, conv_id)

    msgs = db.list_bridge_messages(conv_id)
    err_msg = next((m for m in msgs if m["kind"] == "error"), None)
    assert err_msg is not None
    assert "budget" in err_msg["text"].lower()


def test_bridge_stop_interrupts_turn(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    # Slow custom backend to allow requesting stop
    def slow_step(agent, ctx, tools):
        time.sleep(0.1)
        return StepResult(
            tool_calls=[ToolCall(id="tc-1", name="read_portfolio", args={})],
            done=False,
        )

    rt.bridge_runner.set_backend(ScriptedBackend(slow_step))
    res = rt.execute(BridgeSay(conversation_id=None, text="Operazione lunga"), actor="luca")
    conv_id = res.data["conversation_id"]

    # Immediately request stop
    stop_res = rt.execute(BridgeStop(conversation_id=conv_id), actor="luca")
    assert stop_res.ok is True

    _wait_for_turn(rt, conv_id)
    conv = db.get_bridge_conversation(conv_id)
    assert conv["status"] == "idle"


def test_briefing_reading_and_marking_seen(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    # Insert events and alerts
    db.add_inbox("alert", "Alert prezzo NVDA sopra resistenza", ts=datetime.now(UTC).isoformat())

    b = rt.read.briefing()
    assert b["since"] is not None
    assert len(b["items"]) >= 1
    assert any(i["type"] == "alert" for i in b["items"])

    # Mark briefing seen
    new_seen = (datetime.now(UTC) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    mark_res = rt.execute(MarkBriefingSeen(ts=new_seen), actor="luca")
    assert mark_res.ok is True
    assert mark_res.data["since"] == new_seen

    # Now briefing since new_seen has 0 items
    b2 = rt.read.briefing()
    assert b2["since"] == new_seen
    assert len(b2["items"]) == 0

    # Exhaust bridge daily budget -> summary_text is None for uncached since
    office.settings.agents["bridge"].daily_budget = 0.01
    db.log_llm_call(
        agent="bridge",
        model="my-combo",
        tokens_in=1000,
        tokens_out=200,
        cost=0.05,
        duration_ms=500,
        ts=datetime.now(UTC).isoformat(),
    )
    custom_since = (datetime.now(UTC) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    b_no_budget = rt.read.briefing(since=custom_since)
    assert b_no_budget["summary_text"] is None


def test_bridge_http_endpoints_and_idempotency(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    rt.bridge_runner.set_backend(ScriptedBridgeBackend())
    client = TestClient(create_app(rt))

    # 1. Post bridge_say with Idempotency-Key
    resp = client.post(
        "/v1/commands/bridge_say",
        json={"conversation_id": None, "text": "Ciao Bridge"},
        headers={"Idempotency-Key": "idemp-bridge-1", "X-Actor": "luca"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    conv_id = data["conversation_id"]

    # Repeat with same key -> same result
    resp2 = client.post(
        "/v1/commands/bridge_say",
        json={"conversation_id": None, "text": "Ciao Bridge"},
        headers={"Idempotency-Key": "idemp-bridge-1", "X-Actor": "luca"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["conversation_id"] == conv_id

    _wait_for_turn(rt, conv_id)

    # 2. GET bridge_conversations
    r_convs = client.get("/v1/read/bridge_conversations")
    assert r_convs.status_code == 200
    convs = r_convs.json()
    assert len(convs) >= 1
    assert convs[0]["id"] == conv_id

    # 3. GET bridge_conversation
    r_conv = client.get("/v1/read/bridge_conversation", params={"id": conv_id})
    assert r_conv.status_code == 200
    conv_detail = r_conv.json()
    assert len(conv_detail["messages"]) >= 2

    # 4. Rename & Archive
    client.post(
        "/v1/commands/bridge_rename_conversation",
        json={"conversation_id": conv_id, "title": "Nuovo Titolo"},
        headers={"Idempotency-Key": "idemp-ren-1", "X-Actor": "luca"},
    )
    r_conv_ren = client.get("/v1/read/bridge_conversation", params={"id": conv_id}).json()
    assert r_conv_ren["title"] == "Nuovo Titolo"

    client.post(
        "/v1/commands/bridge_archive_conversation",
        json={"conversation_id": conv_id, "archived": True},
        headers={"Idempotency-Key": "idemp-arc-1", "X-Actor": "luca"},
    )
    r_conv_arc = client.get("/v1/read/bridge_conversations", params={"archived": "true"}).json()
    assert any(c["id"] == conv_id for c in r_conv_arc)

    # 5. GET briefing
    r_brief = client.get("/v1/read/briefing")
    assert r_brief.status_code == 200
    assert "counts" in r_brief.json()


def test_bridge_agent_appears_in_read_agents_as_core_without_supervisor(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    client = TestClient(create_app(rt))

    response = client.get("/v1/read/agents")
    assert response.status_code == 200
    agents = response.json()

    bridge = next((a for a in agents if a["name"] == "bridge"), None)
    assert bridge is not None, "Bridge agent must appear in GET /v1/read/agents"
    assert bridge["kind"] == "core"
    assert bridge["supervisor"] is None
    assert bridge["role"] == "bridge"
    assert bridge["model"] == office.settings.agents["bridge"].model
    assert bridge["status"] == "idle"


def test_bridge_events_published_only_at_commit_never_on_rollback(tmp_path):
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    received_events = []
    rt.bus.add_listener(lambda ev: received_events.append(ev))

    # 1. Rollback test: events emitted inside a rolling back transaction must NOT reach bus
    try:
        with db.transaction():
            cid = db.create_bridge_conversation(title="Rollback Test")
            db.append_bridge_message(cid, "luca", "text", "Test che fallisce")
            db.set_briefing_seen()
            assert received_events == [], "No events should be published before commit"
            raise RuntimeError("Forced rollback")
    except RuntimeError:
        pass

    assert received_events == [], "Events from rolled back transaction must never be published"

    # 2. Commit test: events are only published when transaction commits
    with db.transaction():
        cid2 = db.create_bridge_conversation(title="Commit Test")
        db.append_bridge_message(cid2, "luca", "text", "Messaggio valido")
        db.set_briefing_seen()
        assert received_events == [], "No events should be published while transaction is active"

    # Now transaction has committed
    types = [ev.type for ev in received_events]
    assert "briefing.updated" in types
    assert len(received_events) > 0


def test_bridge_conversation_pagination_and_search_filter(tmp_path):
    """TDD red-green verification for conversation search q and pagination before."""
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    client = TestClient(create_app(rt))

    # Phase 2 (GREEN): Complete test implementation
    # Create 2 conversations: one matching on title, one on message text
    cid1 = db.create_bridge_conversation(title="Analisi Ticker TSLA")
    mid1_1 = db.append_bridge_message(cid1, "luca", "text", "Primo messaggio")
    mid1_2 = db.append_bridge_message(cid1, "bridge", "text", "Secondo messaggio")
    mid1_3 = db.append_bridge_message(
        cid1, "luca", "text", "Terzo messaggio con parola speciale: SegretoInfrasettimanale"
    )

    cid2 = db.create_bridge_conversation(title="Discussione Macro Generale")
    db.append_bridge_message(cid2, "luca", "text", "Nessun segreto qui")

    # 1. Search 'q' on title
    resp_q_title = client.get("/v1/read/bridge_conversations", params={"q": "TSLA"}).json()
    assert len(resp_q_title) == 1
    assert resp_q_title[0]["id"] == cid1
    assert resp_q_title[0]["title"] == "Analisi Ticker TSLA"
    assert resp_q_title[0]["message_count"] == 3
    assert (
        resp_q_title[0]["last_message"]["text"]
        == "Terzo messaggio con parola speciale: SegretoInfrasettimanale"
    )

    # 2. Search 'q' on message text
    resp_q_text = client.get(
        "/v1/read/bridge_conversations", params={"q": "SegretoInfrasettimanale"}
    ).json()
    assert len(resp_q_text) == 1
    assert resp_q_text[0]["id"] == cid1

    # 3. Pagination with 'before' and 'limit'
    # Requesting limit=2 before mid1_3 should return [mid1_1, mid1_2] in chronological order
    resp_page = client.get(
        "/v1/read/bridge_conversation", params={"id": cid1, "limit": 2, "before": mid1_3}
    ).json()
    msgs = resp_page["messages"]
    assert len(msgs) == 2
    assert msgs[0]["id"] == mid1_1
    assert msgs[1]["id"] == mid1_2
    assert msgs[0]["text"] == "Primo messaggio"
    assert msgs[1]["text"] == "Secondo messaggio"

    # 4. Search with archived='all' should return both active and archived conversations
    cid_archived = db.create_bridge_conversation(
        title="Archiviata SegretoInfrasettimanale", archived=True
    )
    resp_archived_all = client.get(
        "/v1/read/bridge_conversations", params={"q": "SegretoInfrasettimanale", "archived": "all"}
    ).json()
    assert len(resp_archived_all) == 2
    assert {c["id"] for c in resp_archived_all} == {cid1, cid_archived}


def test_bridge_replaces_provisional_title_after_first_turn(tmp_path):
    """TDD: verify that Bridge replaces provisional raw title with a crisp short title after turn 1."""
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    rt.bridge_runner.set_backend(ScriptedBridgeBackend())

    # Send say without conversation_id and a long initial message
    long_prompt = "Vorrei controllare il portafoglio e vedere se le posizioni su AAPL sono sicure"
    res = rt.execute(BridgeSay(conversation_id=None, text=long_prompt), actor="luca")
    assert res.ok is True
    conv_id = res.data["conversation_id"]

    # Initial provisional title before the turn completes
    initial_conv = db.get_bridge_conversation(conv_id)
    assert initial_conv["title"].endswith("...")

    _wait_for_turn(rt, conv_id)

    # After first turn, the Bridge must have replaced the provisional title with a crisp title
    updated_conv = db.get_bridge_conversation(conv_id)
    assert not updated_conv["title"].endswith("...")
    assert len(updated_conv["title"]) <= 35
    # The crisp title must reference the discussed topic/ticker rather than being cut off mid-word
    assert "AAPL" in updated_conv["title"] or "Portafoglio" in updated_conv["title"]
    assert not updated_conv["title"].endswith("portafog")


def test_bridge_sse_event_shapes_conform_to_handoff_contract(tmp_path):
    """Verify that all bridge SSE events conform exactly to the handoff contract shapes."""
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    captured_events = []
    rt.bus.add_listener(lambda ev: captured_events.append(ev))

    seen_ts = "2026-11-24T00:00:00Z"
    with db.transaction():
        cid = db.create_bridge_conversation(title="Test SSE Contract")
        db.append_bridge_message(
            cid,
            "luca",
            "text",
            "Messaggio di test evento",
            context={"page": "terminale", "ticker": "AAPL"},
            refs=[{"type": "ticker", "id": "AAPL", "label": "AAPL"}],
        )
        db.create_bridge_action(
            conversation_id=cid,
            command="close_position",
            payload={"ticker": "AAPL", "qty": 5.0},
            summary="Chiudi 5 AAPL",
            capital=True,
            status="pending",
            preview={"ok": True, "reasons": [], "detail": {"dry_run": True}},
        )
        db.set_briefing_seen(seen_ts)

    # 1. bridge.conversation: {conversation: {id, title, created_ts, updated_ts, status, archived}}
    ev_conv = next(e for e in captured_events if e.type == "bridge.conversation")
    conv_obj = ev_conv.payload["conversation"]
    for field in ("id", "title", "created_ts", "updated_ts", "status", "archived"):
        assert field in conv_obj, f"Missing field {field} in bridge.conversation payload"

    # 2. bridge.message: {conversation_id, message: {id, conversation_id, author, kind, text, ts, context, refs, action}}
    ev_msg = next(e for e in captured_events if e.type == "bridge.message")
    assert ev_msg.payload["conversation_id"] == cid
    msg_obj = ev_msg.payload["message"]
    for field in (
        "id",
        "conversation_id",
        "author",
        "kind",
        "text",
        "ts",
        "context",
        "refs",
        "action",
    ):
        assert field in msg_obj, f"Missing field {field} in bridge.message payload"
    assert msg_obj["context"]["ticker"] == "AAPL"

    # 3. bridge.action: {conversation_id, action: {id, command, summary, capital, status, preview, result_reasons, decided_ts, decided_by}}
    ev_act = next(e for e in captured_events if e.type == "bridge.action")
    assert ev_act.payload["conversation_id"] == cid
    act_obj = ev_act.payload["action"]
    for field in ("id", "command", "summary", "capital", "status", "preview", "result_reasons"):
        assert field in act_obj, f"Missing field {field} in bridge.action payload"

    # 4. briefing.updated: {since}
    ev_brf = next(e for e in captured_events if e.type == "briefing.updated")
    assert ev_brf.payload["since"] == seen_ts

    # 5. tool.started and tool.finished emission for bridge tools
    from tools.bridge_tools import build_bridge_tools

    tools = build_bridge_tools(rt, conversation_id=cid)
    port_tool = next(t for t in tools if t.name == "read_portfolio")
    port_tool.fn()

    ev_start = next(e for e in captured_events if e.type == "tool.started")
    assert ev_start.payload["agent"] == "bridge"
    assert ev_start.payload["tool"] == "read_portfolio"
    assert ev_start.payload["conversation_id"] == cid

    ev_finish = next(e for e in captured_events if e.type == "tool.finished")
    assert ev_finish.payload["agent"] == "bridge"
    assert ev_finish.payload["tool"] == "read_portfolio"
    assert ev_finish.payload["conversation_id"] == cid
    assert ev_finish.payload["success"] is True


def test_bridge_actions_filter_by_conversation_and_limit(tmp_path):
    """TDD: verify GET /v1/read/bridge_actions supports conversation_id and limit filters."""
    db = OfficeDB(tmp_path / "bridge.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    client = TestClient(create_app(rt))

    cid1 = db.create_bridge_conversation(title="Conv 1")
    cid2 = db.create_bridge_conversation(title="Conv 2")

    # Create two actions for cid1 and one action for cid2
    act1 = db.create_bridge_action(
        conversation_id=cid1,
        command="close_position",
        payload={"ticker": "AAPL", "qty": 1.0},
        summary="Chiudi AAPL",
        status="pending",
    )
    act2 = db.create_bridge_action(
        conversation_id=cid1,
        command="close_position",
        payload={"ticker": "MSFT", "qty": 2.0},
        summary="Chiudi MSFT",
        status="pending",
    )
    act3 = db.create_bridge_action(
        conversation_id=cid2,
        command="close_position",
        payload={"ticker": "GOOGL", "qty": 3.0},
        summary="Chiudi GOOGL",
        status="pending",
    )

    # Filtering by conversation_id=cid1 must only return actions for cid1
    resp_conv = client.get("/v1/read/bridge_actions", params={"conversation_id": cid1}).json()
    assert len(resp_conv) == 2
    assert {a["id"] for a in resp_conv} == {act1, act2}
    assert all(a["conversation_id"] == cid1 for a in resp_conv)

    # Filtering by conversation_id=cid1 with limit=1 must return only the newest action for cid1
    resp_limit = client.get(
        "/v1/read/bridge_actions", params={"conversation_id": cid1, "limit": 1}
    ).json()
    assert len(resp_limit) == 1
    assert resp_limit[0]["id"] == act2

    # Filtering by conversation_id=cid2 must return act3
    resp_cid2 = client.get("/v1/read/bridge_actions", params={"conversation_id": cid2}).json()
    assert len(resp_cid2) == 1
    assert resp_cid2[0]["id"] == act3

