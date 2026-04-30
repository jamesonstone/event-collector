"""SQLite ledger adapter."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from event_collector.api.schemas import EventEnvelope
from event_collector.models import EventRecord

from .models import Base, IngestAttemptRow, IngestEventRow


class SQLiteLedger:
    """SQLite-backed ingest ledger."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.path}",
            future=True,
            connect_args={"check_same_thread": False},
        )
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def is_ready(self) -> bool:
        inspector = inspect(self.engine)
        return inspector.has_table("ingest_event") and inspector.has_table("ingest_attempt")

    @contextmanager
    def _session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session

    def get_event(self, event_id: str) -> EventRecord | None:
        with self._session() as session:
            row = session.execute(
                select(IngestEventRow).where(IngestEventRow.event_id == event_id)
            ).scalar_one_or_none()
            return _to_record(row) if row is not None else None

    def insert_received(self, envelope: EventEnvelope, raw_envelope_json: str) -> EventRecord:
        row = IngestEventRow(
            event_id=envelope.normalized_event_id(),
            event_name=envelope.event_name,
            event_version=envelope.event_version,
            producer_service=envelope.producer_service,
            partition_id=envelope.partition_id,
            subject_type=envelope.subject_type,
            subject_id=envelope.subject_id,
            payload_sha256=envelope.payload_sha256,
            event_sha256=envelope.event_sha256,
            status="received",
            received_at=datetime.now(UTC),
            raw_envelope_json=raw_envelope_json,
        )
        with self._session() as session:
            try:
                session.add(row)
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.execute(
                    select(IngestEventRow).where(
                        IngestEventRow.event_id == envelope.normalized_event_id()
                    )
                ).scalar_one()
                return _to_record(existing)
            session.refresh(row)
            return _to_record(row)

    def mark_stored(self, event_id: str, *, storage_uri: str) -> EventRecord:
        with self._session() as session:
            row = _require_row(session, event_id)
            row.status = "stored"
            row.storage_uri = storage_uri
            row.stored_at = datetime.now(UTC)
            row.last_error = None
            session.commit()
            session.refresh(row)
            return _to_record(row)

    def mark_failed(self, event_id: str, *, error: str) -> EventRecord:
        with self._session() as session:
            row = _require_row(session, event_id)
            row.status = "failed"
            row.last_error = error
            session.commit()
            session.refresh(row)
            return _to_record(row)

    def mark_hash_conflict(self, event_id: str, *, error: str) -> EventRecord:
        with self._session() as session:
            row = _require_row(session, event_id)
            row.status = "hash_conflict"
            row.last_error = error
            session.commit()
            session.refresh(row)
            return _to_record(row)

    def record_attempt(self, event_id: str, *, attempt_status: str, message: str | None) -> None:
        with self._session() as session:
            session.add(
                IngestAttemptRow(
                    event_id=event_id,
                    attempt_status=attempt_status,
                    message=message,
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()


def _require_row(session: Session, event_id: str) -> IngestEventRow:
    row = session.execute(
        select(IngestEventRow).where(IngestEventRow.event_id == event_id)
    ).scalar_one_or_none()
    if row is None:
        raise KeyError(f"Unknown event_id: {event_id}")
    return row


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_record(row: IngestEventRow) -> EventRecord:
    return EventRecord(
        event_id=row.event_id,
        event_name=row.event_name,
        event_version=row.event_version,
        producer_service=row.producer_service,
        partition_id=row.partition_id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        payload_sha256=row.payload_sha256,
        event_sha256=row.event_sha256,
        status=row.status,
        storage_uri=row.storage_uri,
        received_at=_as_utc(row.received_at),
        stored_at=_as_utc(row.stored_at) if row.stored_at is not None else None,
        last_error=row.last_error,
        raw_envelope_json=row.raw_envelope_json,
    )
