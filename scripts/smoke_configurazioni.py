"""Smoke test script for Cockpit Configurazioni backend on port 8778."""

from __future__ import annotations

import json
import time
import urllib.request
from multiprocessing import Process

import uvicorn

from scripts.dev_cockpit_server import create_dev_app


def run_server():
    app = create_dev_app(db_path="data/dev-cockpit-configurazioni-be.db", approval_mode="manual")
    uvicorn.run(app, host="127.0.0.1", port=8778, log_level="warning")


def main():
    p = Process(target=run_server, daemon=True)
    p.start()
    time.sleep(2.0)  # wait for server startup

    base = "http://127.0.0.1:8778"
    try:
        endpoints = [
            "/v1/read/settings",
            "/v1/read/settings_history",
            "/v1/read/agent_configs",
            "/v1/read/prompt?agent=portfolio_manager",
            "/v1/read/prompt_history?agent=portfolio_manager",
            "/v1/read/secrets",
            "/v1/read/runtime_health",
            "/v1/read/backups",
        ]
        for ep in endpoints:
            url = f"{base}{ep}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                print(f"OK: {ep} -> received {type(data)}")

        print("Smoke test on port 8778 completed successfully!")
    finally:
        p.terminate()
        p.join()


if __name__ == "__main__":
    main()
