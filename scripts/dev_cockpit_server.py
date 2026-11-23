"""Standalone development server for the Cockpit frontend with synthetic data."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI

logger = logging.getLogger(__name__)

if __package__ in (None, ""):
    # `python scripts/dev_cockpit_server.py` from the repo root: make the root importable.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bootstrap import build_test_office  # noqa: E402
from runtime.core import Runtime  # noqa: E402
from runtime.http import create_app  # noqa: E402
from scripts.dev_cockpit_scenario import ScenarioMarketData, seed_scenario  # noqa: E402
from storage.office_db import OfficeDB  # noqa: E402


def create_dev_app(db_path: str = "data/dev-cockpit.db", approval_mode: str = "manual") -> FastAPI:
    if db_path != ":memory:":
        # The scenario is regenerated on every start, relative to the current time.
        for suffix in ("", "-wal", "-shm", ".lock"):
            Path(db_path + suffix).unlink(missing_ok=True)
    db = OfficeDB(db_path)
    market = ScenarioMarketData()
    office = build_test_office(db=db, market_data=market, approval_mode=approval_mode)
    rt = Runtime(office=office, account_label="dev-cockpit")
    seed_scenario(rt, market)
    app = create_app(rt, token=None, host="127.0.0.1")

    async def _live_event_simulator() -> None:
        steps = [
            lambda: rt.office.db.log_tool_call(
                agent="technical_analyst",
                tool="indicators",
                params={"ticker": "NVDA", "timeframe": "1h"},
                result={"ema20": 174.6, "rsi14": 63.4},
                duration_ms=75,
                cycle_id=2,
                chat_id=rt.office.db.get_or_create_chat("technical_analyst", "NVDA"),
            ),
            lambda: rt.office.db.append_message(
                rt.office.db.get_or_create_chat("market_analyst", "semiconductors"),
                author="market_analyst",
                text="Volumi SOXX costanti nella sessione pomeridiana, supporto a 220 confermato.",
            ),
            lambda: rt.office.db.set_agent_status(
                "technical_analyst",
                "working",
                {"type": "cycle", "ticker": "AMD", "cycle_id": 3, "description": "Verifica candela 1h"},
            ),
            lambda: rt.office.db.log_tool_call(
                agent="market_analyst",
                tool="macro_series",
                params={"series_id": "DGS10"},
                result={"yield": 4.41},
                duration_ms=110,
                chat_id=rt.office.db.get_or_create_chat("market_analyst", "macro"),
            ),
        ]
        idx = 0
        while True:
            await asyncio.sleep(10.0)
            try:
                action = steps[idx % len(steps)]
                idx += 1
                action()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Error in dev live event simulator: {exc}")

    @app.on_event("startup")
    async def on_startup() -> None:
        asyncio.create_task(_live_event_simulator())

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Avvia il dev server con dati finti")
    parser.add_argument("--host", choices=("127.0.0.1", "localhost", "::1"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default="data/dev-cockpit.db")
    parser.add_argument("--approval-mode", choices=("manual", "auto"), default="manual")
    args = parser.parse_args()
    app = create_dev_app(db_path=args.db, approval_mode=args.approval_mode)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
