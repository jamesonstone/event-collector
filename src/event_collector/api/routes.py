"""HTTP routes for event-collector."""

from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from event_collector.api.schemas import (
    BatchIngestRequest,
    BatchIngestResponse,
    EventEnvelope,
    EventIngestResponse,
    EventRecordResponse,
)
from event_collector.errors import HashConflictError, HashValidationError, StorageError
from event_collector.ingest.service import IngestService
from event_collector.models import EventRecord, IngestResult

router = APIRouter()
HTTP_UNPROCESSABLE_ENTITY = 422


def _service(request: Request) -> IngestService:
    return cast(IngestService, request.app.state.ingest_service)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> dict[str, str]:
    service = _service(request)
    if not service.ledger.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ledger not ready",
        )
    if not service.storage.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="storage not ready",
        )
    return {"status": "ready"}


@router.post("/v1/events", response_model=EventIngestResponse)
def ingest_event(envelope: EventEnvelope, request: Request) -> EventIngestResponse:
    try:
        result = _service(request).ingest(envelope)
    except HashConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except HashValidationError as exc:
        raise HTTPException(
            status_code=HTTP_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return _response_from_result(result)


@router.post("/v1/events:batch", response_model=BatchIngestResponse)
def ingest_event_batch(
    batch: BatchIngestRequest,
    request: Request,
) -> BatchIngestResponse:
    results: list[EventIngestResponse] = []
    service = _service(request)
    for envelope in batch.events:
        try:
            results.append(_response_from_result(service.ingest(envelope)))
        except HashConflictError as exc:
            results.append(
                EventIngestResponse(
                    event_id=envelope.normalized_event_id(),
                    status="hash_conflict",
                    storage_uri=None,
                    received_at=envelope.observed_at or envelope.occurred_at,
                    stored_at=None,
                    message=str(exc),
                )
            )
        except (HashValidationError, StorageError) as exc:
            results.append(
                EventIngestResponse(
                    event_id=envelope.normalized_event_id(),
                    status="failed",
                    storage_uri=None,
                    received_at=envelope.observed_at or envelope.occurred_at,
                    stored_at=None,
                    message=str(exc),
                )
            )
    return BatchIngestResponse(results=results)


@router.get("/v1/events/{event_id}", response_model=EventRecordResponse)
def get_event(event_id: str, request: Request) -> EventRecordResponse:
    record = _service(request).get_event(event_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return _record_response(record)


def _response_from_result(result: IngestResult) -> EventIngestResponse:
    return EventIngestResponse(
        event_id=result.event_id,
        status=result.status,
        storage_uri=result.storage_uri,
        received_at=result.received_at,
        stored_at=result.stored_at,
        message=result.message,
    )


def _record_response(record: EventRecord) -> EventRecordResponse:
    return EventRecordResponse(
        event_id=record.event_id,
        event_name=record.event_name,
        event_version=record.event_version,
        producer_service=record.producer_service,
        partition_id=record.partition_id,
        subject_type=record.subject_type,
        subject_id=record.subject_id,
        payload_sha256=record.payload_sha256,
        event_sha256=record.event_sha256,
        status=record.status,
        storage_uri=record.storage_uri,
        received_at=record.received_at,
        stored_at=record.stored_at,
        last_error=record.last_error,
        raw_envelope=json.loads(record.raw_envelope_json),
    )
