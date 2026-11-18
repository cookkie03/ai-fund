"""Smoke test opt-in: un ciclo reale con LLM veri, broker e dati finti.

Lancio manuale:
    OMNIROUTE_API_KEY=... uv run pytest tests/integration/test_office_smoke.py -m integration -q -s

OFFICE_SMOKE_ENDPOINT sovrascrive l'endpoint (default http://localhost:20128/v1). Il broker
è finto: nessun ordine raggiunge Alpaca.
"""

import os
from datetime import UTC, datetime

import pytest

from agents.backend import OpenAICompatibleBackend
from bootstrap import (
    CacheMarketDataAdapter,
    RoutingBackend,
    _lazy_init_data_cache,
    build_test_office,
)
from config.office_settings import OfficeSettings
from storage.office_db import OfficeDB
from workflows.scheduling import ScheduledTask, TaskSource


@pytest.mark.integration
def test_real_llm_cycle_on_fake_broker(tmp_path):
    api_key = os.environ.get("OMNIROUTE_API_KEY")
    if not api_key:
        pytest.skip("OMNIROUTE_API_KEY non impostata")
    endpoint = os.environ.get("OFFICE_SMOKE_ENDPOINT", "http://localhost:20128/v1")

    settings = OfficeSettings()
    settings = settings.model_copy(
        update={
            "agents": {
                name: cfg.model_copy(update={"endpoint": endpoint})
                for name, cfg in settings.agents.items()
            }
        }
    )
    backend = OpenAICompatibleBackend(api_key=api_key, timeout=180.0)
    db = OfficeDB(str(tmp_path / "smoke.db"))
    now = datetime.now(UTC)
    market_data = None
    if os.environ.get("OFFICE_SMOKE_LIVE_DATA") == "1":
        market_data = CacheMarketDataAdapter(_lazy_init_data_cache(db))
    office = build_test_office(
        db=db,
        market_data=market_data,
        backend=RoutingBackend({}, default_backend=backend),
        settings=settings,
        clock=lambda: now,
    )

    outcome = office.deliver(
        ScheduledTask(
            agent="portfolio_manager",
            chat="AAPL",
            when=now,
            source=TaskSource.MANUAL,
            reason="smoke test: valuta AAPL",
            data={},
        )
    )

    cycles = db.connection.execute("SELECT * FROM cycles WHERE ticker = 'AAPL'").fetchall()
    messages = db.connection.execute("SELECT author, text FROM messages").fetchall()
    tools = db.connection.execute("SELECT agent, tool, error FROM tool_calls").fetchall()
    print("outcome:", outcome)
    print("cycle:", [dict(c) for c in cycles])
    print("messages:", len(messages), "tool calls:", [(t["agent"], t["tool"]) for t in tools])
    assert cycles and cycles[-1]["status"] == "closed"
    assert messages
    for m in messages:
        print("MSG", m["author"], "|", (m["text"] or "")[:400].replace("\n", " "))
    for r in db.connection.execute("SELECT agent, model, tokens_in, tokens_out FROM llm_calls"):
        print("LLM", dict(r))
