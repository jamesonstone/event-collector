"""Core ingest orchestration."""

from __future__ import annotations

from contextlib import suppress

from event_collector.api.schemas import EventEnvelope
from event_collector.config import IngestConfig
from event_collector.errors import HashConflictError, HashValidationError, StorageError
from event_collector.hashing import canonical_json_text, sha256_json
from event_collector.ledger.base import Ledger
from event_collector.models import EventRecord, IngestResult
from event_collector.storage.base import Storage


class IngestService:
    """Validate and durably store generic event envelopes."""

    def __init__(self, *, ledger: Ledger, storage: Storage, config: IngestConfig) -> None:
        self.ledger = ledger
        self.storage = storage
        self.config = config

    def ingest(self, envelope: EventEnvelope) -> IngestResult:
        """Ingest one event envelope idempotently."""
        self._validate_hashes(envelope)
        raw_envelope_json = canonical_json_text(envelope.canonical_event())
        event_id = envelope.normalized_event_id()
        existing = self.ledger.get_event(event_id)

        if existing is not None:
            return self._handle_existing(existing, envelope, raw_envelope_json)

        record = self.ledger.insert_received(envelope, raw_envelope_json)
        if record.event_sha256 != envelope.event_sha256:
            return self._handle_existing(record, envelope, raw_envelope_json)
        return self._store_and_mark(envelope, raw_envelope_json)

    def get_event(self, event_id: str) -> EventRecord | None:
        return self.ledger.get_event(event_id)

    def _validate_hashes(self, envelope: EventEnvelope) -> None:
        if self.config.require_payload_hash:
            actual_payload_hash = sha256_json(envelope.canonical_payload())
            if actual_payload_hash != envelope.payload_sha256:
                raise HashValidationError("payload_sha256 does not match canonical payload JSON")
        if self.config.require_event_hash:
            actual_event_hash = sha256_json(envelope.canonical_event_without_event_hash())
            if actual_event_hash != envelope.event_sha256:
                raise HashValidationError(
                    "event_sha256 does not match canonical event JSON without event_sha256"
                )

    def _handle_existing(
        self,
        existing: EventRecord,
        envelope: EventEnvelope,
        raw_envelope_json: str,
    ) -> IngestResult:
        event_id = envelope.normalized_event_id()
        if (
            existing.event_sha256 != envelope.event_sha256
            or existing.payload_sha256 != envelope.payload_sha256
        ):
            message = "event_id already exists with different content hash"
            self.ledger.record_attempt(event_id, attempt_status="hash_conflict", message=message)
            if self.config.reject_hash_conflicts:
                raise HashConflictError(message)
            return IngestResult(
                event_id=event_id,
                status="hash_conflict",
                storage_uri=existing.storage_uri,
                received_at=existing.received_at,
                stored_at=existing.stored_at,
                message=message,
            )

        if existing.status == "stored" and existing.storage_uri:
            self.ledger.record_attempt(event_id, attempt_status="duplicate", message=None)
            return IngestResult(
                event_id=event_id,
                status="duplicate",
                storage_uri=existing.storage_uri,
                received_at=existing.received_at,
                stored_at=existing.stored_at,
            )

        return self._store_and_mark(envelope, raw_envelope_json)

    def _store_and_mark(self, envelope: EventEnvelope, raw_envelope_json: str) -> IngestResult:
        event_id = envelope.normalized_event_id()
        try:
            storage_uri = self.storage.write_raw_event(envelope, raw_envelope_json)
        except Exception as exc:
            error = str(exc)
            self.ledger.record_attempt(event_id, attempt_status="failed", message=error)
            with suppress(KeyError):
                self.ledger.mark_failed(event_id, error=error)
            raise StorageError(error) from exc

        stored = self.ledger.mark_stored(event_id, storage_uri=storage_uri)
        self.ledger.record_attempt(event_id, attempt_status="stored", message=None)
        return IngestResult(
            event_id=stored.event_id,
            status="stored",
            storage_uri=stored.storage_uri,
            received_at=stored.received_at,
            stored_at=stored.stored_at,
        )
