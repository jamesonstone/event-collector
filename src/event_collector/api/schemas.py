"""FastAPI request and response schemas."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class Actor(BaseModel):
    type: str = Field(min_length=1, max_length=64)
    id: str | None = Field(default=None, max_length=256)


class EventEnvelope(BaseModel):
    """Generic application fact event envelope."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_name: str = Field(min_length=1, max_length=256)
    event_version: str = Field(min_length=1, max_length=32)
    producer_service: str = Field(min_length=1, max_length=128)
    producer_instance: str | None = Field(default=None, max_length=256)
    producer_deployment: str | None = Field(default=None, max_length=128)
    occurred_at: datetime
    observed_at: datetime | None = None
    partition_id: str | None = Field(default=None, max_length=256)
    subject_type: str | None = Field(default=None, max_length=128)
    subject_id: str | None = Field(default=None, max_length=256)
    aggregate_type: str | None = Field(default=None, max_length=128)
    aggregate_id: str | None = Field(default=None, max_length=256)
    correlation_id: str | None = Field(default=None, max_length=256)
    causation_id: str | None = Field(default=None, max_length=256)
    actor: Actor | None = None
    payload_sha256: str
    event_sha256: str
    payload: dict[str, Any]

    @field_validator("event_name")
    @classmethod
    def _event_name_is_path_safe(cls, value: str) -> str:
        if "/" in value or "\\" in value:
            raise ValueError("event_name must not contain path separators")
        return value

    @field_validator("occurred_at", "observed_at")
    @classmethod
    def _datetime_must_include_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime values must include timezone information")
        return value

    @field_validator("payload_sha256", "event_sha256")
    @classmethod
    def _hash_must_be_sha256_hex(cls, value: str) -> str:
        normalized = value.lower()
        if not SHA256_RE.fullmatch(normalized):
            raise ValueError("hash values must be 64-character lowercase SHA-256 hex strings")
        return normalized

    @field_serializer("event_id")
    def _serialize_event_id(self, value: UUID) -> str:
        return str(value)

    def normalized_event_id(self) -> str:
        return str(self.event_id)

    def canonical_payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.model_dump(mode="json", exclude_none=True)["payload"])

    def canonical_event_without_event_hash(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", exclude_none=True)
        data.pop("event_sha256", None)
        return data

    def canonical_event(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class BatchIngestRequest(BaseModel):
    events: list[EventEnvelope] = Field(min_length=1, max_length=1000)


class EventIngestResponse(BaseModel):
    event_id: str
    status: str
    storage_uri: str | None
    received_at: datetime
    stored_at: datetime | None
    message: str | None = None


class BatchIngestResponse(BaseModel):
    results: list[EventIngestResponse]


class EventRecordResponse(BaseModel):
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
    raw_envelope: dict[str, Any]
