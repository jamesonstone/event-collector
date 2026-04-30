from __future__ import annotations

from fastapi.testclient import TestClient

from event_collector.hashing import sha256_json
from tests.conftest import make_event


def test_same_event_id_with_different_hash_returns_conflict(api_app: object) -> None:
    client = TestClient(api_app)
    event = make_event()
    changed = make_event(
        event_id=event["event_id"],
        payload={"order_id": "ORD-001", "status": "changed"},
    )

    assert client.post("/v1/events", json=event).status_code == 200
    response = client.post("/v1/events", json=changed)

    assert response.status_code == 409
    assert "different content hash" in response.json()["detail"]


def test_invalid_payload_hash_returns_422(api_app: object) -> None:
    client = TestClient(api_app)
    event = make_event()
    event["payload_sha256"] = "0" * 64
    event_without_event_hash = {key: value for key, value in event.items() if key != "event_sha256"}
    event["event_sha256"] = sha256_json(event_without_event_hash)

    response = client.post("/v1/events", json=event)

    assert response.status_code == 422
    assert "payload_sha256" in response.json()["detail"]
