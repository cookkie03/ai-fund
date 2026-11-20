"""The account label identifies which Runtime (one per broker account) a client is talking to."""

from fastapi.testclient import TestClient

from bootstrap import build_test_office
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB


def _client(rt: Runtime) -> TestClient:
    return TestClient(create_app(rt, token=None, host="127.0.0.1"))


def test_health_reports_explicit_account_label(tmp_path):
    rt = Runtime(office=build_test_office(db=OfficeDB(tmp_path / "a.db")), account_label="alpaca-main")
    assert _client(rt).get("/v1/health").json()["account_label"] == "alpaca-main"


def test_account_label_defaults_to_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_ACCOUNT_LABEL", "alpaca-swing")
    rt = Runtime(office=build_test_office(db=OfficeDB(tmp_path / "b.db")))
    assert rt.read.health().account_label == "alpaca-swing"


def test_account_label_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADING_AGENT_ACCOUNT_LABEL", raising=False)
    rt = Runtime(office=build_test_office(db=OfficeDB(tmp_path / "c.db")))
    assert rt.read.health().account_label == "default"
