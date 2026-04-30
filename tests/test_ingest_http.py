from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import make_event


def test_health_ready_and_redoc(api_app: object) -> None:
    client = TestClient(api_app)

    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
    redoc = client.get("/redoc")

    assert redoc.status_code == 200
    assert "redoc" in redoc.text.lower()


def test_post_event_stores_raw_file(api_app: object, tmp_path: Path) -> None:
    client = TestClient(api_app)
    event = make_event()

    response = client.post("/v1/events", json=event)

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == event["event_id"]
    assert body["status"] == "stored"
    assert body["storage_uri"].startswith("file://")

    event_file = next((tmp_path / "event-lake" / "raw").rglob("*.json"))
    contents = event_file.read_text(encoding="utf-8")
    assert event["event_id"] in contents

    fetched = client.get(f"/v1/events/{event['event_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["raw_envelope"]["event_id"] == event["event_id"]


def test_batch_ingest(api_app: object) -> None:
    client = TestClient(api_app)
    first = make_event(event_name="example.order.created")
    second = make_event(event_name="example.order.submitted")

    response = client.post("/v1/events:batch", json={"events": [first, second]})

    assert response.status_code == 200
    assert [item["status"] for item in response.json()["results"]] == ["stored", "stored"]
