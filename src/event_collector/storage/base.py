"""Storage adapter protocol."""

from __future__ import annotations

from typing import Protocol

from event_collector.api.schemas import EventEnvelope


class Storage(Protocol):
    def is_ready(self) -> bool:
        """Return whether storage can be written."""

    def write_raw_event(self, envelope: EventEnvelope, raw_envelope_json: str) -> str:
        """Write a raw event and return its storage URI."""
