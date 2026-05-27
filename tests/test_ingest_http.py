from __future__ import annotations

import json
from pathlib import Path
from queue import Queue
from typing import cast

from fastapi.testclient import TestClient

from tests.conftest import make_event


def test_health_ready_and_api_docs(api_app: object) -> None:
    client = TestClient(api_app)

    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
    docs = client.get("/")
    redoc = client.get("/redoc")

    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()
    assert client.get("/docs").status_code == 404
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


def test_debug_endpoint_is_omitted_unless_ec_env_is_debug(
    app_config: object,
    monkeypatch: object,
) -> None:
    from event_collector.main import create_app

    monkeypatch.delenv("EC_ENV", raising=False)
    app = create_app(app_config)
    client = TestClient(app)

    assert client.get("/debug").status_code == 404
    assert client.get("/debug/history").status_code == 404
    assert client.get("/debug/stream").status_code == 404
    assert "/debug" not in client.get("/openapi.json").json()["paths"]

    monkeypatch.setenv("EC_ENV", "DEBUG")
    uppercase_app = create_app(app_config)
    uppercase_client = TestClient(uppercase_app)

    assert uppercase_client.get("/debug").status_code == 404
    assert uppercase_client.get("/debug/history").status_code == 404
    assert uppercase_client.get("/debug/stream").status_code == 404
    assert "/debug" not in uppercase_client.get("/openapi.json").json()["paths"]


def test_debug_endpoint_is_registered_when_ec_env_is_debug(
    app_config: object,
    monkeypatch: object,
) -> None:
    from event_collector.main import create_app

    monkeypatch.setenv("EC_ENV", "debug")
    app = create_app(app_config)
    client = TestClient(app)
    openapi = client.get("/openapi.json").json()

    assert "/debug" in openapi["paths"]
    debug_content = openapi["paths"]["/debug"]["get"]["responses"]["200"]["content"]
    assert set(debug_content) == {"text/html"}
    assert "/debug/history" not in openapi["paths"]
    assert "/debug/stream" not in openapi["paths"]

    page = client.get("/debug")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "/debug/stream" in page.text
    assert "correlation_id" in page.text
    assert ">Refresh<" in page.text
    assert 'id="toggleEvents"' in page.text
    assert "Open all events" in page.text
    assert "Copy JSON" in page.text
    assert "Copy event JSON" in page.text
    assert 'id="from"' in page.text
    assert 'id="to"' in page.text


def test_debug_bus_receives_submitted_events(
    app_config: object,
    monkeypatch: object,
) -> None:
    from event_collector.main import create_app

    monkeypatch.setenv("EC_ENV", "debug")
    app = create_app(app_config)
    subscriber = cast(Queue[str], app.state.debug_event_bus.subscribe())
    client = TestClient(app)
    event = make_event()

    response = client.post("/v1/events", json=event)

    try:
        debug_event = json.loads(subscriber.get(timeout=1))
    finally:
        app.state.debug_event_bus.unsubscribe(subscriber)

    assert response.status_code == 200
    assert debug_event["source"] == {"endpoint": "/v1/events"}
    assert debug_event["event_id"] == event["event_id"]
    assert debug_event["event_name"] == event["event_name"]
    assert debug_event["producer_service"] == event["producer_service"]
    assert debug_event["event"]["event_id"] == event["event_id"]

    history = client.get("/debug/history")
    assert history.status_code == 200
    assert history.json()[0]["event_id"] == event["event_id"]


def test_debug_bus_receives_batch_events(
    app_config: object,
    monkeypatch: object,
) -> None:
    from event_collector.main import create_app

    monkeypatch.setenv("EC_ENV", "debug")
    app = create_app(app_config)
    subscriber = cast(Queue[str], app.state.debug_event_bus.subscribe())
    client = TestClient(app)
    first = make_event(event_name="example.order.created")
    second = make_event(event_name="example.order.submitted")

    response = client.post("/v1/events:batch", json={"events": [first, second]})

    try:
        first_debug_event = json.loads(subscriber.get(timeout=1))
        second_debug_event = json.loads(subscriber.get(timeout=1))
    finally:
        app.state.debug_event_bus.unsubscribe(subscriber)

    assert response.status_code == 200
    assert first_debug_event["source"] == {"endpoint": "/v1/events:batch", "batch_index": 0}
    assert first_debug_event["event_id"] == first["event_id"]
    assert second_debug_event["source"] == {"endpoint": "/v1/events:batch", "batch_index": 1}
    assert second_debug_event["event_id"] == second["event_id"]


def test_debug_bus_replays_recent_history() -> None:
    from event_collector.api.routes import DebugEventBus

    bus = DebugEventBus()
    for index in range(1001):
        bus.publish(
            {
                "debug_version": "1.0",
                "streamed_at": "2026-04-30T12:00:00Z",
                "source": {"endpoint": "/v1/events"},
                "event_id": f"event-{index}",
                "event_name": "example.order.created",
                "producer_service": "example-service",
                "event": {"event_id": f"event-{index}"},
            }
        )

    subscriber = bus.subscribe()

    try:
        replayed = [json.loads(subscriber.get_nowait()) for _ in range(1000)]
    finally:
        bus.unsubscribe(subscriber)

    assert replayed[0]["event_id"] == "event-1"
    assert replayed[-1]["event_id"] == "event-1000"
