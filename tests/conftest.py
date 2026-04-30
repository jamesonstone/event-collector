from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from event_collector.config import (
    AppConfig,
    IngestConfig,
    LedgerConfig,
    ServerConfig,
    StorageConfig,
)
from event_collector.hashing import sha256_json
from event_collector.main import create_app


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=8920),
        ledger=LedgerConfig(adapter="sqlite", path=tmp_path / "ingest.sqlite"),
        storage=StorageConfig(adapter="filesystem", root=tmp_path / "event-lake"),
        ingest=IngestConfig(),
    )


@pytest.fixture
def api_app(app_config: AppConfig) -> Iterator[Any]:
    yield create_app(app_config)


def make_event(
    *,
    event_id: str | None = None,
    payload: dict[str, Any] | None = None,
    event_name: str = "example.order.created",
) -> dict[str, Any]:
    event_payload = payload or {"order_id": "ORD-001", "status": "created"}
    envelope: dict[str, Any] = {
        "event_id": event_id or str(uuid4()),
        "event_name": event_name,
        "event_version": "1.0",
        "producer_service": "example-service",
        "producer_instance": "test-1",
        "producer_deployment": "test",
        "occurred_at": "2026-04-30T12:00:00Z",
        "observed_at": "2026-04-30T12:00:01Z",
        "partition_id": "example-account",
        "subject_type": "order",
        "subject_id": "ORD-001",
        "aggregate_type": "order",
        "aggregate_id": "ORD-001",
        "correlation_id": "corr-001",
        "causation_id": "cmd-001",
        "actor": {
            "type": "user",
            "id": "user-001",
        },
        "payload": event_payload,
    }
    envelope["payload_sha256"] = sha256_json(event_payload)
    envelope["event_sha256"] = sha256_json(envelope)
    return envelope
