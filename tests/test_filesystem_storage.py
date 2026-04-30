from __future__ import annotations

from pathlib import Path

import pytest

from event_collector.api.schemas import EventEnvelope
from event_collector.errors import StorageConflictError
from event_collector.hashing import canonical_json_text
from event_collector.storage.filesystem import FilesystemStorage
from tests.conftest import make_event


def test_filesystem_storage_is_idempotent_for_same_content(tmp_path: Path) -> None:
    storage = FilesystemStorage(tmp_path)
    event = EventEnvelope.model_validate(make_event())
    raw = canonical_json_text(event.canonical_event())

    first = storage.write_raw_event(event, raw)
    second = storage.write_raw_event(event, raw)

    assert first == second


def test_filesystem_storage_rejects_different_existing_content(tmp_path: Path) -> None:
    storage = FilesystemStorage(tmp_path)
    event = EventEnvelope.model_validate(make_event())
    raw = canonical_json_text(event.canonical_event())
    storage.write_raw_event(event, raw)

    with pytest.raises(StorageConflictError):
        storage.write_raw_event(event, raw.replace("created", "mutated"))
