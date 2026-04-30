"""SQLAlchemy ORM models for the SQLite ledger."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for ledger tables."""


class IngestEventRow(Base):
    __tablename__ = "ingest_event"
    __table_args__ = (UniqueConstraint("event_id", name="uq_ingest_event_event_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(Text, nullable=False)
    event_version: Mapped[str] = mapped_column(Text, nullable=False)
    producer_service: Mapped[str] = mapped_column(Text, nullable=False)
    partition_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    event_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    stored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_envelope_json: Mapped[str] = mapped_column(Text, nullable=False)


class IngestAttemptRow(Base):
    __tablename__ = "ingest_attempt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    attempt_status: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
