from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import make_event


def test_duplicate_event_returns_duplicate_success(api_app: object) -> None:
    client = TestClient(api_app)
    event = make_event()

    first = client.post("/v1/events", json=event)
    second = client.post("/v1/events", json=event)

    assert first.status_code == 200
    assert first.json()["status"] == "stored"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["storage_uri"] == first.json()["storage_uri"]
