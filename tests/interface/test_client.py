import pytest
from fastapi.testclient import TestClient

from bootstrap import build_test_office
from interface.client import RuntimeClient, RuntimeUnavailable
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB


@pytest.fixture
def test_app(tmp_path):
    db = OfficeDB(tmp_path / "client_test.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    app = create_app(rt)
    return app


def test_runtime_client_command_and_read(test_app):
    test_http_client = TestClient(test_app)
    client = RuntimeClient(client=test_http_client)

    # Command
    res = client.command(
        "add_watchlist",
        {"ticker": "MSFT", "note": "Tech"},
        actor="cli",
    )
    assert res.ok is True
    assert res.data["ticker"] == "MSFT"

    # Read
    wl = client.read("watchlist")
    assert any(item["ticker"] == "MSFT" for item in wl)


def test_runtime_client_unavailable_raises_clean_error():
    # Point to a closed port on loopback
    client = RuntimeClient(base_url="http://127.0.0.1:54321")
    with pytest.raises(RuntimeUnavailable) as exc_info:
        client.health()
    assert "http://127.0.0.1:54321" in str(exc_info.value)
