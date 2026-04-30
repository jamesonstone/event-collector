"""Ledger adapter protocol."""

from __future__ import annotations

from typing import Protocol

from event_collector.api.schemas import EventEnvelope
from event_collector.models import EventRecord


class Ledger(Protocol):
    def initialize(self) -> None:
        """Create required ledger tables."""

    def is_ready(self) -> bool:
        """Return whether the ledger can be used."""

    def get_event(self, event_id: str) -> EventRecord | None:
        """Return a stored event record by id."""

    def insert_received(self, envelope: EventEnvelope, raw_envelope_json: str) -> EventRecord:
        """Insert a new received event."""

    def mark_stored(self, event_id: str, *, storage_uri: str) -> EventRecord:
        """Mark an event as stored."""

    def mark_failed(self, event_id: str, *, error: str) -> EventRecord:
        """Mark an event as failed."""

    def mark_hash_conflict(self, event_id: str, *, error: str) -> EventRecord:
        """Mark an event id conflict."""

    def record_attempt(self, event_id: str, *, attempt_status: str, message: str | None) -> None:
        """Record an ingest attempt."""
