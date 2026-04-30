"""Filesystem raw event storage adapter."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from event_collector.api.schemas import EventEnvelope
from event_collector.errors import StorageConflictError

SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._=-]+")


class FilesystemStorage:
    """Store canonical event JSON under a deterministic raw-event path."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.raw_root = self.root / "raw"

    def is_ready(self) -> bool:
        try:
            self.raw_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return self.raw_root.is_dir() and os.access(self.raw_root, os.W_OK)

    def write_raw_event(self, envelope: EventEnvelope, raw_envelope_json: str) -> str:
        final_path = self._path_for(envelope)
        final_path.parent.mkdir(parents=True, exist_ok=True)

        if final_path.exists():
            existing = final_path.read_text(encoding="utf-8")
            if existing == raw_envelope_json:
                return final_path.resolve().as_uri()
            raise StorageConflictError(
                f"Storage object already exists with different content: {final_path}"
            )

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{final_path.name}.",
            suffix=".tmp",
            dir=str(final_path.parent),
            text=True,
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(raw_envelope_json)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, final_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        return final_path.resolve().as_uri()

    def _path_for(self, envelope: EventEnvelope) -> Path:
        occurred_date = envelope.occurred_at.date().isoformat()
        producer = _safe_segment(envelope.producer_service)
        event_name = _safe_segment(envelope.event_name)
        event_id = _safe_segment(envelope.normalized_event_id())
        return (
            self.raw_root
            / f"producer_service={producer}"
            / f"event_date={occurred_date}"
            / f"event_name={event_name}"
            / f"event_id={event_id}.json"
        )


def _safe_segment(value: str) -> str:
    safe = SAFE_SEGMENT_RE.sub("_", value.strip())
    safe = safe.strip("._")
    return safe or "unknown"
