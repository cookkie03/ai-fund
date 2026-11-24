"""Tests verifying the dev cockpit scenario extension for Assistente & Bridge Agent."""

from __future__ import annotations

import tempfile
from pathlib import Path

from bootstrap import build_test_office
from runtime.core import Runtime
from scripts.dev_cockpit_scenario import ScenarioMarketData, seed_scenario
from storage.office_db import OfficeDB


def test_dev_cockpit_scenario_seeds_four_bridge_conversations_with_required_properties():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = OfficeDB(Path(tmpdir) / "scenario.db")
        office = build_test_office(db=db)
        rt = Runtime(office=office)
        seed_scenario(rt, ScenarioMarketData())

        # 1. Total conversations: exactly 4 seeded conversations
        convs = rt.read.bridge_conversations(limit=10, archived=None)
        assert len(convs) == 4

        # 2. Conversation 1: has agent_relay from technical analyst and synthesis
        c1 = rt.read.bridge_conversation(1)
        assert c1 is not None
        assert c1["archived"] is False
        assert any(
            m["kind"] == "agent_relay" and m["author"] == "technical_analyst"
            for m in c1["messages"]
        )
        assert any(
            m["author"] == "bridge" and "supporto di AMD" in m["text"]
            for m in c1["messages"]
        )

        # 3. Conversation 2: has pending action of close_position with dry_run preview
        c2 = rt.read.bridge_conversation(2)
        assert c2 is not None
        assert c2["archived"] is False
        pending_act = next((m["action"] for m in c2["messages"] if m.get("action")), None)
        assert pending_act is not None
        assert pending_act["command"] == "close_position"
        assert pending_act["status"] == "pending"
        assert pending_act["capital"] is True
        assert pending_act["preview"] is not None
        assert pending_act["preview"]["ok"] is True

        # 4. Conversation 3: has an executed action and a dismissed action
        c3 = rt.read.bridge_conversation(3)
        assert c3 is not None
        assert c3["archived"] is False
        acts_c3 = [m["action"] for m in c3["messages"] if m.get("action")]
        assert any(a["status"] == "executed" for a in acts_c3)
        assert any(a["status"] == "dismissed" for a in acts_c3)

        # 5. Conversation 4: is archived
        c4 = rt.read.bridge_conversation(4)
        assert c4 is not None
        assert c4["archived"] is True
        assert len(c4["messages"]) >= 2


def test_dev_cockpit_scenario_seeds_briefing_with_all_ten_item_types_and_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = OfficeDB(Path(tmpdir) / "scenario.db")
        office = build_test_office(db=db)
        rt = Runtime(office=office)
        seed_scenario(rt, ScenarioMarketData())

        briefing = rt.read.briefing()
        assert briefing["since"] is not None
        assert briefing["summary_text"] is not None
        assert len(briefing["summary_text"]) > 20

        # Verify portfolio change data exists
        assert briefing["portfolio"] is not None
        assert "value" in briefing["portfolio"]

        # Verify all 10 item types are present
        item_types = {item["type"] for item in briefing["items"]}
        expected_types = {
            "trade",
            "order_pending",
            "proposal_pending",
            "proposal_decided",
            "alert",
            "halt",
            "resume",
            "dossier",
            "agent_error",
            "risk_limits",
        }
        assert expected_types.issubset(item_types), (
            f"Missing types: {expected_types - item_types}"
        )
