"""Smoke test script for Cockpit Configurazioni backend on port 8778 (reads, writes, idempotency, restart flags, live SSE delivery)."""

from __future__ import annotations

import json
import threading
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

        # 1. Test update_settings (live setting: max_parallel to 2)
        req_data = json.dumps({
            "changes": {"max_parallel": 2},
            "reason": "smoke test update live setting",
            "confirm": True
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/v1/commands/update_settings",
            data=req_data,
            headers={"Content-Type": "application/json", "Idempotency-Key": "smoke-idemp-1", "X-Actor": "luca"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            print(f"OK: POST update_settings live -> {res}")
            assert res["ok"] is True

        # Test idempotency (same Idempotency-Key)
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            res_idemp = json.loads(resp.read().decode("utf-8"))
            print(f"OK: POST update_settings idempotency -> {res_idemp}")
            assert res_idemp["ok"] is True

        # 2. Test update_settings (restart setting: market.bar_timeframe to 5m)
        req_data_restart = json.dumps({
            "changes": {"market.bar_timeframe": "5m"},
            "reason": "smoke test update restart setting",
            "confirm": True
        }).encode("utf-8")
        req_restart = urllib.request.Request(
            f"{base}/v1/commands/update_settings",
            data=req_data_restart,
            headers={"Content-Type": "application/json", "Idempotency-Key": "smoke-idemp-2", "X-Actor": "luca"},
            method="POST",
        )
        with urllib.request.urlopen(req_restart) as resp:
            assert resp.status == 200
            res_rest = json.loads(resp.read().decode("utf-8"))
            print(f"OK: POST update_settings restart -> {res_rest}")
            assert res_rest["ok"] is True

        # Verify pending_restart in /v1/read/settings
        with urllib.request.urlopen(f"{base}/v1/read/settings") as resp:
            set_data = json.loads(resp.read().decode("utf-8"))
            print(f"OK: settings pending_restart -> {set_data.get('pending_restart')}")
            assert "market.bar_timeframe" in set_data.get("pending_restart", [])

        # 3. Test Live SSE events delivery during command execution
        received_events = []

        def listen_sse():
            req_sse = urllib.request.Request(f"{base}/v1/events")
            try:
                with urllib.request.urlopen(req_sse, timeout=3.0) as resp:
                    for _ in range(10):
                        line = resp.readline()
                        if line:
                            received_events.append(line.decode("utf-8"))
            except Exception as exc:
                print(f"SSE listen finished: {exc}")

        t = threading.Thread(target=listen_sse, daemon=True)
        t.start()
        time.sleep(0.5)

        # Trigger settings update to generate live SSE event
        req_data_sse = json.dumps({
            "changes": {"max_parallel": 3},
            "reason": "generate live sse event",
            "confirm": True
        }).encode("utf-8")
        req_trig = urllib.request.Request(
            f"{base}/v1/commands/update_settings",
            data=req_data_sse,
            headers={"Content-Type": "application/json", "Idempotency-Key": "smoke-sse-1", "X-Actor": "luca"},
            method="POST",
        )
        with urllib.request.urlopen(req_trig) as resp:
            print(f"OK: Triggered setting update for SSE -> {resp.read().decode('utf-8')}")

        time.sleep(1.0)
        print(f"OK: Received live SSE events -> {received_events}")
        assert any("settings.updated" in ev or "data:" in ev for ev in received_events)

        print("Smoke test on port 8778 (reads, live writes, idempotency, restart flags, live SSE delivery) completed successfully!")
    finally:
        p.terminate()
        p.join()


if __name__ == "__main__":
    main()
