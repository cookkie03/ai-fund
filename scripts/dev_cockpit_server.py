"""Standalone development server for the Cockpit frontend with synthetic data."""

from __future__ import annotations

import argparse

import uvicorn
from fastapi import FastAPI

from bootstrap import build_test_office
from runtime.commands import AddWatchlist, UpsertAnnotation
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB
from tests.workflows.test_office import FakeMarketData


def create_dev_app(db_path: str = "data/dev-cockpit.db") -> FastAPI:
    db = OfficeDB(db_path)
    office = build_test_office(db=db, market_data=FakeMarketData())
    rt = Runtime(office=office, account_label="dev-cockpit")
    rt.execute(AddWatchlist(ticker="AAPL", note="Mock leader"), actor="dev-seed")
    rt.execute(AddWatchlist(ticker="NVDA", note="Mock AI"), actor="dev-seed")
    rt.execute(
        UpsertAnnotation(
            id="demo-trend-1",
            ticker="AAPL",
            timeframe="1h",
            drawing={
                "type": "trendline",
                "points": [
                    {"time": 1700000000, "price": 100.0},
                    {"time": 1700086400, "price": 110.0},
                ],
            },
        ),
        actor="user",
    )
    return create_app(rt, token=None, host="127.0.0.1")


def main() -> None:
    parser = argparse.ArgumentParser(description="Avvia il dev server con dati finti")
    parser.add_argument("--host", choices=("127.0.0.1", "localhost", "::1"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default="data/dev-cockpit.db")
    args = parser.parse_args()
    app = create_dev_app(db_path=args.db)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
