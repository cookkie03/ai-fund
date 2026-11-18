"""Tests for agent system prompts, loader, hashing, and tool scoping."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pytest

from agents.backend import AgentSpec
from bootstrap import build_agent_spec
from config.office_settings import OfficeSettings
from prompts.loader import ROLE_ALIASES, load_prompt
from storage.office_db import OfficeDB
from tools.environment import AgentEnvironment

EXPECTED_AGENTS = [
    "portfolio_manager",
    "market_analyst",
    "sentiment_analyst",
    "technical_analyst",
    "fundamental_analyst",
    "risk_analyst",
    "subagent",
]


class DummyMarketData:
    def quote(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "price": 100.0}

    def ohlcv(self, symbol: str, interval: str = "1d", limit: int = 100) -> list[dict[str, Any]]:
        return []

    def news(self, symbol: str | None = None, theme: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        return []

    def ratings(self, symbol: str) -> list[dict[str, Any]]:
        return []

    def insiders(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        return []

    def financials(self, symbol: str) -> dict[str, Any]:
        return {}

    def earnings_dates(self, symbol: str) -> list[dict[str, Any]]:
        return []

    def macro(self, series_id: str) -> list[dict[str, Any]]:
        return []

    def econ_calendar(self, limit: int = 20) -> list[dict[str, Any]]:
        return []

    def sector_perf(self) -> list[dict[str, Any]]:
        return []


class DummyBrokerReader:
    def get_account(self) -> dict[str, Any]:
        return {"equity": 100000.0, "cash": 50000.0}

    def get_positions(self) -> list[dict[str, Any]]:
        return []

    def get_orders(self, query: Any = None) -> list[Any]:
        return []


@pytest.fixture
def agent_environment() -> AgentEnvironment:
    db = OfficeDB(":memory:")
    return AgentEnvironment(
        db=db,
        market_data=DummyMarketData(),
        broker_reader=DummyBrokerReader(),
    )


def test_every_agent_has_prompt():
    """Ensure every office agent has a corresponding prompt file."""
    for agent in EXPECTED_AGENTS:
        text, p_hash = load_prompt(agent)
        assert isinstance(text, str)
        assert len(text) > 100
        assert len(p_hash) == 64
        assert text.lstrip().startswith("<!-- DRAFT")


def test_role_aliases():
    """Ensure common role aliases resolve correctly."""
    for alias, canonical in ROLE_ALIASES.items():
        text_alias, hash_alias = load_prompt(alias)
        text_canon, hash_canon = load_prompt(canonical)
        assert text_alias == text_canon
        assert hash_alias == hash_canon


def test_unknown_agent_raises():
    """Ensure unknown agent names raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_agent_role")


def test_hashes_are_stable_and_differ():
    """Verify hashes are deterministic, match sha256, and differ across agents."""
    hashes: set[str] = set()

    for agent in EXPECTED_AGENTS:
        text1, hash1 = load_prompt(agent)
        text2, hash2 = load_prompt(agent)

        # Stability
        assert hash1 == hash2
        expected_hash = hashlib.sha256(text1.encode("utf-8")).hexdigest()
        assert hash1 == expected_hash

        # Different when text differs
        tampered_hash = hashlib.sha256((text1 + "\n# Extra").encode("utf-8")).hexdigest()
        assert hash1 != tampered_hash

        hashes.add(hash1)

    # Every agent prompt has a unique hash
    assert len(hashes) == len(EXPECTED_AGENTS)


def test_every_tool_name_mentioned_in_prompt_exists_in_tools_for(agent_environment: AgentEnvironment):
    """Every tool name mentioned in an agent's prompt must exist in tools_for for that role."""
    # Collect all existing tool names across all roles
    all_system_tools: set[str] = set()
    role_tools: dict[str, set[str]] = {}

    for agent in EXPECTED_AGENTS:
        tools = agent_environment.tools_for(agent)
        names = {t.name for t in tools}
        role_tools[agent] = names
        all_system_tools.update(names)

    # Check each prompt
    for agent in EXPECTED_AGENTS:
        text, _ = load_prompt(agent)
        allowed_for_agent = role_tools[agent]

        # Check for any tool from all_system_tools that appears as a distinct word in text
        for tool_name in all_system_tools:
            # Pattern matches tool name as an identifier / code snippet / word
            pattern = rf"\b{re.escape(tool_name)}\b"
            if re.search(pattern, text):
                assert (
                    tool_name in allowed_for_agent
                ), f"Agent '{agent}' prompt mentions tool '{tool_name}' which is NOT in its tools_for ({allowed_for_agent})"


def test_prompt_content_and_domain_rules():
    """Verify specific domain requirements in prompts."""
    # Market Analyst: catalyst to PM, schedule_task, macro
    ma_text, _ = load_prompt("market_analyst")
    assert "catalizzator" in ma_text.lower()
    assert "send_message" in ma_text
    assert "schedule_task" in ma_text

    # Technical Analyst: ATR multipliers (k_stop, k_tp, k_trail)
    ta_text, _ = load_prompt("technical_analyst")
    assert "k_stop" in ta_text
    assert "k_tp" in ta_text
    assert "k_trail" in ta_text
    assert "indicators" in ta_text

    # Fundamental Analyst: financials, ratios, earnings_dates, rischio evento
    fa_text, _ = load_prompt("fundamental_analyst")
    assert "financials" in fa_text
    assert "ratios" in fa_text
    assert "earnings_dates" in fa_text
    assert "rischio evento" in fa_text.lower()

    # Risk Analyst: contrary thesis, k_entry, risk_fraction, portfolio_risk
    ra_text, _ = load_prompt("risk_analyst")
    assert "contrari" in ra_text.lower()
    assert "k_entry" in ra_text
    assert "risk_fraction" in ra_text
    assert "portfolio_risk" in ra_text

    # PM: schedule_next_check, accept_order, defer, watchlist
    pm_text, _ = load_prompt("portfolio_manager")
    assert "schedule_next_check" in pm_text
    assert "accept_order" in pm_text
    assert "defer" in pm_text
    assert "watchlist_get" in pm_text
    assert "obbligo" in pm_text.lower()

    # Subagent: read-only, no messaging or orders
    sub_text, _ = load_prompt("subagent")
    assert "sola lettura" in sub_text.lower()
    assert "read_state" in sub_text
    assert "read_portfolio" in sub_text

    # General constraints across all main agents
    for agent in EXPECTED_AGENTS:
        txt, _ = load_prompt(agent)
        txt_lower = txt.lower()
        assert "paper" in txt_lower
        assert "live" in txt_lower
        assert "token" in txt_lower or "costi" in txt_lower


def test_bootstrap_build_agent_spec():
    """Verify bootstrap.build_agent_spec initializes AgentSpec with loaded prompt and hash."""
    settings = OfficeSettings()
    for agent in EXPECTED_AGENTS:
        spec: AgentSpec = build_agent_spec(agent, settings)
        assert spec.name == agent
        assert len(spec.system_prompt) > 0
        assert len(spec.prompt_hash) == 64
        expected_hash = hashlib.sha256(spec.system_prompt.encode("utf-8")).hexdigest()
        assert spec.prompt_hash == expected_hash
