"""Shared typed models for ingest results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

IngestStatus = Literal["stored", "duplicate", "hash_conflict", "rejected", "failed"]
LedgerStatus = Literal["received", "stored", "hash_conflict", "rejected", "failed"]


@dataclass(frozen=True)
class IngestResult:
    event_id: str
    status: IngestStatus
    storage_uri: str | None
    received_at: datetime
    stored_at: datetime | None
    message: str | None = None


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    event_name: str
    event_version: str
    producer_service: str
    partition_id: str | None
    subject_type: str | None
    subject_id: str | None
    payload_sha256: str
    event_sha256: str
    status: str
    storage_uri: str | None
    received_at: datetime
    stored_at: datetime | None
    last_error: str | None
    raw_envelope_json: str
